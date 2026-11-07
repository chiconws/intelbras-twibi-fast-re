# Firmwares

Dois arquivos, no formato **`.bin` (uImage + payload)** que o firmware oficial usa:

| Arquivo | Tamanho | SHA-256 |
|---|---|---|
| `twibi_fast_1.1.11.bin` | 6.378.580 B | `ec90662d…5ff01` |
| `chiconws-v20.bin` | 6.566.996 B | `12e71fa6…89a8e` |

## Qual usar

- **`twibi_fast_1.1.11.bin`** — firmware **oficial da Intelbras** (versão 1.1.11), o
  ponto de partida. Serve para restaurar o aparelho ao estado de fábrica ou para
  reconstruir o firmware customizado.
- **`chiconws-v20.bin`** — firmware customizado descrito em
  [`../docs/firmware.md`](../docs/firmware.md): SSH no lugar do telnet, sem nuvem nem
  TR-069, sem reboot diário, branding próprio, faixa de IP para IoT com internet
  ligável/desligável, página web e API JSON.

## Como gravar

O bootloader aceita a imagem **sem os 64 bytes do cabeçalho uImage**. Os dois arquivos
aqui **incluem** o cabeçalho, então antes de enviar remova os primeiros 64 bytes:

```sh
python3 - <<'EOF'
d = open('chiconws-v20.bin','rb').read()
open('payload.bin','wb').write(d[0x40:])   # 64 bytes a menos
EOF

# com o aparelho em disaster mode e o PC em 192.168.1.0/24:
python3 ../tools/tftp_put.py 192.168.1.6 payload.bin --name payload.bin
```

O procedimento completo (UART, disaster mode, reset no power-on) está em
[`../docs/recovery.md`](../docs/recovery.md).

## Aviso de origem

- O `twibi_fast_1.1.11.bin` é **propriedade da Intelbras** (firmware OEM da Tenda).
  Está aqui apenas para **recuperação e estudo** do próprio aparelho. Se você é o
  detentor dos direitos e quer a remoção, abra uma issue.
- O `chiconws-v20.bin` é um **derivado** do rootfs oficial (mesmo kernel, mesmas
  partições), com as modificações documentadas em [`../docs/firmware.md`](../docs/firmware.md).
- Nenhum dos arquivos contém dados pessoais: são imagens de firmware "de fábrica".
