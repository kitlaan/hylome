# Findings — what the sensor can and cannot do

Measured results from the captures in this repo, plus the rules we
would hand to anyone building their own fingerprint library. The
headline numbers re-derive from the published data:
`python3 scripts/match.py report` reproduces every accuracy figure
in sections 2-4 below.

## Contents

- [The instrument](#the-instrument)
- [The metric](#the-metric)
- [Identification works](#identification-works)
- [Near-neighbor confusions](#near-neighbor-confusions)
- [Pigment vs polymer: the PLA/PETG case](#pigment-vs-polymer-the-plapetg-case)
- [The paper family](#the-paper-family)
- [Capture paths: bench vs phone](#capture-paths-bench-vs-phone)
- [Building your own library](#building-your-own-library)
- [Limits](#limits)

## The instrument

The Magic Pencil is a 22-channel reflectance sensor, not a
spectrometer. One scan returns 22 sample values plus 22 reference
values (44 raw 24-bit counts); the sample/reference ratio per
channel is the drift-immune quantity. The clean wavelength anchors:
ch 2 = 405 nm, ch 0-1 = the 940 nm band, ch 16-21 = the NIR family
(SCiO's 740-1070 nm band), ch 5 = ~625 nm. Everything between is
leak-heavy: each visible color smears ~1% differentials across most
of the array. Treat the 44 values as a fingerprint for matching, not
a spectrum for interpretation. Cross-referencing against published
spectra is only meaningful on the clean channels.

Measured instrument behavior (computed tables in
captures/report-characterization.md):

- Noise: worst-channel CV 0.30% over 10-scan groups. One scan
  carries almost the full information of an average.
- Drift: raw counts fall ~1.1% per session; the ratio drifts 0.35%,
  inside noise. Use ratios.
- Geometry: contact-only. A 5 mm gap cuts the signal 83%, 10 mm
  93%, a 15-degree tilt 80%.
- Contact validation: hand-held contact matches a printed jig to a
  0.09% mean (max 0.44%), inside the noise floor.

## The metric

Euclidean distance over the 22 raw log sample/reference ratios,
unstandardized:

- All 22 channels, raw: the metric. Leave-one-repeat-out top-1 is
  **96% (127/132)** over the published library.
- z-scoring the channels hurts: **91%**. Do not standardize.
- The "clean" set (ch 2 + 16-21) alone scores **86%** — the leaky
  mid-visible carries most of the discrimination. The clean set is
  for noise and drift interpretation, not for matching.
- The mid-visible alone scores ~97% in our runs, but it has no
  physical meaning as a band; all-22 is the defensible default.

## Identification works

Leave-one-repeat-out over the published library (132 scans, 37
objects): a repeat finds its own object 96% of the time. Every miss
is a near-neighbor pair, not a failure of the method — the same
objects confuse in every run (see below). The vendor's own cloud
service, asked the same objects, landed 1-2 of 11 in our one
recorded round: every black plastic (PETG x2, PLA) came back "PC",
both pigmented filaments were hijacked (lime PLA -> "PVC", orange
PETG -> "PP"), transparent TPU -> "ABS", white HDPE -> "PC". Only
the PP yogurt tub answered PP. Notable: black PETG answered PC in
both forms (printed and spool), so the vendor model is consistent
within a polymer+color and wrong for the same reason — its taxonomy
is consumer packaging, and 3D-printing polymers sit outside it.
A local library with honest per-object labels beats it on this
universe. That comparison is the recorded evidence for this repo
existing at all.

## Near-neighbor confusions

The confusions are physically sensible and they mark the danger
zones of a fingerprint library:

- kraft paper <-> cardboard (recycled pulp near-twins) — the most
  repeat offender; every paper-family miss is this one pair, at
  1-2x the repeat-noise distance.
- denim <-> cotton (indigo-dyed twill vs knit, both cotton).
- HDPE <-> PP (polyolefins), HDPE <-> transparent PETG.
- black plastics with black plastics (carbon black dominates the
  return), transparents with transparents.
- Same-color type pairs DO separate: two nominally-white office
  papers at 10x the repeat noise; sticky note vs Astrobrights
  yellow at 17x.

The library treats these pairs as known near-neighbors: matching
across them needs cross-session coverage, not a threshold tweak.

## Pigment vs polymer: the PLA/PETG case

Identification and generalization are different problems, and this
sensor splits them sharply. Measured on the filament family
(lib-plastics.csv):

- Same-pigment polymer pairs separate cleanly: black PETG printed
  vs black PETG spool at 0.06; black PETG vs black PLA at 0.36 —
  6x the repeat noise. Orange PETG sits 3+ from everything; pigment
  dominates the first axis.
- The polymer axis does NOT survive the pigment axis: across
  non-black PLA/PETG classes, the between-polymer distance is 0.9x
  the within-polymer distance; leave-color-out PLA-vs-PETG calls
  score 6/18, at chance. At 405-1070 nm the weak third/fourth-
  overtone polymer signal is swamped by pigment variance.

Consequences: exact-object entries and same-color reference pairs
are the valuable data. A mystery part needs a same-color reference
before its polymer can be named. Cross-color polymer ID is the one
thing this band cannot do — it needs the 1700-2500 nm overtone
region (InGaAs detectors). Nothing in this band's modeling
substitutes for it.

## The paper family

Paper identifies AND partially generalizes: paper-only
leave-one-repeat-out is 42/45 (93%), every miss the kraft/cardboard
pair. Unlike polymers, the type axis at matched color (two office
papers, sticky vs Astrobrights) is comparable in magnitude to the
color axis, so both identification and partial generalization work.
Color still dominates paper fingerprints (0.125-0.199 within the
Astrobrights line across colors).

## Capture paths: bench vs phone

The same objects scanned from the bench (Python/bleak) and from a
phone (Web Bluetooth) measure 5-40x the repeat-noise scale apart
(median repeat d = 0.001; cross-path d = 0.005-0.043). Distinct
materials still match across paths (white paper: cross 0.005 vs
next-best 0.058); near-neighbors do not (kraft/cardboard cross).
One caveat is baked into that number: same object was not same
surface spot, so spot variance and capture-path offset are not yet
separated. Either way, the library must hold each object's own
spread, cross-path entries included, and match against that spread.

## Building your own library

Everything above compresses into these rules:

1. **One device per library.** Device-to-device variation is
   unmeasured. Record the device id with every scan; never silently
   merge two units' data. (Our published scans carry the pseudonym
   `hylome-unit-1`.)
2. **Contact, every scan.** Hold the window flat on the target
   (the donut ring is the contact plane). A fixed jig is better;
   hand-held contact validated within 0.09% of jig contact here.
   Contact also seals the window against the target, so room
   light cannot reach the detector.
3. **Store raw counts, compute ratios.** The ratio kills lamp drift;
   raw counts are the fingerprint. Never discard the reference
   values.
4. **3+ repeats per object, same spot.** They give the per-object
   spread, which the reject decision needs. Single scans carry
   nearly full information for matching, but a library without
   spreads cannot say "unknown".
5. **Label honestly, from the object.** Recycling codes, carton
   labels, printed percentages. Never promote a vendor app's
   classification to ground truth. Label what you know; leave the
   rest empty rather than guessed.
6. **Same-color reference pairs are the valuable data.** Pigment
   dominates the fingerprint; a same-color pair isolates the type
   axis. Cross-color polymer ID will not work in this band.
7. **Prefer flat, matte, opaque targets.** Gloss bounces the lamp
   (the OLED screens failed as color anchors for this reason);
   transparents and thin films read the backing too; NIR-transparent
   blacks leak the surface below. Check unknown dark materials for
   NIR transparency with an IR remote and a phone camera.
8. **Liquids: barrier, never a dip.** The window seal is unknown.
   Pour into a thin LDPE bag, 5-10 mm bubble-free layer on white
   paper, and scan the empty barrier once as the vessel reference.
9. **Bookend sessions.** One dark (cap-on) and one white scan at
   session start; one white at the end as the drift check.
10. **Answer with a reject option.** A nearest neighbor always
    answers; a confident wrong answer costs more than "unknown".
    Match with the raw all-22 log-ratio distance and reject
    beyond what the library's own spreads justify. Our measured
    bands: same-object repeats 0.001-0.006; same-object cross-path
    0.005-0.043; near-twin materials 0.005-0.015; same-color type
    pairs 0.06-0.10; distinct classes 0.02-0.2+. `match.py
    identify` ships with 0.05 as the reject line and prints each
    candidate's own spread beside the distance.
11. **Grow by repeats and PRs, not by clever math.** Published
    models in this field use dozens to hundreds of samples per
    class (LITERATURE.md). Library size is the long game.

The starter loop: capture with `scripts/vispek_client.py --scan`,
identify with `scripts/match.py identify <scan.csv>`, and when the
answer is UNKNOWN, add the object (3+ repeats, honest label) to the
matching material file.

## Limits

- Device-to-device variation: unmeasured. Byte-4 codes and channel
  gains may differ per unit.
- Cross-path threshold: the spot-vs-path experiment (two marked
  spots on each near-twin object, both scanned on both paths) is
  still open; until it runs, cross-path near-neighbor answers stay
  untrusted.
- Channel identity: only ch 2 (405 nm), ch 5 (~625 nm), ch 0-1
  (940 nm) and ch 16-21 (NIR family) are anchored; the rest are
  leak-heavy and unlabelled by wavelength.
- The 0x34 continuous mode's 20 channels: identity and stop
  semantics unknown (PROTOCOL.md).
- The library is 132 target scans / 37 objects from one device,
  one household and one filament shop. It is a seed and a proof,
  not a coverage claim.
