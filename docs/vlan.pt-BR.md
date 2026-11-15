# VLANs no switch interno

[English](vlan.md) | **Português**

Resumo: o switch RTL865x **sabe** marcar e bridgear VLANs, mas o driver só expõe parte
disso. Clientes com e sem tag funcionam **se** a interface da LAN for um dispositivo VLAN
(`eth0.9`) em vez do `eth0`. O que **não** funciona: trunk na porta LAN, VLAN por MAC e
isolamento L2 por cliente.

## Onde ficam os controles

```
/proc/net/vlan/vlanEnable     global: "vlan enable:%x hw support enable:%d"
/proc/net/vlan/pvid           PVID por porta (ASIC) e por netdev (VAPs do Wi-Fi)
/proc/net/vlan/groupIndex     VID sendo configurado (cursor)
/proc/net/vlan/vlanGroup      tabela VLAN: <vid>, <máscara de membros>, <máscara de tag>, <tipo>
/proc/net/vlan/wanVlanId      VID do WAN usada pelo NAT (8)
/proc/net/vlan/hwNatLanVid    VID da LAN usada pelo hw NAT (9)
/proc/rtl865x/vlan            dump da tabela VLAN do ASIC
/proc/rtl865x/pvid            dump dos PVIDs do ASIC
```

Parecem somente leitura (`-r--r--r--`), mas **o root escreve** via
`CAP_DAC_OVERRIDE`; os handlers existem de verdade.

## Formatos (confirmados na bancada)

```sh
echo "1 1" > /proc/net/vlan/vlanEnable     # liga + hw support (espaço, não vírgula)
echo "0 0" > /proc/net/vlan/vlanEnable     # desliga
echo "9,20,9,9,9" > /proc/net/vlan/pvid    # PVID das portas 0..4 (ASIC)
echo 10 > /proc/net/vlan/groupIndex        # o VID sendo configurado
echo "1,<membros>,<taggeados>,10,0" > /proc/net/vlan/vlanGroup
```

O `vlanGroup` usa `%d,%x,%x,%d,%d`: campo 1 é o enable, campo 2 a **máscara de membros**,
campo 3 a **máscara de taggeados**, campo 4 o **VID** (tem que ser igual ao `groupIndex`)
e campo 5 uma flag. O handler adiciona a porta da CPU (8) sozinho.

## A arquitetura do bridge (a parte que importa)

Com o modo VLAN ligado, o switch entrega os frames ao Linux **taggeados**. Bridgear o
`eth0` cru então descarta tudo (o bridge do 3.10 não entende VLAN). O próprio OEM já faz
do jeito certo (`default.cfg`: `lan_ifnames=vlan1 wlan0 wlan1`):

```sh
vconfig add eth0 9
ifconfig eth0.9 up
brctl delif br0 eth0
brctl addif br0 eth0.9
```

Depois disso os clientes sem tag funcionam normalmente e o `br0` fica com
`eth0.9 wlan0 wlan-msh wlan1`.

Sintomas quando o bridge está errado: os contadores do `eth0` sobem e o bridge descarta
tudo; com o modo VLAN desligado, escrever no `vlanGroup` imprime
`rtk 11q vlan support not enabled!!!`.

## Limites encontrados

- **A porta 0 (LAN) não entra em outra VLAN.** Um VID novo com a porta 0 como membro não
  é criado na tabela do ASIC (testado com o VID 60). A porta 1 (WAN) aceita.
- **Não existe VLAN por MAC**: o dump do ACL expõe só `permit`, `to cpu`, `mirror`,
  `deny`, `redirect to ether/pppoe` — não há ação de VLAN.
- **Sem bridge VLAN filtering** (kernel 3.10) e **sem ebtables** (não está no kernel).
- Isolamento L2 por cliente é, portanto, **impossível** neste firmware; a alternativa é
  agrupar em L3 (bloqueio por MAC, que é o que o Twibify faz).

## Símbolos úteis

```
vlan_group_write       0x804558dc   handler do /proc/net/vlan/vlanGroup
vlan_pvid_write        0x804556ac   handler do pvid
vlan_ctl_single_write  0x8045550c   handler do vlanEnable
rtk_add_eth_vlan       0x8017b544   aplica uma VLAN (caminho hw support)
rtl865x_addVlan        0x8018ff24
rtl865x_addVlanPortMember 0x8018fbb4
rtl865x_setVlanPortTag    0x8018fa04
rtl865x_setVlanFilterDatabase 0x8018f948
```

Tudo é **só de runtime**: um reboot volta VID 8/9, `vlanEnable=0` e PVID
`9,8,9,9,9`.
