# Intelbras Twibi Fast — engenharia reversa e firmware customizado

[English](README.md) | **Português**

Roteador mesh **Intelbras Twibi Fast** (OEM **Tenda**, plataforma **Realtek RTL8197F**):
engenharia reversa do firmware original, recuperação de uma unidade "brickada" e
firmware próprio com SSH, sem nuvem e com controle de internet por faixa de IP.

> ⚠️ Projeto pessoal, educacional, feito **no meu próprio aparelho** (uma unidade de
> sacrifício). Não é afiliado à Intelbras nem à Tenda. Mexer no firmware **anula a
> garantia** e pode inutilizar o aparelho — se for repetir, faça por sua conta e risco.

---

## TL;DR

- O Twibi Fast é um **RTL8197F + RTL8812BRH**, 8 MB de flash, 64 MB de DDR2, Linux 3.10.90.
- Uma unidade parou de bootar (`rootfs checksum error`) — era **rootfs truncado** por
  uma atualização interrompida.
- Recuperei pela **UART** (115200) + **disaster mode** do bootloader + **TFTP**.
- Decifrei o **checksum do rootfs** que o bootloader valida (soma de 16 bits).
- Construí um **firmware próprio** (`chiconws`) mantendo o kernel oficial:
  SSH no lugar do telnet, sem nuvem/TR-069, branding próprio, faixa de IP para IoT com
  internet ligável/desligável, página web e API JSON.
- Decifrei a interface de **VLAN** do switch interno e como o driver faz a bridge do
  `eth0.9` (com os limites: sem trunk na porta LAN, sem VLAN por MAC).
