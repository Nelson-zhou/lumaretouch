# Original same-face chromatic evenness

**AUTHORED / UNRUN.** Original dependency-free Rust source, strict Python ABI and
recipe state, build hook, header and fixtures only. No product import, compiler,
build, test collection/execution, typecheck, inference, benchmark, installation,
download or Git write was performed. Source review is not compilation, numeric
validation, photographic acceptance, CPU/GPU parity or release readiness.

Exact partial reference: `LNX-REF-PC-32465-C-60b7c0e3d1`, AI肤色统一（脸部）, from
[the official skin guide](https://www.pixcakeai.com/guide/32465). This source adds
a dedicated deterministic face-skin chromatic-evenness operation, not an alias for
`skin.broad` frequency smoothing. Old recipes are unchanged. It does not reproduce
or claim equivalence to a proprietary AI, blemish detector, learned classifier,
physical illumination/material separation, body correction or multi-person match.

Preparation uses reliable statistical log-chroma from this same face only, an
original coverage-normalized luminance-guided low-frequency chroma construction,
and a bounded source-owned displacement field. Application changes chroma while
preserving each **actual current-stage** pixel's linear luminance, with one common
gamut-feasible interpolation. It never blurs/replaces luminance texture, clips
channels independently, quantizes RGB8 or uses an external skin-color palette.

- Recipe: `lnx.skin_evenness.v1`, exactly `{version:1, amount:0..1}`. Zero neutral.
- `prepare(source_rgb, coverage, amount, *, radius, cancelled)` returns an owned
  read-only contiguous float32 HWC2 log-chroma field.
- `apply(current_rgb, shift, *, cancelled)` returns owned float32 RGB, preserving
  current Y to the documented float32 tolerance. HWC2 is never an RGB placeholder.
- Both input grids are encoded working-sRGB-D65 SDR. Strict finite native float32
  inputs, source-grid radius4..256, at most32M pixels, resource/cancellation checks.
- Active missing reliable own-face reference or entirely invalid guided context
  explicitly refuses. A valid already-even face can produce an exact zero field.
- All nonzero native statuses leave caller output untouched. Python publishes
  only a validated complete new result. Missing native code never falls back.

See [the numerical contract](../../docs/skin-evenness/NUMERICAL-CONTRACT.md) for
source ownership, exact thresholds, same-face window/halo requirements, current-Y
reconstruction, ABI, resource accounting and authored/unrun acceptance coverage.
The offline hook is `sh packaging/build-skin-evenness.sh`; it has not been run.
The runtime library is `engine/src/lumaretouch_engine/bin/liblrt_skin_evenness.so`.
No binary, external assets/models, vendored implementation or Cargo lock is added.

## License and conceptual provenance

Original project implementation: **GPL-3.0-or-later**, as declared in every source
header and Cargo manifest; the complete GPL text is the repository [LICENSE](../../LICENSE).
The project owns its new code and uses existing local ABI/resource conventions.
External publications supplied concepts, not copied code or assets. No proprietary
license or source authorization is inferred from publicly described behavior.

Conceptual primary references are He/Sun/Tang's luminance-guided chroma treatment
and Barron's log-chrominance translation discussion, linked in the contract. The
masked statistical construction, source admission, correction bounds, constant-Y
application and fail-closed contracts here are independently authored. They are
not asserted to reproduce those papers' full algorithms or learned estimators.
