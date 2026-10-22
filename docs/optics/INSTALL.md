# Optical runtime installation and release production

Status: implemented source wiring, **not built, installed, run, or accepted in this task**. Qoder must verify the actual package and photographs. No source/model download was executed here.

## Normal users: no compilation

The normal Linux release bundles a prebuilt Lensfun 0.3.4 shared library, lensfunpy 1.18.0, and the independently pinned official 2026-10-20 calibration database. `setup-runtime.sh` installs that verified wheel **offline**, with no compiler, resolver, database updater, or model download. The existing Python/GPU setup still explicitly acquires its ordinary dependencies. The Debian package depends on the distribution's ExifTool for RAW lens metadata. Perspective uses the existing `opencv-contrib-python==5.0.0.93`, not a second cv2 distribution.

The release baseline is Ubuntu 24.04 Linux x86_64 and CPython 3.12, matching the existing uv setup. Without uv, setup selects `python3.12` (or an actual CPython 3.12 `python3`) and rejects an incompatible existing venv **before torch downloads**. It never silently replaces that venv. Use a separate `--prefix`, or explicitly choose `--force-new`. Other architectures need their own producer artifact; mismatched ABI, architecture or older libc is rejected with the required platform. No cross-platform acceptance is claimed.

Repair a normal installed runtime by rerunning `/usr/lib/LumaRetouch/engine/setup-runtime.sh` with the original GPU variant. Its optical-only offline repair is:

```
<engine-venv>/bin/python /usr/lib/LumaRetouch/engine/setup-optics.py install \
  --bundle /usr/lib/LumaRetouch/engine/runtime/optics \
  --python <engine-venv>/bin/python
```

The actual UI error shows the packaged path. Missing/ambiguous camera, focal metadata or calibrated branches remain explicit, with manual fallback. A profile name is not proof that correction was applied. RAW defaults enable correction only for a real usable profile; nonRAW defaults off. Manually configured `LRT_LENSFUN_DB` overrides the bundled directory explicitly, never silently. Changed XML/library identity invalidates prior correction and review rather than silently adopting a new result.

## Release producer, not an end-user requirement

`packaging/build-deb.sh` invokes `prepare-optics-release.sh --acquire` before existing staging/build/check steps. `.github/workflows/ci.yml` invokes the reusable optical producer and downloads its same-run, same-commit artifact before UI staging. Existing CI tests and triggers remain in place.

The producer requires distribution `build-essential cmake pkg-config libglib2.0-dev python3.12-venv binutils`; CI installs these explicitly. It creates a separate build venv, announces pinned official-PyPI build-tool acquisition, then fetches exact official Git source objects from `optics-sources.lock.json`. CMake builds the replaceable Lensfun shared library; the wrapper links through pkg-config with `$ORIGIN/_native` rpath. No source build occurs on normal application startup.

### Build-interpreter binding

`requirements-optics-build.txt` already pins setuptools 80.9.0 in the isolated
build venv. Lensfun 0.3.4's pinned
[apps/CMakeLists.txt](https://github.com/lensfun/lensfun/blob/101c745e847a5de4a1e569a94368ce2027198598/apps/CMakeLists.txt)
uses `FIND_PROGRAM(PYTHON "python3")` and creates its Python-package build/install
commands independently of `INSTALL_PYTHON_MODULE=OFF`. Therefore that flag alone
does not avoid its generated setup.py, which imports setuptools.

The producer now passes the admitted venv executable as `-DPYTHON:FILEPATH=...`,
checks the resulting CMake cache before building, and uses the same venv-first
PATH for configure, build, install, database conversion and wheel creation.
It preserves the venv interpreter's symlink path rather than resolving it to
system Python. Inherited PYTHONHOME/PYTHONPATH and user-site imports cannot supply
different build modules; dependency admission uses this same environment.
Both selected interpreter paths are recorded in bundle provenance. This fixes
the source-level interpreter mismatch without installing global setuptools,
adding runtime dependencies or changing offline installation policy. The fix
has not been built or executed in this task; a later normal CI result must
establish whether the producer now succeeds.

The library pin is independent of calibration commit `b98997f7f1c020d0fac3136c2abbf06126385971` (official repository, 2026-10-20). Its own pinned `tools/update_database/xml_converter.py` performs the official v2→v1 compatibility conversion. This removes unsupported ACM calibration records rather than inventing coefficients. Raw database digest, converted digest, converter digest/blob, commit timestamp, authors, source archive, license, and conversion notice are retained. Updating this pin is an explicit new release, not background acquisition.

`BUNDLE.json` binds the wheel SHA256, source commits/archives, XML SHA256, Python ABI, architecture, libc, actual dynamic linkage, build tools and application commit. Stage/installation revalidate it and archive budgets; CI uses no unrelated downloaded mystery bundle. Existing offline artifacts must match the same application commit. `LRT_OPTICS_OFFLINE=1` forbids acquisition and requires such an artifact. A local developer can explicitly use `LRT_ALLOW_MISSING_OPTICS=1` for staging without optics; that writes `OPTICS-NOT-BUNDLED.txt`, and the normal release producer refuses this opt-out.

Independent advanced commands are `setup-optics.py fetch`, `build`, `verify`, `stage`, and `install`. Only `fetch` acquires the pinned source repositories; `prepare-optics-release.sh --acquire` separately acquires the declared build tools. These are developer/release/repair routes, not promises that source installation has already succeeded.

## Redistribution and remaining acceptance

The wheel includes exact corresponding source tar archives and full available license texts: Lensfun library LGPL-3.0-or-later, bundled source applications GPL-3.0-or-later, calibration CC-BY-SA-3.0 (including its legal text), lensfunpy MIT. Original database author attributions and an explicit conversion notice accompany the derivative XML. The library remains a replaceable shared object. System GLib/C/C++ and ExifTool remain distribution dependencies with their own package source/notice obligations; they are not falsely relabeled MIT. The original Rust optical kernel and its source/license are staged separately.

Required before release acceptance: actual producer build, linkage/replacement and offline install on the baseline platform, full license/package inspection, calibration coverage and missing-profile behavior, real RAW/nonRAW metadata, precision/full16/tile equivalence, automatic-solver quality and memory admission. The source changes establish a concrete supported build route; they do not certify an unrun artifact or optical quality.
