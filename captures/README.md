# Captures

Every published scan from the reverse-engineered sessions,
merged into one row per scan, one CSV per material (the
fingerprint library) plus one for instrument and exploratory
scans. All scans are from a single device unit (pseudonym
`hylome-unit-1`, model NT-BL-G1); device-to-device variation is
unmeasured.

Every label comes from the object itself — recycling codes,
carton labels, printed content — never from a classifier's
guess. The 44 values per scan are the device readings as
reported, never recomputed.

## Files

| File | Contents |
|---|---|
| `lib-paper.csv` | paper products: office papers, sticky notes, kraft, cardboard, Astrobrights, facial tissues |
| `lib-plastics.csv` | polymers: PLA, PETG, TPU, HDPE, PP, PS, PEI, and unknown-plastic items — rows grouped by material, so all PLA scans sit adjacent, then all PETG, etc. |
| `lib-fabric.csv` | cotton: t-shirt, denim |
| `lib-wood.csv` | plywood, popsicle stick |
| `lib-metal.csv` | aluminum foil, steel putty knife |
| `lib-household.csv` | masking tapes |
| `instrument.csv` | 66 scans that document the instrument/protocol, not materials: noise groups, geometry, wavelength line-sources, drift bookends, scene/mode probes, the four exploratory first runs |
| `continuous-0x34.csv` | the 0x34 continuous-mode time series (2080 values per list, 20 channels, identity unknown) |
| `report-characterization.md` | computed noise/drift/geometry tables from the characterization session |

Only the `lib-*.csv` files are reference data — labeled
objects, 3+ repeats each — and only they belong in a matcher's
training data. instrument.csv documents how the device
behaves, and includes the four `exploratory-*` first scans
(uncontrolled geometry, single scans — working notes, not
characterization). See FINDINGS.md for what a match means.

## Column dictionary

Both scan schemas carry a few label fields with one job each,
plus the 44 raw values. The library files (`lib-*.csv`):

| Column | Meaning |
|---|---|
| `material` | normalized material family, every row; `unknown` marks a polymer that is not established — never guessed |
| `item` | the object's complete physical identity — form, color, brand when it identifies the object, and verified facts with their source in parentheses (`milk jug wall (recycling code 2)`) — written so the object can be picked out of a drawer. No polymer words; `material` carries them. The matcher's key together with `material` |
| `sample_00..21`, `reference_00..21` | the 44 raw 24-bit counts — the fingerprint |

Physical traits that change the fingerprint — texture, thickness,
color, preparation — are part of `item`, not stray metadata: in a
fingerprint library the physical instantiation is the identity.
A property column can be added when regression targets exist (fat
%, ABV); none are published.

instrument.csv documents the device instead of materials:

| Column | Meaning |
|---|---|
| `scan` | row id: the experiment as a groupable prefix plus condition and repeat — `noise-dark-03`, `geometry-gap-5mm`, `wavelength-laser405-1`, `scene-2`, `param-count-511`, `bookend-dark`, `drift-white-start`, or an `exploratory-*` slug. The ids state the geometry, command parameters, and light sources; the columns that carried them derivably are gone. A trailing `-2`, `-3`, … marks a repeat of a condition (`bookend-dark-2..5`, the `wavelength-screen-*-2` re-runs) |
| `item` | the target object or light source — the authority when a historical id misleads: the `laser940` scans used a Flipper Zero IR LED, and the `laser532` and `screen-*` scans used dimmed XIAO RGB LEDs |
| `sample_*`, `reference_*` | as above |

The library's printer-paper scans are the same paper stack as the
instrument session's white-paper scans.
