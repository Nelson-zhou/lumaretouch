# Selected same-photo skin reference matching core

**AUTHORED / UNRUN.** Original dependency-free Rust, GPL-3.0-or-later. No compiler,
product import, build, test execution, inference, benchmark or download was run.
No runtime library or working-product/photo-quality claim is supplied.

This independent source module supports `lnx.skin_reference_match.v1`: explicitly
selected actual same-photo reference-face skin statistics can adjust the colour
**and brightness** of separately reviewed target face/body skin. It never detects
the brightest face, supplies instance/body masks or authenticates ownership.
The host must exclude the selected reference face from every target application.
The public reference requirement remains `control:PC-32465:19`; its lost original
hashed LNX mapping is not reconstructed or guessed.

This is not a relabel of `lnx.body_face_match.v1`, whose different operation is
body-to-own-face chroma only. There is no full AI multi-person feature parity.

- `fit_reference`: independent real source ROI sizes, streaming robust log-Y and
  log-chroma statistics, bounded separate brightness/chroma shifts, diagnostics.
- `apply_into`: immutable fit applied pointwise to **current** RGB through reviewed
  coverage, original dimensions and sampling intact, no halo, blur or source replay.
- C ABI: `lrt_skin_reference_match_abi`, `lrt_skin_reference_match_fit_v1`,
  `lrt_skin_reference_match_apply_v1`, declared in `skin_reference_match.h`.
- Neutral amount accepts absent evidence and copies exact current bits. Active
  missing/ambiguous evidence refuses instead of fabricating a neutral success.
- Fixed-size fit histograms avoid full-image sample storage; bounded staged tile
  application leaves output untouched on error or cancellation.

See [CORE](../../docs/skin-reference-match/CORE.md),
[NUMERICS](../../docs/skin-reference-match/NUMERICS.md),
[RESEARCH](../../docs/skin-reference-match/RESEARCH.md), and
[unrun acceptance](../../docs/skin-reference-match/ACCEPTANCE-UNRUN.md).
The complete project GPL text is [LICENSE](../../LICENSE).
