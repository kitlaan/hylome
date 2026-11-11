# Vispek Magic Pencil — BLE Protocol

> Verified against live hardware. Every frame format and command
> below was exercised on a real device; [Data streams](#data-streams)
> transcribes a complete exchange.

This spec was established by reverse-engineering the vendor's
Android app and verified against live hardware; the method is in
README.md. No vendor code is distributed here.

## Contents

- [Transport](#transport)
- [Command frame format](#command-frame-format)
- [CRC-8](#crc-8)
- [Command table](#command-table)
- [Response frames](#response-frames)
- [Data streams](#data-streams)
- [Byte-4 integrity codes](#byte-4-integrity-codes)
- [Quirks](#quirks)
- [Device behavior](#device-behavior)
- [Tip optics](#tip-optics)
- [App orchestration](#app-orchestration)
- [Open questions](#open-questions)

## Transport

Nordic UART Service (NUS), no pairing, no encryption.

| Role | UUID | Use |
|---|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | — |
| RX char | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | App writes commands here |
| TX char | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Device notifies responses here |

Subscribe to the TX characteristic only. The device also exposes a
DFU service (0000fe59) — never subscribe to or write it; see
[Quirks](#quirks).

## Command frame format

Fixed 20 bytes, written to the RX char:

```
byte 0     0x3D ('=') header
byte 1     command code
bytes 2-18 parameters, big-endian fields, zero padded
byte 19    CRC-8 over bytes 0-18
```

## CRC-8

```
crc = 0
for byte b in frame[0:19]:
    crc ^= b
    repeat 8 times:
        crc = (crc << 1) ^ 0x07 if crc & 0x80 else (crc << 1)
        crc &= 0xFF
```

Poly 0x07, init 0x00, no reflection, no final xor (CRC-8/SMBus-style).
A Dallas/Maxim-style CRC-8 (poly 0x31) appears unused for commands;
it is the candidate for the checksum-like tail byte of `5a34`
packets (see [Open questions](#open-questions)).

## Command table

| Byte | Meaning |
|---|---|
| 0x01 | Query battery |
| 0x01 | Heartbeat: same frame, CRC byte forced to 0xAA |
| 0x11 | Start scan (see [scan parameters](#scan-command-parameters)) |
| 0x12 | Start calibration — FORBIDDEN, unknown semantics |
| 0x13 | Remote power-off |
| 0x14 | Lamp control on (`byte3=1`) / off (`byte3=0`); `byte2` = mode |
| 0x15 | Query serial number |
| 0x16 | Query hardware version |
| 0x17 | Query firmware version |
| 0x18 | OTA: begin update, `byte2`=len, `bytes3..`=version |
| 0x19 | OTA: total image length, 4 bytes BE at `bytes2..` |
| 0x20 | OTA: data packet, index 2B BE at `bytes2..`, 14 data bytes at `bytes5..` |
| 0x22 | Query product model |
| 0x23 | Query temperature — DROPS THE LINK, do not send |
| 0x24 | Set PWM — not understood, do not send |
| 0x33 | Periodic scan, see below |
| 0x34 | Continuous scan, see below |

Scan variants (byte 0x11):

- Old devices (name not starting with `VSPK02`):
  `byte2=23, byte3=100, byte4=1`
- VSPK02 devices (the newer units):
  `byte2=23`, `bytes3-4 = 0x03FF` (1023, BE), `byte5 = n` (scene id)
- Simple preset scan: `byte2=mode, byte4=2`

Heart-rate scan 0x33:
`byte2=p1`, `bytes3-4=1023` BE, `byte5=2`, `bytes6-7=p2*1000` BE (period in ms).

Continuous scan 0x34:
`byte2=b (0/1)`, `byte3=p2`, `bytes4-5=1023` BE, `byte6=p3`, `bytes7-8=1023` BE,
`byte9=2`.

### Scan command parameters

The three parameter fields of the 0x11 scan command, measured live:

- **`byte2` selects the response mode**: 23 returns the full
  22-channel scan; 10 and 15 each return a single (sample,
  reference) pair — the quick-read mode the app's blood test uses.
  Observed against the same white-paper target: mode 10 returned
  sample 2363208 / reference 2987776, mode 15 returned
  2443334 / 3044383.
- **The count field (`bytes3-4`) is ignored**: 511, 1023, and 2047
  all return identical 22-row scans.
- **The scene byte (`byte5`) changes per-channel exposure or lamp
  grouping**: scene 1 is the normal scan; scene 2 boosts the early
  channels, scene 3 crushes them, scene 4 zeroes them.

The meaning of the 23 and 1023 defaults is open (see
[Open questions](#open-questions)).

## Response frames

Device notifications on the TX char. Header `0x5A`. Offsets below
are byte positions in the notify payload.

| Prefix | Meaning | Payload |
|---|---|---|
| `5a01` | Battery | `byte2` = percent |
| `5aff15` | Serial number | `byte3`=len, ASCII from `byte4` |
| `5aff16` | Hardware version | same string layout |
| `5aff17` | Firmware version | same string layout |
| `5aff22` | Product model | same string layout |
| `5aff23` | Temperature | `bytes3-4` BE / 100, in °C |
| `5a11` | Scan data packet | see streams |
| `5aff1102` | Scan stream end | emits accumulated samples |
| `5a33` | Periodic-scan data packet | see streams |
| `5a34` | Continuous-scan data packet | see streams |
| `5aff3401` | Continuous stream begin | reset accumulators |
| `5aff3400` | Continuous stream end | emits accumulated samples |

## Data streams

All sample values are 3 bytes, big-endian.

`5a11` (one-shot scan): packet `byte2` == 1 resets the accumulators.
Each packet appends one sample from `bytes8-10` and one reference value
from `bytes5-7`. `5aff1102` ends the stream.

Observed packet layout, 20 bytes:

```
5a 11 01 00 ff 04 52 75 04 5a d0 00 00 00 00 00 00 00 00 a6
|  |  |  |  |  +--------+ +--------+                      |
|  |  |  |  |  reference  sample, 3 bytes BE each        CRC
|  |  |  |  | byte 4: CONSTANT per channel (see below) --
|  |  |  |  |  usable as a stream integrity check
|  |  |  |  zero in all captures
|  |  channel index, 0x01..0x16 (22 channels)
|  command echo 0x11
header 0x5A
```

One complete scan = `5aff1100` ACK + 22 data packets + `5aff1102`
end marker. Observed value ranges: samples 285k-2.21M, references
283k-2.73M. The sample/reference ratio per channel is the
reflectance estimate; the reference path also sees the target, so
both lists carry target information.

`5a33` (periodic): `bytes5-6` BE = total, `bytes7-8` BE = index,
`bytes9-10` BE = count. Index 1 resets. Samples follow from `byte11`.
When total == count the stream is complete.

`5a34` (continuous): `5aff3401` resets. Each data packet: `byte4` = n,
then n samples from `byte5`, then n reference values up to the last
byte (the final byte is likely a device-side checksum). `5aff3400`
ends the stream. Packets carry 20 channels (not 22); a full
captured run is in captures/continuous-0x34.csv. There is no known
stop command (see [Open questions](#open-questions)).

### Example scan exchange (captured live)

Full session transcripts are not published. This is one real
exchange, start to end marker — the wire ground truth for anyone
writing a parser. The command frame is the VSPK02 scene-1 scan,
complete with its CRC-8 at byte 19:

```
 -> 3d 11 17 03 ff 01 00 00 00 00 00 00 00 00 00 00 00 00 00 dd  scan: byte2=23, count=1023, scene 1
 <- 5a ff 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 06  ACK: scan accepted
 <- 5a 11 01 00 ff 1e e1 10 1f 3f 89 00 00 00 00 00 00 00 00 de  wire ch 0x01 (byte4 = ff)
 <- 5a 11 02 01 13 23 9a 69 23 a6 85 00 00 00 00 00 00 00 00 12  wire ch 0x02 (byte4 = 13)
 <- 5a 11 03 01 72 2b 13 33 26 31 c9 00 00 00 00 00 00 00 00 e4  wire ch 0x03 (byte4 = 72)
 <- 5a 11 04 01 86 25 0a 80 1f da 13 00 00 00 00 00 00 00 00 81  wire ch 0x04 (byte4 = 86)
 ...                                                             wire ch 0x05..0x15
 <- 5a 11 16 06 72 44 70 d4 3f 74 93 00 00 00 00 00 00 00 00 4e  wire ch 0x16 (byte4 = 72)
 <- 5a ff 11 02 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 02  end marker: 22 samples
```

In each data packet the reference value is bytes 5-7 and the
sample is bytes 8-10, both 3 bytes big-endian. Byte 4 carries the
per-channel code from the table below. Wire channel indices run
0x01-0x16; the CSV files and the byte-4 table are 0-based.

## Byte-4 integrity codes

Byte 4 of each `5a11` packet is CONSTANT per channel: one code per
channel, stable across all 2,485 observed packets — through floods,
overload, and every target. Cross-unit stability is UNVERIFIED — a
second unit may carry different codes (factory trim hypothesis);
treat the table as per-unit observed, not universal.

| csv ch | byte4 (hex) | | csv ch | byte4 (hex) |
|---:|---|---|---:|---|
| 0 | ff | | 11 | 43 |
| 1 | 13 | | 12 | 57 |
| 2 | 72 | | 13 | 70 |
| 3 | 86 | | 14 | ac |
| 4 | c7 | | 15 | de |
| 5 | 0d | | 16 | 1a |
| 6 | 3b | | 17 | b0 |
| 7 | 5d | | 18 | 14 |
| 8 | 70 | | 19 | aa |
| 9 | 94 | | 20 | 0e |
| 10 | bc | | 21 | 72 |

Two pairs share a code (8/13 → 70, 2/21 → 72), which argues
against a channel-ID and for gain/trim semantics. A parser can
validate the stream against this table and flag any mismatch as
corrupt.

## Quirks

- The heartbeat frame does not use the computed CRC. Byte 19 is
  forced to 0xAA instead.
- The vendor's battery query ships with a stale CRC byte
  pre-filled, then recomputes it before sending: always compute
  byte 19 yourself, never trust a constant.
- Multi-byte parameters are big-endian (the 1023 count field goes
  out as `03 FF`).
- The device answers plain-text probes with silence. Only 0x3D
  frames get replies.
- The 0x12 calibration command has unknown semantics. It may overwrite
  device calibration state. Never send it without prior research.
- The DFU service (0000fe59, characteristic
  8ec90003-f315-4f60-9fb8-838830daea50): never subscribe, never write.
- 0x24 PWM is not understood. Do not use.
- 0x23 temperature makes the device drop the link. Do not send.

## Device behavior

From the official manual:

- The only button is power: hold 2 s to switch on or off.
- Blinking blue = on and advertising; solid blue = connected.
- Blinking red = charging; steady red or no start = charge needed.
- The device powers off 2 min after BLE disconnects.
- All measurements are app-driven. The button never triggers a scan.

Observed on our unit (NT-BL-G1; BLE names start with VSPK02):

- Do not run scan sessions while the device charges. Charging makes
  the BLE stack unstable: connects fail or the link drops on first
  write. A LOW battery also browns out the radio during connection
  events. Charge between sessions.
- Idle links drop after tens of seconds; back-to-back steps never
  dropped. The heartbeat frame every 3 s holds the link. This is
  likely why a heartbeat exists at all.
- Connects fail at random (BlueZ more than Android Chrome). Retry
  with a FRESH client object per attempt; reusing a failed client
  breaks the next connect on it.
- BlueZ evicts the device object once discovery stops. When connects
  report "not found", re-scan for the device.
- Off charger, battery fell 1-2% per minute during lamp runs.
- After a completed session, the device may drop the link on its
  own; data before the drop is complete.

## Tip optics

The tip is not a cone to a point. Caliper measurements:

- Optical window: 8.8 mm diameter, recessed 0.5 mm below the donut
  face. Sensor die visible at the bottom: gold pads around a small
  square die, what looks like two circular wells (emitters or
  reference elements) and a central detector region.
- Donut: 15.8 mm outer diameter, the raised ring around the window.
- Lip: outside the donut, 1.5 mm wide, sitting 0.7 mm ABOVE the
  donut plane; outer diameter about 18.8 mm. The donut, not the lip,
  is the contact surface.
- Beyond the lip, a lathed circular cone rises to the hex body:
  23.5 mm across flats, a rounded hex; corners at most 27.1 mm
  (sharp-corner bound; the true envelope is smaller).

Consequences:

- The donut is the contact plane in every scan mode, hand-held
  included. Pressed flat, the window floats 0.5 mm above the surface
  and the lip 0.7 mm. "Contact" never means sensor-on-target.
- The window looks along the tip axis. A scan at a controlled gap
  needs the pencil perpendicular over the spot (a printed jig).
- The window is 8.8 mm across, so the field of view is small; scan
  spot placement matters more than scan head orientation.
- The cap contains a magnet, visible inside it. The pencil's tip
  region is therefore ferromagnetic — that is how the cap snaps on.
  Cap-on scans mix plastic transmission with metal reflection, not
  a pure polymer spectrum. Fixture idea: a magnet under the target
  holds the pencil in hands-free contact.

## App orchestration

The vendor app's scan flow — useful as a reference client:

1. Register the response listener, clear accumulators.
2. Send exactly one scan command, chosen by test type:
   - normal test → scene 1
   - two other test modes → scene 3 and scene 4
   - blood test → the 0x33 periodic scan, mode 10, period 5000 ms;
     the app collects TWO scans (the second via mode 15) and joins
     them.
3. The app polls for data and times out after 30 s without any. A
   30 s collection window matches.
4. The app accumulates samples and reference values separately and
   submits both to its classification service. Both lists carry
   information; neither is discarded.

The heartbeat frame (`3d 01 .. aa`) is the idle-link keep-alive
(see [Device behavior](#device-behavior)).

## Open questions

- Meaning of `byte2=23` and the 1023 fields in scan commands (mode?
  channel mask 0x3FF? sample count?).
- The scene id (`byte5`) values beyond 1-4, and what the app picks
  them from.
- Heartbeat period: not fixed by the protocol; 3 s is verified to
  hold the link.
- Whether the `5a34` tail byte is a Dallas/Maxim CRC-8 (poly 0x31).
- How to stop the 0x34 continuous stream cleanly.
- Cross-unit stability of the byte-4 code table.
