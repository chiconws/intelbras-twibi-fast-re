# Firmwares

**English** | [Português](README.pt-BR.md)

Two files, in the **`.bin` (uImage + payload)** format used by the official firmware:

| File | Size | SHA-256 |
|---|---|---|
| `twibi_fast_1.1.11.bin` | 6,378,580 B | `ec90662d…5ff01` |
| `chiconws-v20.bin` | 6,566,996 B | `12e71fa6…89a8e` |

## Which one to use

- **`twibi_fast_1.1.11.bin`** — the **official Intelbras firmware** (1.1.11), the starting
  point. Use it to restore the device to factory state or to rebuild the custom firmware.
- **`chiconws-v20.bin`** — the custom firmware described in
  [`../docs/firmware.md`](../docs/firmware.md): SSH instead of telnet, no cloud or TR-069,
  no daily reboot, custom branding, an IoT IP range with internet on/off, a web page and a
  JSON API.

## How to flash

The bootloader accepts the image **without the 64-byte uImage header**. Both files here
**include** the header, so strip the first 64 bytes before sending:

```sh
python3 -c "d=open('chiconws-v20.bin','rb').read(); open('payload.bin','wb').write(d[0x40:])"
```

# with the device in disaster mode and the PC in 192.168.1.0/24:
python3 ../tools/tftp_put.py 192.168.1.6 payload.bin --name payload.bin
```

The full procedure (UART, disaster mode, reset at power-on) is in
[`../docs/recovery.md`](../docs/recovery.md).

## Provenance notice

- `twibi_fast_1.1.11.bin` is **Intelbras property** (Tenda OEM firmware). It is here only
  for **recovery and study** of the device itself. If you hold the rights and want it
  removed, open an issue.
- `chiconws-v20.bin` is a **derivative** of the official rootfs (same kernel, same
  partitions), with the changes documented in [`../docs/firmware.md`](../docs/firmware.md).
- Neither file contains personal data: they are factory-state firmware images.
