# Product coverage checkpoint — 2026-10-22

Published code checkpoint: 083f6f149d886fb076df1e04a8f138efa6620aa3. This updates the
older sampled audits, not a claim to have independently accepted every handbook
requirement. The original product handbook and AI development package remain the
scope; deferred real-device validation does not remove any feature.

## Do not turn catalogue counts into completion percentages

The1047 traceability records include805 child controls,206 parent/workflow/UI/
acceptance records and36 P0 contracts. They overlap. Neither these records nor the
partial39-route UI table form an independent implementation denominator. No reliable
whole-product completion percentage is currently established.

## Real implementations that must not be listed as entirely absent

- RAW/proxy import and full-source inspection infrastructure; frame-bound aspect
  and identity handling. Native/physical quality acceptance remains separate.
- Exposure, versioned WB algorithm/reset, levels, RGB/channel/linear-Y point curves,
  parametric curves, legacy-HSV8 HSL, crop/rotation and partial portrait operators.
- Bounded stage histogram/readout and identified RGB/Lab colour sampling. WB,
  levels black/white, curve targeted dragging and HSL hue dragging now also have
  connected action paths. Their frozen-stage previews are not final full-chain
  images or full-source real-time analytics; see targeted-color-pickers.md.
- Project/history, complete-scope presets, frozen-source/target batch preflight,
  correlated receipts, conflict-aware scoped undo and export task handling.
- True RGB16 input/float editing/RGB16 output paths; not an8-bit left-shift substitute.

The old sampled “parametric curves” and “frozen batch” gaps have code/basic-test
implementations now. The old product-gap-audit's top-level table is historical and
must be read with subsequent corrections, not copied as today's missing-feature list.

## Major functional groups still incomplete

1. Professional colour completion: AI colour matching and group consistency,
   lens/perspective/calibration requirements. Action pickers now have connected
   code, not independent runtime or photographic acceptance.
2. Detailed portrait families: independent body, hair, makeup, clothing, hand/foot
   and many blemish/reshaping controls. One related slider does not close a family.
3. Local editing: remaining automatic/category/free/quick AI selection, mask
   batch/preset groups, effect recovery and full liquify protection. Retained composable brush/linear/
   radial/color/luminance objects and real portrait-category sources are now wired
   to the existing grade consumer; this does not make LUT or every adjustment local. Source-sampled patch and genuine
   clone-stamp brush are connected in code (source-patch-tool.md / clone-stamp-tool.md),
   not yet accepted.
4. Multi-person/cross-image workflows: grouping, parameter-level inheritance and
   explicitly confirmed cross-image identity associations.
5. Advanced delivery: remaining output requirements beyond the connected watermark,
   ordinary/ID-photo layout and explicit native print-dialog workflows. These code
   paths are not accepted; see export-watermark-implementation.md / layout-print-workflow.md.
6. Creative/generative tools and the separately requested optional extension flow.

These are major groupings, not six equally sized tasks or a complete item-level count.
WB picker sampling/math infrastructure passed61 dedicated cases historically.
Its capture redemption, native/UI lifecycle and click-to-edit path are now connected
in code; this integration remains unverified. See white-balance-picker-implementation.md.

## Separate final validation track

Real photographs, texture/identity/edge quality, GPU parity, interactive latency,
large batches, controlled colour display, clean installation and release/license
verification remain. They must not be mixed into the count of missing code features,
or used to stop independent feature implementation.

## Reuse review before further broad custom implementation

Direct related projects have been identified for source-level comparison:
- https://github.com/crispin81/RapidRetouch : local Evoto/Aperty-style portrait editor,
  AGPL-3.0-only; a direct product comparator, not merely an algorithm library.
- https://github.com/CyberTimon/RapidRAW : Rust/Tauri/WGPU editor, AGPL-3.0, with
  published masking/retouch/output/ComfyUI workflows.

README features are claims to inspect, not proof of quality or drop-in compatibility.
Pin source revisions, trace UI→processing→export, inspect tests, separate code and
model licensing, and compare integration cost before copying or choosing a new base.
RapidRetouch source-patch code has now been adapted with AGPL-3.0-only attribution
and bundled license; subsequent under-eye/clothing adapters retain the same source
obligations. Existing unrelated source licenses remain unchanged. The development
branch policy, installed application and original functional scope are unchanged.

## Development-first delivery policy

User confirmed on 2026-10-22 that complete function packages take priority over
per-change regression loops. Continue implementation without waiting for each CI
result; consolidate behavioral and physical acceptance at phase end. Keep necessary
interface/compile correctness, preserve tests already written, and label unverified
work explicitly rather than reporting it as accepted.

Additional development-first code packages (not acceptance claims):
- Independent dark-circle and eye-bag controls use actual selected-face landmarks,
  retained source-derived correction, history/project and full-resolution replay.
  The preserve-aegyo-sal control and broader makeup family remain separate gaps.
- Fine clothing-crease correction uses the actual semantic clothes channel and
  connects state/history/project/preview/full export. It is not garment synthesis,
  coarse-fold removal or upper/lower garment separation. Cross-image processing
  without that image's own clothing mask is explicitly rejected.

The composable mask package uses project v4 and retains v1–v3 migrations. Its
source/model identity and Rust worker implementation are unverified integrations,
not evidence of runtime or image-quality acceptance. See composable-local-mask-scope.md
and semantic-mask-source-scope.md for exact covered and unimplemented controls.

## Subsequent connected packages, still pending runtime acceptance

- SAM2.1 Tiny positive/negative points and box prompting, reviewed candidates,
  retained source/model-bound selections and explicit optional installation are
  connected. This is not pet classification or generic automatic subject selection.
  See prompted-ai-selection-scope.md for exact resource limits and licensing.
- PC-32454 child72 is true colour-range selection inversion, not merely inversion
  of the overlay. Child75 is a read-only luminance/retained-coverage diagnostic,
  not a live draft mask. The matching Rust worker now uses LMR2.
- Source-domain object coverage is transformed by the same deformation grid as
  the image before the existing post-LUT grade consumer. The actual pipeline has
  deformation before exposure/levels/curves/HSL/LUT/grade; the old statement that
  the grade consumer precedes deformation was incorrect. The established image
  operator order was not changed to accommodate masks.
- Independent local-grade groups and real mask batch/preset append/replace are
  currently being implemented. They are not yet included in this published
  checkpoint. Tool-specific recovery brushes are also in development, not done.

No local application, build, typecheck, model installation/download or inference
was run for these recent packages. Existing automatic CI results and eventual
Qoder/physical checks must be recorded separately; published code is not an
installation or acceptance result.
