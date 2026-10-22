# Optics optional acquisition and redistribution

Nothing below has been installed, built, resolved, fetched or accepted by this
implementation task. These are explicit packaging steps, not application startup
actions. There is no model-weight download or alleged trained perspective model.

## Components and provenance

- Original Rust ABI and manual transform code: repository GPL-3.0-or-later source.
- Lensfun library: official documentation specifies LGPLv3 for libraries and
  GPLv3 for bundled applications; the lens database is separately CC-BY-SA3.0.
  Library attribution is not sufficient for database redistribution.
  https://lensfun.github.io/manual/latest/license.html
- lensfunpy1.18.0: MIT Python/Cython wrapper. Linux upstream setup uses pkg-config
  to link Lensfun. Prefer a Linux source build against a replaceable system
  library. Do not assume the wheel's bundled native libraries/database have only
  the wrapper's MIT license or that `--no-binary` proves redistribution compliance.
  https://pypi.org/project/lensfunpy/1.18.0/
  https://github.com/letmaik/lensfunpy/blob/master/setup.py
- OpenCV: use an audited recent4.x build exposing LSD. Versions4.1.0–4.5.3 had
  its implementation removed; official docs say restoration followed MIT
  publication of NFA code. Review actual OpenCV and all wheel component notices,
  not only the Python package name. Distribution source/system builds are valid
  alternatives. https://docs.opencv.org/4.x/db/d73/classcv_1_1LineSegmentDetector.html
- ExifTool: optional camera/lens metadata reader, licensed under the same terms
  as Perl. Preserve the applicable upstream license notices with a distributed
  copy, and audit the exact distro package. https://exiftool.org/
  https://exiftool.org/exiftool_pod2.html

## Explicit staged release process

1. Choose target distro/architecture and record exact Lensfun, OpenCV, ExifTool,
   Python, NumPy and wrapper versions. Acquire from official vendor repositories
   or well-known registries only in a separate authorized release setup step.
   This task has not approved or executed dependency installation.
2. Resolve the complete dependency tree in that setup environment; record hashes,
   sources, versions, license texts and notice files. Produce an offline wheelhouse
   and a platform lock. `requirements-optics.txt` is a candidate declaration,
   NOT a resolved lock or an assertion that all wheels were audited.
3. For Linux, build lensfunpy from the staged source using distro Lensfun headers
   and pkg-config. Verify actual dynamic linkage and replacement of Lensfun.
   If redistributing LGPL components, provide required source/relink/replacement
   materials as appropriate. If choosing a bundled wheel, separately audit its
   native dependency tree and satisfy those actual terms before shipping.
4. Stage a SPECIFIC official Lensfun XML database snapshot, with its author
   attribution, source/version, CC-BY-SA3.0 license and change notices if modified.
   Do not silently update this snapshot. A project pins XML digest and runtime
   Lensfun+wrapper versions; a changed/missing snapshot suspends its correction.
5. Configure `LRT_LENSFUN_DB` to the staged directory. Only its immediate XML files
   are loaded; no common/system/bundled fallback. Bound to4096 XML files /32MiB,
   rejecting symlinks and change-during-load. Keep external symlink/path/permissions
   assumptions visible in release review. No network updater is called.
6. ExifTool may be supplied by a system package or an explicit `LRT_EXIFTOOL` path.
   Runtime disables per-user ExifTool executable config and requests only make,
   model, lens name, focal length, aperture, subject distance and orientation.
   No GPS, owner or serial is retained. The subprocess has15-second and32KiB
   output bounds. It never writes source tags or sends files off-machine.
7. Build the Rust kernel with `bash packaging/build-optics.sh` as an explicit
   packaging action, not at runtime. Ship the ABI1 `.so` with its corresponding
   Rust source. Missing/mismatched ABI produces a visible error.
8. Execute and record local optical quality/precision/interaction/packaging
   acceptance in the authorized Qoder environment before release enablement.

## Absence is a visible state, not success

Missing Lensfun/DB/calibration or ambiguous camera/lens leaves RAW auto correction
off with a reason. NonRAW starts off. Manual distortion/vignette and guided/manual
perspective need the Rust core but not Lensfun/OpenCV/ExifTool. Automatic perspective
needs actual OpenCV LSD; absence/low confidence rejects the request, never substitutes
fixed geometry. Unknown aperture/distance disables calibrated vignetting, not all
other available calibration. Internally Lensfun requires arguments for inactive
branches;0 aperture /1000m are sent only when vignetting was not requested, never
retained as claimed measured data. Manual metadata selection is explicit in UI.

## Calculation sources

Lensfun returns inverse geometry and per-channel coordinates; callers must
actually resample RGB. This package does so with its Rust sampler:
https://lensfun.github.io/manual/latest/structlfModifier.html
https://letmaik.github.io/lensfunpy/api/lensfunpy.Modifier.html

Camera/lens lookup, calibration availability and explicit database paths:
https://letmaik.github.io/lensfunpy/api/lensfunpy.Database.html
https://letmaik.github.io/lensfunpy/api/lensfunpy.Lens.html

The wrapper's initialize method returns None; actual enabled branches are probed
through generated geometry and color gains, rather than treating a database
record or a nonexistent return bitmask as proof of correction:
https://github.com/letmaik/lensfunpy/blob/master/lensfunpy/_lensfun.pyx
