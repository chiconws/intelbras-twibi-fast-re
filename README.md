# Intelbras Twibi Fast — reverse engineering & custom firmware

**English** | [Português](README.pt-BR.md)

Mesh router **Intelbras Twibi Fast** (OEM **Tenda**, **Realtek RTL8197F** platform):
reverse engineering of the stock firmware, recovery of a bricked unit, and a custom
firmware with SSH, no cloud, and per-IP-range internet control.

> ⚠️ Personal, educational project done **on my own device** (a sacrificial unit). Not
> affiliated with Intelbras or Tenda. Flashing firmware **voids the warranty** and can
> brick the device — if you repeat any of this, you do it at your own risk.

---

## TL;DR

- The Twibi Fast is an **RTL8197F + RTL8812BRH**, 8 MB flash, 64 MB DDR2, Linux 3.10.90.
- One unit stopped booting (`rootfs checksum error`) — it was a **truncated rootfs**
  from an interrupted update.
- I recovered it through the **UART** (115200) + the bootloader's **disaster mode** + **TFTP**.
- I reverse engineered the **rootfs checksum** the bootloader validates (a 16-bit sum).
- I built a **custom firmware** (`chiconws`) keeping the stock kernel: SSH instead of
  telnet, no cloud/TR-069, custom branding, an IoT IP range with internet on/off, a web
  page and a JSON API.

---

## First things first: what UART and the FTDI232 are

**UART** is the device's "serial port" — a **text console** that exists from the very
first program (the bootloader), before any network or operating system. Instead of a
keyboard and monitor, you wire **three wires** (GND, TX, RX) to an adapter on your PC and
start seeing and typing what the router sees during boot. It is what saved this device:
with a corrupted flash, it was the only channel still responding.

**FTDI232** (chip **FT232RL**) is the **USB → serial adapter**: the PC side plugs into USB
(shows up as `/dev/ttyUSB0`), the other side has three pins that go to the board pads. It
is sold as "FTDI FT232RL adapter" (the modules with a **3.3 V / 5 V** jumper). It does
**not** power the board: the Twibi uses its own 9 V supply; the adapter only carries the
signals.

<p align="center">
  <img src="images/uart-pads.jpg" width="360" alt="UART pads on the board">
</p>

| Board pad | Signal | Goes to the adapter |
|---|---|---|
| 1 | GND | GND (connect **first**) |
| 2 | RX (input) | adapter TX |
| 3 | VCC 3.3 V | **nothing** |
| 4 | TX (output) | adapter RX |

