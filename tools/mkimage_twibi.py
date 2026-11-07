#!/usr/bin/env python3
"""Monta uma imagem de firmware no formato do Twibi Fast.

Formato: header uImage (64 B) + kernel (container cr6c) + squashfs + padding + 2 B
de checksum do bootloader, com o tamanho total no campo 0x28 do header.

O checksum do rootfs e a soma de 16 bits (big-endian) sobre
``bswap32(squashfs+8) + 0x282`` bytes, que precisa dar zero: os 2 bytes finais
sao o complemento. O campo em ``squashfs+8`` guarda ``total - 0x282``.

Uso:
    ./mkimage_twibi.py --kernel kernel.lzma --rootfs rootfs.squashfs --out nova.bin

O header fixo e embutido (nao precisa da imagem oficial). Se quiser usar os
campos de um header especifico, passe ``--template``.
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

IH_MAGIC = 0x27051956
LOAD_ADDR = 0x80000000
ENTRY_POINT = 0x80468CF0

# Header padrao (campos fixos do firmware oficial; size/dcrc/hcrc/0x28 sao calculados)
DEFAULT_HEADER = bytes.fromhex(
    "27051956" "00000000" "69ba3d04" "00000000"
    "80000000" "80468cf0" "00000000" "05050203"
    "02000000" "11030003" "00000000" "00000000"
    "00000000" "00000000" "00000000" "00000000"
)


def uimage_header(payload: bytes, template: bytes, total_size: int) -> bytes:
    """Monta o header de 64 B.

    ``template`` e o header original: os campos fora de magic/size/dcrc/hcrc/
    0x28 (versao, tipo, nome) sao copiados dele.
    """
    header = bytearray(template or DEFAULT_HEADER)
    if len(header) < 0x40:
        header += b"\x00" * (0x40 - len(header))
    struct.pack_into(">I", header, 4, 0)  # hcrc zerado para o calculo
    struct.pack_into(">I", header, 0x0C, len(payload))
    struct.pack_into(">I", header, 0x18, zlib.crc32(payload) & 0xFFFFFFFF)
    struct.pack_into(">I", header, 0x28, total_size)
    struct.pack_into(">I", header, 4, zlib.crc32(bytes(header)) & 0xFFFFFFFF)
    return bytes(header)


def rootfs_checksum(squashfs: bytes) -> tuple[bytes, int]:
    """Ajusta o campo de tamanho e devolve (rootfs+pad+checksum, checksum).

    O bootloader Realtek soma palavras de 16 bits big-endian da raiz por
    ``tamanho + 0x282`` bytes e exige soma zero; os 2 bytes finais zeram a conta.
    O campo em ``squashfs+8`` (big-endian) guarda ``total - 0x282``.
    """
    sq = bytearray(squashfs)
    pad = (-len(sq)) % 0x1000
    total = len(sq) + pad + 2
    struct.pack_into(">I", sq, 8, total - 0x282)
    body = bytes(sq) + b"\x00" * pad
    acc = 0
    for i in range(0, len(body), 2):
        acc = (acc + struct.unpack(">H", body[i : i + 2])[0]) & 0xFFFF
    checksum = (0x10000 - acc) & 0xFFFF
    return body + struct.pack(">H", checksum), checksum


def build(kernel: bytes, squashfs: bytes, template: bytes, checksum: int | None = None) -> bytes:
    """Devolve a imagem completa.

    O uImage da Tenda embrulha a imagem inteira: ``ih_size`` e o CRC de dados
    cobrem kernel + squashfs + trailer, e o campo 0x28 guarda o tamanho total.
    """
    rootfs, calc = rootfs_checksum(squashfs)
    if checksum is not None and checksum != calc:
        raise SystemExit(f"checksum informado {checksum:#06x} != calculado {calc:#06x}")
    payload = kernel + rootfs
    header = uimage_header(payload, template, 0x40 + len(payload))
    return header + payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--rootfs", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="opcional: .bin oficial para copiar os campos fixos do header",
    )
    parser.add_argument("--checksum", type=lambda x: int(x, 0), default=None,
                        help="confere o checksum calculado contra este valor")
    args = parser.parse_args()

    template = args.template.read_bytes()[:0x40] if args.template else DEFAULT_HEADER
    image = build(args.kernel.read_bytes(), args.rootfs.read_bytes(), template, args.checksum)
    args.out.write_bytes(image)

    squashfs_off = 0x40 + args.kernel.stat().st_size
    print(f"imagem    {len(image):>10} B")
    print(f"header    {0x40:>10} B")
    print(f"kernel    {args.kernel.stat().st_size:>10} B  (em 0x000040)")
    print(f"squashfs  {args.rootfs.stat().st_size:>10} B  (em {squashfs_off:#08x})")
    print(f"trailer   {len(image) - squashfs_off - args.rootfs.stat().st_size:>10} B")


if __name__ == "__main__":
    main()
