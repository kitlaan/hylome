# hylome

**hylome** (hy-lohm): hyle, Greek for matter, + -ome as in genome —
an open library of material fingerprints.

This repo documents the reverse-engineered BLE protocol of the
[Vispek "Magic Pencil"](https://www.vispec.com) (model NT-BL-G1), a
pocket NIR reflectance sensor sold as a food/material identifier,
and publishes a starter fingerprint library captured with it.

The device is a 22-channel reflectance sensor with an internal
lamp. The vendor's app drives it over Bluetooth and sends the raw
readings to a cloud classifier; no protocol was ever published, so
outside the vendor's app the hardware was unusable. This repo fixes
that: with the protocol below, you can drive the pencil from any
BLE stack, capture raw scans, build your own labeled library, and
classify new scans locally — no cloud, no account, no vendor
dependency.

## Read this first

**This is a fingerprint sensor, not a spectrometer.** One scan
returns 44 values: 22 channel readings plus 22 internal-reference
readings. Only a handful of channels map cleanly to wavelength
(405 nm, ~625 nm, 940 nm, and a NIR family at 800-900 nm); the
rest are leak-heavy. The 44 values work well as a *fingerprint* for
nearest-neighbor matching against a labeled library (96%
leave-one-repeat-out on ours) and poorly as a *spectrum* for
physical interpretation. See [FINDINGS.md](FINDINGS.md) before
building anything on top of this data — especially the
pigment-vs-polymer result (cross-color polymer ID does not work in
this band) and the positioning rules (contact-only geometry;
sample/reference ratios, not raw counts).

## How this was made: agentic reverse engineering

No protocol docs existed, so an AI agent reconstructed one:

1. **Decompiled the vendor Android app** (v1.0.5) and read the
   vendor SDK's Bluetooth stack to extract the frame format, CRC,
   command table, and response parsers. The decompiled
   app itself is not distributed here — it is the vendor's
   copyrighted work.
2. **Probed the device over BLE** with a generic GATT recon tool
   ([scripts/ble_recon.py](scripts/ble_recon.py)) to confirm the
   transport and map services.
3. **Ran live verification sessions**: info queries, full scan
   exchanges, heartbeat behavior, command-space probes — every
   protocol claim in PROTOCOL.md is verified live, and PROTOCOL.md
   transcribes a real example exchange as wire-format ground
   truth.
4. **Characterized the instrument** (noise, drift, geometry,
   wavelength anchors) and built a reference library, then measured
   what the sensor can and cannot identify
   ([FINDINGS.md](FINDINGS.md)).

The device rules in [AGENTS.md](AGENTS.md) are the hard-won
operational learnings (idle links drop, connect retries, charging
instability, forbidden commands). Respect them; they were learned
the long way.

## Contents

| Path | What it is |
|---|---|
| [PROTOCOL.md](PROTOCOL.md) | The BLE protocol, verified live |
| [FINDINGS.md](FINDINGS.md) | What the sensor can and cannot do; how to build a library |
| [LITERATURE.md](LITERATURE.md) | The papers behind the method |
| [captures/](captures/) | The fingerprint library and instrument data — see [captures/README.md](captures/README.md) for the layout, columns, and use rules |
| [scripts/](scripts/) | Talk the protocol; analyze scans; match against the library |
| [web/](web/) | A one-file browser page: connect and scan from Chrome, download the CSV |
| [AGENTS.md](AGENTS.md) | Device rules and repo hygiene, for agents and humans |

## Quickstart

```sh
pip install bleak                     # Linux/BlueZ, bleak 2.x

# find the pencil (power it on: hold the button ~2 s), query info
python3 scripts/vispek_client.py

# run one scan (fires the lamp; hold the tip flat on the target)
python3 scripts/vispek_client.py --scan

# identify that scan against the published library
python3 scripts/match.py identify your-scan.csv

# re-derive the published accuracy numbers from the data
python3 scripts/match.py report

# per-channel view of any published scan
python3 scripts/analyze.py --list
python3 scripts/analyze.py --scan exploratory-cap
```

Or scan from the browser: serve the repo over HTTPS (or localhost)
and open `web/scan.html` in Chrome — connect, scan, download the
same-format CSV, and feed it to `match.py identify`. No install,
no build step, no offline machinery: the page is one file.

Safety notes: the scan lamp fires on every 0x11 command. Some
commands are forbidden or dangerous (0x12 calibration, 0x24 PWM,
the DFU service; 0x23 drops the link) — see PROTOCOL.md. All
device-handling rules are in AGENTS.md.

## Legal

The Magic Pencil hardware, firmware, mobile app, cloud service,
and the "Vispek" name and marks are property of Vispek. This repo
is independent protocol documentation for interoperability, plus
our own measurements of our own device. No vendor code, app
payloads, or decompiled material is included. The protocol facts
here were verified live and are published so others can use the
hardware they own with the software they choose.

The code, documentation, and capture data **authored for this
repo** are dedicated to the public domain worldwide via
CC0 1.0 (see [LICENSE](LICENSE)) — no attribution required,
credit appreciated. Use the device and this software at your own
risk; the lamp fires on scans, and the forbidden commands list
exists because some frames have unknown or destructive semantics.
