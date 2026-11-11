# hylome — agent notes

This is the public repo: the reverse-engineered BLE protocol for
the Vispek Magic Pencil (NT-BL-G1), a starter fingerprint library,
and the clients that talk to the device (scripts/vispek_client.py
on the bench, web/scan.html in the browser). Everything here is
meant for reuse. Read PROTOCOL.md and FINDINGS.md before any
device or protocol work; read captures/README.md before touching
data. The device rules below apply to every client alike.

## Environment facts

- Linux, BlueZ, Python 3.10+, bleak 2.x.
- bleak 2.0: `client.is_connected` is a property, not a method.
- The pencil advertises a name starting with `VSPK` (`VSPK02...`
  on newer units). There is no public address to hard-code; find
  it by name prefix.

## Device rules

These rules came from the reverse-engineering sessions. Follow
them; do not relearn them the hard way.

- Do not run sessions while the device charges. Charging makes BLE
  unstable: connects fail or the link drops on first write.
- The device powers off about 2 minutes after a BLE disconnect.
  Hold the button about 2 seconds to wake it.
- The only button is power. It never triggers a scan.
- The 0x23 temperature query makes the device drop the link. Do
  not send it.
- Connects fail at random. Retry with a FRESH BleakClient object
  per attempt; reusing a failed client breaks the next connect
  on it.
- BlueZ evicts the device object once discovery stops. When
  connects report "not found", re-scan for the device.
- The device drops links that sit idle for tens of seconds. Send
  the heartbeat frame (see vispek_client.heartbeat()) about every
  3 s for the whole session.
- Lamp runs drain the battery 1-2 percent per minute. Run scans
  off the charger, charge between sessions.
- Subscribe to the Nordic UART notify characteristic only
  (6e400003). Leave the DFU characteristic alone.

## Forbidden

- 0x12 calibration command: unknown semantics. It may overwrite
  device calibration state. Never send it without prior research.
- DFU service (0000fe59, characteristic
  8ec90003-f315-4f60-9fb8-838830daea50): never subscribe, never
  write.
- 0x24 PWM: not understood yet. Do not use.
- 0x23 temperature: drops the link (see device rules).

## Data discipline

- The `lib-*.csv` files are the reference library; instrument.csv
  holds the instrument, bookend, and exploratory scans. Never use
  instrument.csv rows as calibration or library truth.
- The engine reads only material + item as the class key.
  Everything else is context. No property column is published; add
  one when you collect regression targets (fat %, ABV) — that is
  the job it was designed for.
- Label from the object itself (recycling codes, carton labels,
  printed percentages). A vendor app's classification is never
  ground truth; it is weak evidence at best.
- All published captures are from one device unit (pseudonym
  `hylome-unit-1`). Never merge scans from a second device into
  the same library; device-to-device variation is unmeasured.
- New library scans: 3+ repeats, same spot, contact geometry,
  raw counts recorded as-is. See FINDINGS.md, "Building your own
  library".

## Publication hygiene

This repo is public. Before committing:

- `captures/` holds published data only. The clients write local
  runs to `runs/` (gitignored); never point them at `captures/`.
- Never add the device serial, BLE address, account emails,
  cloud credentials, or auth tokens to any file. The published
  captures use the device pseudonym `hylome-unit-1`; keep it
  that way.
- Grep the tree for identifier fragments before committing when
  in doubt (serial prefixes, MAC addresses, `eyJ` JWT prefixes).
- Raw frame transcripts are not published. The one exchange
  printed in PROTOCOL.md was hand-checked; treat any future
  transcript excerpt the same way before it lands.