- O firmware atual é o **Twibify** (mínimo, nuvem mantida, SSH, grupo IoT por MAC, página
  dentro da UI original) — veja [`chiconws/twibify`](https://github.com/chiconws/twibify).

---

## Antes de tudo: o que é UART e o que é o FTDI232

**UART** é a "porta serial" do aparelho — um **console de texto** que existe desde o
primeiro programa (o bootloader), antes de qualquer rede ou sistema operacional. Em vez
de teclado e monitor, você liga **três fios** (GND, TX, RX) a um adaptador no PC e
passa a ver e digitar o que o roteador vê durante o boot. É o que salvou este aparelho:
com a flash corrompida, era o único canal que ainda respondia.

**FTDI232** (chip **FT232RL**) é o **adaptador USB → serial**: de um lado o USB do PC
(aparece como `/dev/ttyUSB0`), do outro três pinos que vão nos pads da placa. É vendido
como "adaptador FTDI FT232RL" (aqueles módulos com jumper **3,3 V / 5 V**). Ele **não**
alimenta a placa: o Twibi usa a própria fonte de 9 V; do adaptador vêm só os sinais.

<p align="center">
  <img src="images/uart-pads.jpg" width="360" alt="Pads do UART na placa">
</p>

| Pad da placa | Sinal | Vai no adaptador |
|---|---|---|
| 1 | GND | GND (ligue **primeiro**) |
| 2 | RX (entrada) | TX do adaptador |
| 3 | VCC 3,3 V | **nada** |
| 4 | TX (saída) | RX do adaptador |

Detalhes: adaptador em **3,3 V**, console em **115200 8N1**, `TX ↔ RX` cruzados e
GND comum. Qualquer terminal serial serve (PuTTY, `picocom`, `minicom`, `screen`) — e
este repo inclui um em Python (`tools/` do projeto completo).

## Glossário rápido

| Termo | O que é |
|---|---|
| **UART** | console serial da placa (texto, 3 fios) |
| **FTDI232** | adaptador USB ↔ serial usado para falar com a UART |
| **TFTP** | protocolo simples de transferência de arquivo (UDP); o bootloader escuta em `192.168.1.6` |
| **Bootloader** | primeiro programa da flash: inicializa a RAM, carrega o kernel e tem o modo de recuperação |
| **uImage** | cabeçalho de 64 bytes que embrulha a imagem do firmware |
| **squashfs** | sistema de arquivos comprimido e somente-leitura usado no rootfs |
| **rootfs** | a "raiz" do Linux: todos os arquivos do firmware |
| **checksum** | soma de verificação que o bootloader usa para validar o rootfs |
| **CFM** | partição de configuração persistente do firmware (chaves `chave=valor`) |

---

## Hardware

| Item | Detalhe |
|---|---|
| SoC | Realtek **RTL8197FNT** — MIPS 24Kc @ 600 MHz, DRAM DDR2 64 MB no pacote |
| 5 GHz | **RTL8812BRH** (802.11ac 2×2) |
| 2,4 GHz | rádio integrado do RTL8197F |
| Flash | 8 MB SPI (BOYAMICRO/BOHONG **BH25Q64**) |
| Ethernet | 2× 100 Mbps (uma porta é WAN/LAN automática) |
| Alimentação | 9 V / 1 A, **centro positivo** |

<p align="center">
  <img src="images/board.jpg" width="520" alt="Placa do Twibi Fast">
</p>

Fotos do SoC e do rádio 5 GHz: [`images/soc-rtl8197fnt.jpg`](images/soc-rtl8197fnt.jpg),
[`images/soc-rtl8812brh.jpg`](images/soc-rtl8812brh.jpg).

---

## O aparelho brickado e a recuperação

Sintoma: LED fixo, link de rede ativo mas **RX = 0** (não transmitia), sem DHCP, sem
SSID, botão de reset sem efeito.

Pela UART apareceu a causa:

```
Booting...
DRAM Type: DDR2, 533MHz, Size: 64MB
found BH25Q64, size=8MB
Boot release version:247 (May 11 2018) (600MHz)
wait for upgrage
rootfs checksum error at 0021D012!
<RealTek>
```

O firmware do aparelho estava com o **rootfs truncado** (só ~256 KB de 3,4 MB) — o
bootloader rodava, mas recusava o rootfs e parava no prompt.

### UART

Conector 2×2 na placa. A ordem real (descoberta medindo continuidade e testando):

<p align="center">
  <img src="images/uart-pinout.jpg" width="420" alt="Pads do UART">
</p>

| Pad | Sinal |
|---|---|
| 1 | **GND** |
| 2 | **RX** (entrada da placa — vai no TX do adaptador) |
| 3 | **VCC 3,3 V** — **não ligar** |
| 4 | **TX** (saída da placa — vai no RX do adaptador) |

Console em `115200 8N1`. O adaptador deve estar em **3,3 V**; **nunca** conecte o VCC
dele ao pad 3.

### Disaster mode + TFTP (por cabo Ethernet)

Antes de tudo: **a UART é só o console** — é por ela que você vê o boot e digita
comandos. A **imagem do firmware não passa pela UART**: ela é enviada por **cabo de
rede**, usando TFTP (o bootloader sobe um servidor TFTP em `192.168.1.6` e você empurra
o arquivo pelo PC). São dois canais separados: UART para enxergar/diagnosticar, Ethernet
para transferir.

Segurando o reset **no power-on**, o bootloader entra em modo de recuperação
(`Entry disaster mode`) e sobe o servidor TFTP. Enviando a imagem com o cabeçalho uImage
removido (6.378.516 bytes), ele valida e grava sozinho:

```
Linux kernel (root-fs) upgrade.
checksum Ok !
burn kernel-fs Addr:0x00030000 ...
squashfs upgrade. checksum Ok !
burn rootfs ...
reboot.......
```

Detalhes do procedimento: [`docs/recovery.pt-BR.md`](docs/recovery.pt-BR.md).

---

## O checksum do rootfs (decifrado)

O bootloader valida o rootfs com uma soma simples, descoberta descompilando o segundo
estágio dele:

```
len = bswap32(*(u32 *)(rootfs + 8)) + 0x282;
sum = 0;
for (i = 0; i < len; i += 2)
    sum += bswap16(*(u16 *)(rootfs + i));
if (sum != 0) -> "rootfs checksum error"
```

Ou seja: **soma de 16 bits (big-endian) que tem que dar zero**; os 2 bytes finais são o
complemento. O campo em `squashfs+8` guarda `tamanho_total - 0x282`.

A ferramenta [`tools/mkimage_twibi.py`](tools/mkimage_twibi.py) recalcula isso e produz
uma imagem aceita pelo bootloader — o round-trip com a imagem oficial é byte a byte
idêntico.

---

## Firmware `chiconws`

Firmware próprio montado sobre o rootfs oficial (mesmo kernel, mesma partição), com:

| Recurso | Original | `chiconws` |
|---|---|---|
| Acesso remoto | telnet (texto claro) | **SSH** (dropbear estático) |
| Nuvem Tenda (`ucloud`) | ativo | removido |
| TR-069 (`cwmpd`) | ativo | removido |
| Reboot diário (03:00) | ativo | desligado |
| Hostname / banner / web | Intelbras | `chiconws` |
| Faixa IoT `192.168.6.200-254` | — | internet **ligável/desligável** |
| Página web + API JSON | — | `http://twibi.lan:8080/` |

<p align="center">
  <img src="images/board-bottom.jpg" width="520" alt="Face inferior da placa">
</p>

Detalhes: [`docs/firmware.pt-BR.md`](docs/firmware.pt-BR.md).

---

## Limitações conhecidas

- **VLANs: parcial.** O driver expõe `/proc/net/vlan` e a tabela VLAN do ASIC pode ser
  programada. Com o modo VLAN ligado (`echo "1 1" > /proc/net/vlan/vlanEnable`) e o
  `eth0.9` na bridge em vez do `eth0`, clientes com e sem tag funcionam. Mas a **porta LAN
  (porta 0) não entra em outra VLAN** (sem trunk nela), **não existe VLAN por MAC** (o ACL
  não tem ação de VLAN) e o kernel 3.10 não tem bridge VLAN filtering nem ebtables.
  Detalhes: [`docs/vlan.pt-BR.md`](docs/vlan.pt-BR.md).
- **O upgrade local da web original é stub**: `POST /goform/upgrade` (campo multipart
  `upgradeFile`) devolve `{"errcode":"1005"}` tanto para a imagem oficial 1.1.11 quanto
  para uma customizada — o upgrade local está desabilitado nesta build.
- **Temperatura**: não há sensor de temperatura do SoC exposto no Linux. O
  `/proc/wlan0/thermal` (medidor "thermal meter" da Realtek) é um **ADC relativo**, útil
  para tendência, não em °C.
- **Tailscale no roteador**: inviável (44 MB de RAM, ~1,4 MB livres no rootfs, sem
  `/dev/net/tun`). O caminho é usar uma RPi como subnet router.

---

## Firmwares

As imagens estão em [`firmware/`](firmware/):

- **`twibi_fast_1.1.11.bin`** — firmware oficial (Intelbras), para restaurar de fábrica
- **`chiconws-v20.bin`** — o firmware customizado deste projeto (legado)

O firmware atual é o **Twibify**, em repositório próprio:
[`chiconws/twibify`](https://github.com/chiconws/twibify).

A gravação é pelo **disaster mode + TFTP**, enviando a imagem **sem os 64 bytes do
cabeçalho uImage** (o `firmware/README.pt-BR.md` mostra o comando). Detalhes em
[`docs/recovery.pt-BR.md`](docs/recovery.pt-BR.md).

## Estrutura do repositório

```
docs/
  recovery.md    recuperação (UART, disaster mode, TFTP, checksum)
  firmware.md    como o chiconws/Twibify foram montados e gravados
  vlan.md        a interface de VLAN do switch interno e seus limites
  hardware.md    placa, chips, pinagens, alimentação
tools/
  mkimage_twibi.py   monta a imagem com o checksum correto
  tftp_put.py        envia a imagem no disaster mode
  unpack_kernel.py   extrai o kernel do container cr6c
images/          fotos da placa, UART e flash
firmware/        imagens .bin (oficial e chiconws) + instruções
```

## Ferramentas usadas

Ghidra (descompilação do bootloader e do firmware), binwalk/unsquashfs, U-Boot
`mkimage` (referência), musl-cross (compilação estática do dropbear e do servidor web),
tftpy e um adaptador FTDI 3,3 V.

## Créditos

Projeto realizado com o auxílio do **DeepSeek** — engenharia reversa do firmware,
recuperação do aparelho, desenvolvimento do firmware customizado e desta documentação.

## Licença

MIT — veja [`LICENSE`](LICENSE).
