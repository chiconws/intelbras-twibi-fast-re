# VLANs on the internal switch

**English** | [Português](vlan.pt-BR.md)

Short version: the RTL865x switch **can** tag and bridge VLANs, but the driver only
exposes part of it. Tagged and untagged clients work **if** the LAN interface is a VLAN
device (`eth0.9`) instead of `eth0`. What does **not** work: a trunk on the LAN port, a
VLAN per MAC, and per-client L2 isolation.

## Where the control lives

```
/proc/net/vlan/vlanEnable     global: "vlan enable:%x hw support enable:%d"
/proc/net/vlan/pvid           per-port PVID (ASIC) and per-netdev (wlan VAPs)
/proc/net/vlan/groupIndex     VID being configured (cursor)
/proc/net/vlan/vlanGroup      VLAN table: <vid>, <member mask>, <tagged mask>, <type>
/proc/net/vlan/wanVlanId      WAN VID used by NAT (8)
/proc/net/vlan/hwNatLanVid    LAN VID used by hw NAT (9)
/proc/rtl865x/vlan            ASIC VLAN table dump
/proc/rtl865x/pvid            ASIC PVID dump
```

They look read-only (`-r--r--r--`), but **root can write** through
`CAP_DAC_OVERRIDE`; the handlers are real.

## Formats (verified on hardware)

```sh
echo "1 1" > /proc/net/vlan/vlanEnable     # enable + hw support (space, not comma)
echo "0 0" > /proc/net/vlan/vlanEnable     # disable
echo "9,20,9,9,9" > /proc/net/vlan/pvid    # PVID for ports 0..4 (ASIC)
echo 10 > /proc/net/vlan/groupIndex        # the VID being configured
echo "1,<members>,<tagged>,10,0" > /proc/net/vlan/vlanGroup
```

`vlanGroup` uses `%d,%x,%x,%d,%d`: field 1 is the enable, field 2 the **member mask**,
field 3 the **tagged mask**, field 4 the **VID** (must equal `groupIndex`) and field 5 a
flag. The handler adds the CPU port (8) by itself.

## The bridge architecture (the part that matters)

With VLAN mode on, the switch hands frames to Linux **tagged**. Bridging the raw `eth0`
then drops everything (the bridge is not VLAN-aware in 3.10). The OEM already does it the
right way (`default.cfg`: `lan_ifnames=vlan1 wlan0 wlan1`):

```sh
vconfig add eth0 9
ifconfig eth0.9 up
brctl delif br0 eth0
brctl addif br0 eth0.9
```

After that, untagged clients work normally and `br0` keeps `eth0.9 wlan0 wlan-msh wlan1`.

Symptoms when the bridge is wrong: `eth0` counters grow, the bridge drops everything;
with VLAN mode off, `vlanGroup` writes print `rtk 11q vlan support not enabled!!!`.

## Limits found

- **Port 0 (the LAN port) cannot join another VLAN.** A fresh VID with port 0 as member
  is not created in the ASIC table (tested with VID 60). Port 1 (WAN) accepts it.
- **No MAC-based VLAN**: the ACL dump exposes only `permit`, `to cpu`, `mirror`, `deny`,
  `redirect to ether/pppoe` — there is no VLAN action.
- **No bridge VLAN filtering** (kernel 3.10) and **no ebtables** (not in the kernel).
- Per-client L2 isolation is therefore **not possible** on this firmware; the alternative
  is L3 grouping (blocking by MAC, which is what Twibify does).

## Useful symbols

```
vlan_group_write       0x804558dc   /proc/net/vlan/vlanGroup handler
vlan_pvid_write        0x804556ac   pvid handler
vlan_ctl_single_write  0x8045550c   vlanEnable handler
rtk_add_eth_vlan       0x8017b544   applies a VLAN (hw-support path)
rtl865x_addVlan        0x8018ff24
rtl865x_addVlanPortMember 0x8018fbb4
rtl865x_setVlanPortTag    0x8018fa04
rtl865x_setVlanFilterDatabase 0x8018f948
```

Everything is **runtime only**: a reboot restores VID 8/9, `vlanEnable=0` and PVID
`9,8,9,9,9`.
