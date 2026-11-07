#!/usr/bin/env python3
"""Envia um arquivo por TFTP para o bootloader do Twibi.

Uso:
    python tools/tftp_put.py 192.168.1.6 arquivo.bin [--name nome_remoto]

O bootloader Realtek escuta em 192.168.1.6 por padrão (IPCONFIG no console).
"""

from __future__ import annotations

import argparse
import sys

import tftpy


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host")
    ap.add_argument("file")
    ap.add_argument("--name", default=None, help="nome remoto (default: basename)")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--blksize", type=int, default=512)
    args = ap.parse_args()

    name = args.name or args.file.rsplit("/", 1)[-1]
    opts = {} if args.blksize >= 512 else {"blksize": str(args.blksize)}
    client = tftpy.TftpClient(args.host, 69, opts)
    try:
        client.upload(name, args.file, timeout=args.timeout)
    except Exception as err:  # noqa: BLE001 - queremos a mensagem crua
        print(f"falhou: {type(err).__name__}: {err}")
        return 1
    print(f"enviado {args.file} -> {args.host}:/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
