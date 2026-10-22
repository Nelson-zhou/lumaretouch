# Optical dependencies, acquisition and redistribution

This task changed source only: no dependency build/install/download, product run,
test, typecheck or quality acceptance occurred. The concrete normal packaging path
is now [INSTALL.md](INSTALL.md), not merely optional requirements.

## Independent pinned sources

- Lensfun **library** 0.3.4, official commit
  `101c745e847a5de4a1e569a94368ce2027198598`, library LGPL-3.0-or-later.
  Its source applications are GPL; they are not installed as app runtime helpers.
- Official **database**, independently pinned at
  `b98997f7f1c020d0fac3136c2abbf06126385971`, 2026-10-20, selected from the official
  commit listing on 2026-10-22. CC-BY-SA-3.0 with original author attributions.
  Its own official `xml_converter.py` blob
  `42bd88ea2bb6a54df9322c18fcd9e52287f58fb9` converts v2 to compatible v1. This
  conversion drops unsupported ACM records; unavailable branches remain explicit.
  We do not freeze lens coverage to the library's old 2023 release or fabricate
  replacement coefficients. Both original/converted hashes and change notice ship.
- lensfunpy 1.18.0, official commit
  `458a24475ae03ec52f0fac4fea786120ef5a503f`, MIT wrapper. Built against the actual
  replaceable Lensfun shared library, not an assumed-MIT opaque vendor wheel.
- Existing normal engine OpenCV: `opencv-contrib-python==5.0.0.93`. Do not install
  an additional headless/cv2 distribution. Actual LSD detection/solver is used,
  never a fixed guessed transform or pretended ML model. There are no weights.
- ExifTool is a normal Debian `libimage-exiftool-perl` dependency for RAW metadata,
  with developer override `LRT_EXIFTOOL`. Perl/ExifTool license and source are
  supplied through the distribution package, not mislabeled as wrapper MIT.
- Original Rust transform/remap ABI: repository GPL-3.0-or-later, built/staged
  with its corresponding source. Missing or mismatched ABI fails visibly.

The source lock records exact official repositories/commits. The release producer
emits and checks actual source archive SHA256, XML digest and wheel SHA256, platform,
ABI, linkage, compiler and application commit. Full source archives and legal texts
(including database CC-BY-SA text) accompany the library/wrapper. Source pinning
is reproducible provenance, not a claim of byte-identical compiler output. The
system GLib and C/C++ runtimes remain dynamic distribution dependencies. Audit the
actual release artifact, system dependencies and full wheel notices before shipping.

Normal setup installs the prepared bundle offline, never compiles Lensfun for users.
CI and `build-deb.sh` have an actual source producer before staging. Only explicit
release acquisition fetches official source and pinned build tools. The app does
not update databases or download models. No build was run in this task.

## Runtime absence and safety

Missing/ambiguous profile or incomplete metadata never silently succeeds. RAW auto
correction defaults on only after real usable profile resolution; nonRAW defaults
off. Manual distortion/vignette and manual/guided perspective need Rust but not
Lensfun/OpenCV. Unknown aperture/distance disables calibrated vignetting, not
unrelated available calibration. Internal inactive-branch placeholder arguments
are never retained or represented as measured metadata.

The bundled database is loaded only after source/provenance/version/hash checks.
An explicit `LRT_LENSFUN_DB` chooses a separate local directory, with no common-DB
fallback. XML count/size/symlink/change checks remain bounded. A changed database or
library invalidates frozen proof and retained correction rather than silently
re-solving. ExifTool uses no per-user executable config, reads only camera/lens
calibration tags, retains no GPS/owner/serial, has 15-second/32-KiB limits, and never
writes the source or uploads photos.

## Primary calculation and license sources

- https://github.com/lensfun/lensfun/tree/101c745e847a5de4a1e569a94368ce2027198598
- https://github.com/lensfun/lensfun/commit/b98997f7f1c020d0fac3136c2abbf06126385971
- https://github.com/lensfun/lensfun/blob/b98997f7f1c020d0fac3136c2abbf06126385971/tools/update_database/xml_converter.py
- https://github.com/lensfun/lensfun/blob/master/docs/make-release-0.3.x.txt
- https://lensfun.github.io/manual/latest/license.html
- https://lensfun.github.io/manual/latest/structlfModifier.html
- https://letmaik.github.io/lensfunpy/api/lensfunpy.Modifier.html
- https://letmaik.github.io/lensfunpy/api/lensfunpy.Database.html
- https://github.com/letmaik/lensfunpy/blob/458a24475ae03ec52f0fac4fea786120ef5a503f/setup.py
- https://docs.opencv.org/4.x/db/d73/classcv_1_1LineSegmentDetector.html
- https://exiftool.org/exiftool_pod2.html

Lensfun supplies coordinates/gains, which the Rust sampler actually applies.
A database record alone, or the wrapper initialize method's None return value,
is never treated as proof of applied correction.
