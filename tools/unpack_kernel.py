#!/usr/bin/env python3
"""Descomprime o kernel do container `cr6c` do Twibi Fast.

Formato (descoberto em 2026-11-03):

    0x0000  64 B   header uImage (só no pacote .bin; na flash não existe)
    0x0000  16 B   "cr6c" + load (0x80a00000) + offset flash (0x30000) + tamanho
    0x0038  ~10 KB stub MIPS de descompressão (LZMA padrão)
    0x2813   1 B   flag (0x01)
    0x2814   4 B   entry point do kernel (0x80468cf0)
    0x2818   5 B   props LZMA (0x5d -> lc=3, lp=0, pb=2; dict 8 MB)
    0x281d   4 B   tamanho descomprimido (0x00657e1c)
    0x2821   4 B   zero
    0x2825  ...    stream LZMA (sem o byte inicial 0x00 do range coder)

O stream não começa com 0x00, que o liblzma exige; o stub ignora o primeiro
byte. Por isso a extração completa falha no fim: usamos decodificação em blocos
e guardamos o que foi produzido antes do erro.

Uso:
    python unpack_kernel.py firmware/twibi_fast_1.1.11.bin firmware/kernel.raw
"""

from __future__ import annotations

import lzma
import struct
import sys

STUB_OFFSET = 0x2813
ENTRY_OFFSET = 0x2814
PROPS_OFFSET = 0x2818
USIZE_OFFSET = 0x281D
STREAM_OFFSET = 0x2825

FILTERS = [{"id": lzma.FILTER_LZMA1, "dict_size": 1 << 23, "lc": 3, "lp": 0, "pb": 2}]


def unpack(image: bytes) -> tuple[bytes, dict[str, int]]:
    """Devolve (kernel, metadados) a partir da imagem ou do payload do kernel."""
    # aceita tanto o .bin (com uImage) quanto o payload cru
    base = 0x40 if image[:4] == b"\x27\x05\x19\x56" else 0
    payload = image[base:]
    if payload[:4] != b"cr6c":
        raise SystemExit("não achei o magic cr6c")

    entry = struct.unpack("<I", payload[ENTRY_OFFSET : ENTRY_OFFSET + 4])[0]
    usize = struct.unpack("<I", payload[USIZE_OFFSET : USIZE_OFFSET + 4])[0]
    props = payload[PROPS_OFFSET : PROPS_OFFSET + 5]

    dec = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=FILTERS)
    src = payload[STREAM_OFFSET:]
    out = bytearray()
    error_at = -1
    for i in range(0, len(src), 65536):
        try:
            out += dec.decompress(src[i : i + 65536])
        except lzma.LZMAError:
            error_at = i
            break
        if dec.eof:
            break

    meta = {
        "entry": entry,
        "usize": usize,
        "out": len(out),
        "error_at": error_at,
        "props": props[0],
    }
    return bytes(out), meta


def main() -> int:
    src = sys.argv[1]
    dst = sys.argv[2]
    kernel, meta = unpack(open(src, "rb").read())
    open(dst, "wb").write(kernel)
    print(f"entry        {meta['entry']:#010x}")
    print(f"usize        {meta['usize']:#x}")
    print(f"extraído     {meta['out']} B ({meta['out'] / meta['usize'] * 100:.1f}%)")
    if meta["error_at"] >= 0:
        print(f"parou em     offset {meta['error_at']:#x} do stream")
    print(f"escrito em   {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
