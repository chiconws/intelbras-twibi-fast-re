# Recuperação do Twibi Fast (disaster mode + TFTP)

Procedimento usado para ressuscitar uma unidade que não bootava
(`rootfs checksum error`), e também para gravar qualquer firmware novo.

## 1. Sintoma do brick

- LED fixo, sem SSID, sem DHCP
- Link de rede ativo, mas **0 bytes recebidos** (não transmitia)
- Botão de reset sem efeito (quem lê o botão é o firmware, não o hardware)

No console UART:

```
Booting...
DRAM Type: DDR2, 533MHz, Size: 64MB
found BH25Q64, size=8MB
Boot release version:247 (May 11 2018) (600MHz)
wait for upgrage
rootfs checksum error at 0021D012!
<RealTek>
```

O rootfs estava truncado: o superblock do squashfs dizia 3,39 MB, mas a partir de
`0x220000` a flash era só `0xFF`.

## 2. UART (console serial)

**O que é:** a UART é o console de texto do aparelho. Ela funciona desde o bootloader,
independente de rede ou sistema — é como "plugar um teclado e um monitor" na placa. Com
a flash corrompida, foi o único jeito de ver o erro (`rootfs checksum error`) e de
confirmar que o bootloader ainda estava vivo.

**O que você precisa:** um adaptador **USB → serial FTDI232** (FT232RL), daqueles com
jumper 3,3 V/5 V. Ele aparece no PC como `/dev/ttyUSB0` (Linux) ou `COMx` (Windows) e
**não** alimenta a placa — o Twibi usa a fonte de 9 V. Configure o jumper em **3,3 V**
(a placa é 3,3 V; 5 V pode danificar o SoC).

Pads 2×2 na placa (vista de cima):

<p align="center">
  <img src="../images/uart-pinout.jpg" width="380" alt="Pinagem do UART">
</p>

| Pad | Sinal | Liga no adaptador |
|---|---|---|
| 1 | GND | GND |
| 2 | RX (entrada) | TX do adaptador |
| 3 | VCC 3,3 V | **nada** |
| 4 | TX (saída) | RX do adaptador |

`115200 8N1`. Ligue **o GND primeiro** (sem ele o console fica mudo e a placa pode
ficar com o RX flutuando, imprimindo `<RealTek>` sem parar). Não ligue o VCC do
adaptador no pad 3 — o Twibi já é alimentado pela fonte.

Para abrir o console, qualquer terminal serial serve:

- Linux: `picocom -b 115200 /dev/ttyUSB0`, `minicom -D /dev/ttyUSB0 -b 115200` ou
  `screen /dev/ttyUSB0 115200`
- Windows: PuTTY em modo Serial, 115200, 8N1
- O projeto completo inclui `tools/uart_console.py` (console com log e comandos via FIFO)

## 3. Disaster mode

1. Desligar a fonte.
2. Segurar o **reset**.
3. Ligar a fonte e manter o reset por ~5 s.
4. Soltar: o console mostra `Entry disaster mode` e o bootloader sobe o TFTP em
   **`192.168.1.6`** (padrão Realtek).

## 4. Enviar a imagem

O arquivo enviado é o **payload do `.bin` oficial sem o cabeçalho uImage de 64 bytes**:

```bash
# .bin oficial -> payload
python3 - <<'EOF'
d = open('twibi_fast_1.1.11.bin','rb').read()
open('payload.bin','wb').write(d[0x40:])
EOF

# PC com IP em 192.168.1.0/24, então:
python3 tools/tftp_put.py 192.168.1.6 payload.bin --name payload.bin
```

O bootloader reconhece a imagem sozinho:

```
**TFTP Client Upload File Size = 00615414 Bytes at A0A00000
Success!
Linux kernel (root-fs) upgrade.
checksum Ok !
burn kernel-fs Addr:0x00030000 srcAddr:0xa0a00000 len:0x001ed412
squashfs upgrade.
checksum Ok !
burn rootfs first aligned block
burn rootfs Addr:0x00220000! srcAddr:0xa0bf0000 len:0x00425414
reboot.......
```

Não é preciso UART para a transferência — só para acompanhar/diagnosticar. O modo
disaster é acionado pelo reset no power-on e o TFTP é Ethernet puro.

## 5. Layout da flash (8 MB)

| Offset | Tamanho | Partição |
|---|---|---|
| `0x000000` | 128 KB | `Bootloader` |
| `0x020000` | 64 KB | `CFG` |
| `0x030000` | 7,5 MB | `KernelFS` (kernel `cr6c` + rootfs) |
| `0x21D412` | — | início do `RootFS` (squashfs, precedido de assinatura `83 12`) |
| `0x7C0000` | 64 KB | `CFM` (configuração) |
| `0x7D0000` | 64 KB | `CFM_BACKUP` |
| `0x7E0000` | 64 KB | `LOG` |
| `0x7F0000` | 64 KB | `ENV` |

## 6. O checksum do rootfs

O segundo estágio do bootloader (gzip em `0x8D60` do primeiro estágio) foi
descompactado e descompilado; a função `check_rootfs_image` faz:

```c
len = bswap32(*(u32 *)(rootfs + 8)) + 0x282;   // campo big-endian no header do squashfs
sum = 0;
for (i = 0; i < len; i += 2)
    sum += bswap16(*(u16 *)(rootfs + i));       // soma de 16 bits, big-endian
if (sum != 0) "rootfs checksum error";
```

- O campo em `squashfs+8` (que o squashfs chama de `mkfs_time`) guarda
  `tamanho_total - 0x282`.
- Os 2 bytes finais são o complemento que zera a soma.
- Validado nos dois firmwares (oficial e recuperado): soma = 0.

[`tools/mkimage_twibi.py`](../tools/mkimage_twibi.py) recalcula o campo e o checksum e
produz a imagem completa (uImage + payload) — o round-trip com o `.bin` oficial é
byte a byte idêntico.

## 7. Observações práticas

- O TFTP aceita qualquer nome de arquivo; o que importa é o **conteúdo**.
- Arquivos pequenos/inválidos (ex.: 5 bytes) são carregados na RAM e ignorados — só uma
  imagem válida dispara o upgrade.
- Se o TFTP falhar, o aparelho provavelmente não está em disaster mode: repita o
  power-on com o reset.
- Mesmo sem UART dá para gravar: o risco é não ver o que aconteceu.