Details: adapter set to **3.3 V**, console at **115200 8N1**, `TX ↔ RX` crossed and a
common GND. Any serial terminal works (PuTTY, `picocom`, `minicom`, `screen`) — and this
repo includes a Python one (see the full project's `tools/`).

## Quick glossary

| Term | What it is |
|---|---|
| **UART** | the board's serial console (text, 3 wires) |
| **FTDI232** | USB ↔ serial adapter used to talk to the UART |
| **TFTP** | simple file-transfer protocol (UDP); the bootloader listens on `192.168.1.6` |
| **Bootloader** | first program in flash: inits RAM, loads the kernel, has the recovery mode |
| **uImage** | 64-byte header that wraps the firmware image |
| **squashfs** | compressed, read-only filesystem used by the rootfs |
| **rootfs** | the Linux "root": all files of the firmware |
| **checksum** | verification sum the bootloader uses to validate the rootfs |
| **CFM** | persistent configuration partition of the firmware (`key=value` entries) |

---

## Hardware

| Item | Detail |
|---|---|
| SoC | Realtek **RTL8197FNT** — MIPS 24Kc @ 600 MHz, 64 MB DDR2 **in-package** |
| 5 GHz | **RTL8812BRH** (802.11ac 2×2) |
| 2.4 GHz | radio integrated into the RTL8197F |
| Flash | 8 MB SPI (BOYAMICRO/BOHONG **BH25Q64**) |
| Ethernet | 2× 100 Mbps (one port is auto WAN/LAN) |
| Power | 9 V / 1 A, **center positive** |

<p align="center">
  <img src="images/board.jpg" width="520" alt="Twibi Fast board">
</p>

SoC and 5 GHz radio photos: [`images/soc-rtl8197fnt.jpg`](images/soc-rtl8197fnt.jpg),
[`images/soc-rtl8812brh.jpg`](images/soc-rtl8812brh.jpg).

---

## The bricked unit and the recovery

Symptoms: LED steady on, network link up but **RX = 0** (not transmitting), no DHCP, no
SSID, reset button doing nothing.

The UART showed the cause:

```
Booting...
DRAM Type: DDR2, 533MHz, Size: 64MB
found BH25Q64, size=8MB
Boot release version:247 (May 11 2018) (600MHz)
wait for upgrage
rootfs checksum error at 0021D012!
<RealTek>
```

The device had a **truncated rootfs** (only ~256 KB of 3.4 MB written) — the bootloader
ran fine, but refused the rootfs and stopped at its prompt.

### UART

2×2 connector on the board. The actual order (found by continuity tests and trial):

<p align="center">
  <img src="images/uart-pinout.jpg" width="420" alt="UART pads">
</p>

| Pad | Signal |
|---|---|
| 1 | **GND** |
| 2 | **RX** (board input — goes to adapter TX) |
| 3 | **VCC 3.3 V** — **do not connect** |
| 4 | **TX** (board output — goes to adapter RX) |

Console at `115200 8N1`. The adapter must be at **3.3 V**; **never** connect its VCC to
pad 3.

### Disaster mode + TFTP (over the Ethernet cable)

First of all: **the UART is just the console** — that is how you see the boot and type
commands. The **firmware image does not travel over UART**: it is sent over the **network
cable** using TFTP (the bootloader starts a TFTP server on `192.168.1.6` and you push the
file from the PC). Two separate channels: UART to watch/diagnose, Ethernet to transfer.

Holding reset **while powering on** makes the bootloader enter recovery mode
(`Entry disaster mode`) and start a **TFTP server on `192.168.1.6`**. Sending the image
without the uImage header (6,378,516 bytes), it validates and flashes by itself:

```
Linux kernel (root-fs) upgrade.
checksum Ok !
burn kernel-fs Addr:0x00030000 ...
squashfs upgrade. checksum Ok !
burn rootfs ...
reboot.......
```

Full procedure: [`docs/recovery.md`](docs/recovery.md).

---

## The rootfs checksum (decrypted)

The bootloader validates the rootfs with a simple sum, found by decompiling its second
stage:

```
len = bswap32(*(u32 *)(rootfs + 8)) + 0x282;
sum = 0;
for (i = 0; i < len; i += 2)
    sum += bswap16(*(u16 *)(rootfs + i));
if (sum != 0) -> "rootfs checksum error"
```

In other words: a **16-bit big-endian sum that must be zero**; the last 2 bytes are the
complement. The field at `squashfs+8` holds `total_size - 0x282`.

[`tools/mkimage_twibi.py`](tools/mkimage_twibi.py) recomputes it and produces an image the
bootloader accepts — the round-trip against the official image is byte-for-byte identical.

---

## The `chiconws` firmware

A custom firmware built on top of the stock rootfs (same kernel, same partition):

| Feature | Stock | `chiconws` |
|---|---|---|
| Remote access | telnet (plaintext) | **SSH** (static dropbear) |
| Tenda cloud (`ucloud`) | enabled | removed |
| TR-069 (`cwmpd`) | enabled | removed |
| Daily reboot (03:00) | enabled | disabled |
| Hostname / banner / web | Intelbras | `chiconws` |
| IoT range `192.168.6.200-254` | — | internet **on/off** |
| Web page + JSON API | — | `http://twibi.lan:8080/` |

<p align="center">
  <img src="images/board-bottom.jpg" width="520" alt="Board bottom side">
</p>

Details: [`docs/firmware.md`](docs/firmware.md).

---

## Known limitations

- **No 802.1Q VLANs**: the RTL865x switch does routing/NAT **in hardware** and only knows
  the LAN and the WAN. A separate subnet as a bridge alias only works towards the router
  itself — forwarded traffic dies in the switch. That is why internet control is done by
  **IP range on the LAN itself** (iptables).
- **Temperature**: there is no SoC temperature sensor exposed in Linux. The
  `/proc/wlan0/thermal` (Realtek "thermal meter") is a **relative ADC**, useful for trends,
  not °C.
- **Tailscale on the router**: not viable (44 MB RAM, ~1.4 MB free in the rootfs, no
  `/dev/net/tun`). The way is to use a Raspberry Pi as a subnet router.

---

## Firmwares

The images are in [`firmware/`](firmware/):

- **`twibi_fast_1.1.11.bin`** — official (Intelbras) firmware, to restore factory state
- **`chiconws-v20.bin`** — the custom firmware from this project

Flashing is done via **disaster mode + TFTP**, sending the image **without the 64-byte
uImage header** (`firmware/README.md` shows the command). Details in
[`docs/recovery.md`](docs/recovery.md).

## Repository layout

```
docs/
  recovery.md    recovery (UART, disaster mode, TFTP, checksum)
  firmware.md    how chiconws was built and flashed
  hardware.md    board, chips, pinouts, power
tools/
  mkimage_twibi.py   builds the image with the correct checksum
  tftp_put.py        sends the image in disaster mode
  unpack_kernel.py   extracts the kernel from the cr6c container
images/          board, UART and flash photos
firmware/        .bin images (official and chiconws) + instructions
```

## Tools used

Ghidra (bootloader and firmware decompilation), binwalk/unsquashfs, U-Boot `mkimage` (as
a reference), musl-cross (static builds of dropbear and the web server), tftpy and a 3.3 V
FTDI adapter.

## Credits

Project carried out with the help of **DeepSeek** — firmware reverse engineering, device
recovery, custom firmware development and this documentation.

## License

MIT — see [`LICENSE`](LICENSE).
