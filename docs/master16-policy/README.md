# Explicit RGB16 passthrough classifier correction — AUTHORED / UNRUN

## Scope and status

This is a bounded source correction to the inherited **explicit PNG16/TIFF16**
neutral shortcut, not a new renderer or an export-quality acceptance report.
The six omitted edit families previously could be silently bypassed by the
source-copy writer. They now use their existing canonical validators and actual
pixel-activity predicates in both live and frozen classification.

Original-format native16 remains independently **always edited-RGB16**, even for
neutral documents. No Original decision, codec, bit depth, preset, default,
source-proof, render order, destination owner, no-clobber publisher, or numeric
algorithm was changed. A blocker selects the existing checked edited path;
malformed input raises instead of qualifying as neutral. Neither result promises
that preparation or rendering will succeed.

Only source inspection, Python AST parsing, JSON parsing, SHA-256 inventory and
Git whitespace inspection were performed. **All authored and existing runtime
cases remain UNRUN in this correction.** No product/test imports, test collection,
pytest, build, typecheck, inference, codec execution, install or download occurred.
The user's local Qoder owner retains full functional/visual/codec acceptance.

## Canonical rules

| Family | Active | Genuine neutral examples |
|---|---|---|
| `colour_grading` | Any wheel saturation or luminance | Hue/blending/balance changes alone |
| `selective_colour` | Any CMYK range amount | Relative/absolute method alone |
| `primary_calibration` | Any primary hue or saturation | All six amounts zero |
| `extended_tone` | Enabled monochrome or effective amount | Disabled recipe; zero amounts and no monochrome |
| `photo_detail` | Enabled sharpen/luma/chroma amount | Radius/detail/contrast/smoothness alone; disabled amounts |
| `id_background` | Enabled and opacity above zero, after full validation | Valid disabled recipe or valid zero-opacity recipe |

Strict grading/selective/primary objects reject present `null`, incomplete,
unknown-field and nonfinite values. Missing legacy fields are neutral. Extended
tone/detail/ID preserve their canonical `check(None)` legacy-neutral contract;
this correction does not invent stricter saved-record semantics. ID validation
still includes source-bound support, spill and original-shadow children, even
when the parent is disabled or has zero opacity.

Legacy grade, LUT amount, exposure/WB/reference/tone, HSL, deform amounts and
enhance amounts now validate before identity comparisons. NaN, invalid ranges
and unknown zero-valued amount keys cannot disappear in `abs(value) > 0` checks.
An empty deform amount map remains valid neutral. The enhance wrinkle-unlock
flag is metadata only: `ENH.check_amounts` plus `facial_wrinkle_state.active_enhance`
keeps every actual effect, including families outside `ENH.PIXEL_KEYS`.

Frozen policy shares the exact existing 107-field producer inventory with
creative capture admission through an import-free module. A new unknown top-level
field fails closed even when its value is zero or null. The body snapshot envelope
is canonically checked before its bank is read. Non-null creative derived contexts
and an orphan body source proof block passthrough rather than silently returning
the original. Existing repair/light, nonempty liquify, enabled local-group/recovery,
geometry, support and retained-body validation remain conservative.

The no-enabled-face people case now materializes all-people overrides through
existing canonical recipe validators, without inventing a face or running
inference. `False == 0` cannot hide an invalid numeric-only leaf. The live helper
alone is **not** an active-document people gate; production frozen export remains
the people/source-ownership boundary. This is not a broad rewrite of dormant
asset/path ownership or a claim to have proved every future effect neutral.

## Creative capture collateral

Creative edited capture intentionally admits tonal grading, selective colour and
primary calibration. Those three actual recipes are validated before the local
diagnostic copy is neutralized. Only that diagnostic copy receives neutral
objects. Actual snapshot, fingerprint, built ExportSpec and rendering state keep
the complete user's recipe. Invalid/null native colour now declines admission.
Unknown fields and existing source-bound capture refusals are not relaxed.

## Authored acceptance handoff

`engine/tests/test_master16_policy_hardening_unrun.py` specifies:

- Every omitted family live/frozen, active and true neutral; disabled and legacy
  omission; incomplete/unknown/null/NaN state; ID nested support/spill/shadow.
- Legacy malformed scalars, 3-scalar exposure compatibility, zero-amount grade,
  metadata-only wrinkle unlock and every actual enhance effect key.
- Unknown frozen zero/null fields, malformed body envelopes, active missing
  support, disabled malformed support, retained recovery/liquify/repair/light,
  orphan contexts and frozen-target independence.
- No-face and only-disabled-face all-people numeric/boolean/unknown-leaf cases.
- Explicit edited-route selection and unchanged Original always-edited dispatch;
  both branches retain the existing destination wrapper (source-level contract,
  **not** a successful file-publication/no-overwrite runtime proof).

Creative admission fixtures additionally preserve real native colour state in
snapshot/spec/fingerprint. Existing master16 fixtures replace obsolete `eyes`
with the actual canonical `sclera` enhance key; no product alias was introduced.

Local Qoder should run the authored files plus existing
`test_master16_blockers.py`, `test_master16_batch_preflight.py`,
`test_master16_verification_cost.py`, `test_export_original_native16_unrun.py`,
`test_creative_edited_capture_admission_unrun.py`,
`test_creative_edited_capture_real_state_unrun.py`,
`test_export_destination_policy.py`, and `test_owned_export_destination_unrun.py`
with the project's installed dependencies and controlled runtime authorization.
Then verify actual single/batch PNG16 and TIFF16 outputs with each active family,
neutral low bits, exact frozen document state, source change/refusal, pre-existing
output preservation, cancelled/failed preparation and mixed people/body/derived
sources. Full photographic quality, native dependencies, GPU/CPU behavior,
performance, encoded readback, race safety and complete application coverage have
not been established by this source work.

## Reproducibility

Baseline local commit: `1c1b71761a2a32e81b84f0c7fbefe1f40372fbe7`.
Supplied remote equivalent: `1329684a545de148d553b41dd91b43e92500acad`.
Baseline tree: `1c8f5e3b98a6f7b0ea704afcea647af31957d4d6`.
`source-manifest.json` records changed deliverables and preserved route/publication
files by byte count and SHA-256. The manifest excludes itself to avoid a recursive
hash claim. It records static checks, not execution or publication success.
