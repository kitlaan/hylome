# Literature: pocket NIR sensors and few-channel material ID

Papers verified through Crossref / publisher records; DOIs are
given for every entry. Organized by what each body of work
teaches this project.

## Contents

- [SCiO — the direct ancestor](#scio--the-direct-ancestor)
- [Portable NIR plastics ID](#portable-nir-plastics-id)
- [Food authentication chemometrics](#food-authentication-chemometrics)
- [Few-channel spectral reconstruction](#few-channel-spectral-reconstruction)
- [What this means for us](#what-this-means-for-us)

## SCiO — the direct ancestor

Consumer Physics (Tel Aviv, ~2014): a pocket NIR sensor
(740-1070 nm) whose app sends raw data to a cloud model and shows
a result. The Magic Pencil is the same product shape, and its
usable window (ch 2 = 405 nm; ch 16-21 = the NIR family) covers
the same band. A decade of papers evaluate SCiO exactly the way
this project works: scan known samples, build a local labeled
library, fit a classifier, report accuracy.

- Evaluating the performance of a consumer-scale SCiO molecular
  sensor (produce quality) -- Postharvest Biology and Technology,
  ScienceDirect PII S0925521418302990.
- Performance evaluation of two commercially available portable
  spectrometers (F-750, SCiO), 740-1070 nm -- Agriculture 10(1):148
  (2020), doi:10.3390/agriculture10010148.
- Comparing the performance of miniaturized near-infrared
  spectrometers (SCiO and others; mango quality) -- Food
  Analytical Methods (2023), doi:10.1007/s11694-023-02097-y.
- Use of low-cost near-infrared spectroscopy to predict pasting
  properties of cassava flour -- Scientific Reports (2024),
  doi:10.1038/s41598-024-67299-w.
- Evaluation of a handheld near-infrared spectroscopy sensor
  (crop/forage use) -- doi:10.1002/cft2.20235; companion forage
  dry-matter evaluation doi:10.1002/cft2.20239. The paper's system
  diagram is this project's architecture: sensor + app + cloud.
- A comparative investigation of two handheld near-IR spectrometers
  (SCiO, NIRscan Nano) for textile fibres at crime scenes --
  Vibrational Spectroscopy, ScienceDirect PII S0924203120302095.
- Review of portable near infrared spectrometers: current status
  and new trends -- Applied Spectroscopy Reviews (2021),
  doi:10.1177/09670335211030617.

## Portable NIR plastics ID

Our target list (PET / HDPE / PP / PS / PVC with recycling-code
ground truth) is the standard benchmark set of this field. NIR is
the established industrial sorting technology.

- Discrimination of plastics using a portable near infrared
  spectrometer -- J. Near Infrared Spectroscopy (2002),
  doi:10.1255/jnirs.341.
- Development of a near infrared-based fiber identification
  system for carpet recycling -- JNIRS (1998),
  doi:10.1255/jnirs.205.
- Classification of common household plastic wastes combining
  multiple methods based on near-infrared spectroscopy -- ACS
  ES&T Engineering (2020), doi:10.1021/acsestengg.0c00183.
- Enabling mechanical recycling of plastic bottles with shrink
  sleeves through near-infrared spectroscopy and machine
  learning algorithms -- Resources, Conservation and Recycling
  (2023), doi:10.1016/j.resconrec.2022.106719.
- Near-infrared-based quality control of plastic pre-concentrates
  in lightweight-packaging waste sorting plants -- RCR (2024),
  doi:10.1016/j.resconrec.2023.107256.
- Convolutional neural network for identification of plastic
  solid waste using near infrared spectroscopy -- preprint
  (2021), doi:10.21203/rs.3.rs-245885/v1.
- An IoT-based system for classification and identification of
  plastic waste using near infrared spectroscopy -- Proc. 2nd
  Int. Conf. Communication, Devices and Computing, Springer
  LNEE (2019), doi:10.1007/978-981-15-0829-5_65.

## Food authentication chemometrics

Thirty years of classification-on-spectra practice; the
methodological backbone for any fingerprint engine built on this
sensor. Preprocessing (SNV/MSC normalization, derivatives) and
models (PLS-DA, SIMCA, k-NN, SVM) come from this literature.

- The authentication of Basmati rice using near infrared
  spectroscopy -- JNIRS (1993), doi:10.1255/jnirs.8; further
  analysis (1995), doi:10.1255/jnirs.62.
- Authentication of whole and ground coffee beans by near
  infrared reflectance spectroscopy -- JNIRS (1994),
  doi:10.1255/jnirs.35.
- Commercial wheatflour authentication by discriminant analysis
  of near infrared reflectance spectra -- JNIRS (1993),
  doi:10.1255/jnirs.22.
- Authentication of food and food ingredients by near infrared
  spectroscopy (review) -- JNIRS (1996), doi:10.1255/jnirs.75.

## Few-channel spectral reconstruction

The rigorous treatment of "can we move between spectra and
few-channel fingerprints": forward synthesis with priors is a
real research direction; inversion is ill-posed. These papers
work from RGB; the math is the same for any few overlapping
channels.

- Cluster-based deep convolutional networks for spectral
  reconstruction from RGB images -- Neurocomputing (2021),
  doi:10.1016/j.neucom.2021.08.104.
- Colour fidelity in spectral reconstruction from RGB images --
  London Imaging Meeting (2020),
  doi:10.2352/issn.2694-118x.2020.lim-08.
- Enhancing deep spectral super-resolution from RGB images by
  enforcing the metameric constraint -- VISIGRAPP (2020),
  doi:10.5220/0008950100570066.

## What this means for us

1. The method is standard. Scan known samples, build a labeled
   library, fit a classifier: this follows published practice;
   the statistics are not new here.
2. Our NIR family sits in SCiO's band, and SCiO's whole
   application catalog (ripeness, dry matter, fat) lives there.
   The NIR subspace carries the discrimination power; build
   engine features accordingly.
3. Sample-size realism: these papers use dozens to hundreds of
   samples per class. Three repeats per target give capture
   quality, not statistical power; the library grows by repeat
   sessions and PRs.
4. Nothing found on open reverse engineering of such a device,
   or on an open community library replacing the vendor cloud.
   That part is genuinely new here.
