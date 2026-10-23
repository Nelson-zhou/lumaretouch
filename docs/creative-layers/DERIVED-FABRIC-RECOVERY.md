# M14 derived fabric and reviewed global recovery

Source-only continuation of `95ed4f10ace05ad386cb4b9227699a7870f32a9d`.
Subsequent smoothing and its recovery source port is documented in
[DERIVED-SMOOTHING.md](DERIVED-SMOOTHING.md); it supersedes that specific residual
below, not the UNRUN acceptance boundary.

All numerical, model, native, UI, persistence-runtime and visual acceptance is
**UNRUN**. This is not completion of M14, the clothing module, or 32 AI tools.

## Exact scope and evidence

Handbook mapping: fine creases `LNX-REF-PC-32477-C-f9b27ee32d`, clothing manual
brush `LNX-REF-PC-32477-C-c68a287a5a`, and clothing-wrinkle recovery
`LNX-REF-PC-32481-C-35a8c63501`; return and history remain
`LNX-REF-WF-127932-a9c143a25d` and `LNX-REF-WF-127932-c7783ea5fb`.
The clothing brush reference is a scope reference, not a claim that every
clothing enhancement brush is implemented.

The supplied handbook and mapping were read. Live reads of the official
[clothing guide](https://www.pixcakeai.com/guide/32477) and
[recovery guide](https://www.pixcakeai.com/guide/32481) were unavailable through
the web reader this turn; no new official behavior is inferred from that failure.
The [MediaPipe primary guide](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter)
was read: confidence fields are model-specific; its six-class model identifies
clothes separately from person/background. A person silhouette or inverse skin
mask is not accepted as clothing evidence.

Existing `ops/fabric.py` and `fabric_math.py` retain the RapidRetouch
`5e9d9c1d2770ff29d11a3879e5a90aad5887e028` AGPL-3.0-only adaptation with existing
LICENSE/NOTICE. No upstream code was downloaded or copied in this slice.
Measurement remains Python/OpenCV and application torch, not a new Rust or AI
solver. Existing Rust normalized-vector rasterization remains the recovery mask
producer. We preserve existing quality rules rather than claim an algorithm port.

## Actual consumer and source boundaries

The existing all-clothes fine-crease slider now has a precise derived-source
command contract. Fresh measured clothes confidence, pinned semantic-model
identity, actual analysis-input proof and normalized face-scale vectors are
captured independently of original-file provenance. Proxy measurement verifies
actual immutable source pixels and the ordered repair replay output. Cache keys
cover content, source, model, scale and repair evidence instead of object IDs.
Missing evidence does not silently turn an active derived fabric edit into a
neutral render. It refuses and reports the missing prerequisite; zero/clear
remains possible without fabric inference.

Export captures a bounded read-only confidence/scale bank in its frozen snapshot,
not in project history. The canonical source resolver stamps the actual full
working-sRGB float32 input. If repairs exist, their completed ordered replay proof
is checked before fabric measurement. Only semantic confidence is resampled;
the fine-crease correction is measured once on the full image and shared by tiles.
There is no enlarged proxy correction, uint8 image roundtrip, fake original SHA,
new source bitmap per history step, or silent precision/alpha/HDR conversion.

## Recovery, review and persistence

Only `fabric_fine` joins existing face-owned recovery on derived sources.
`skin_smoothing` and `background_replace` remain refused, including disabled
persisted rows. Global fabric review has its own immutable source, consumer
amount/evidence and prior recovery-recipe context; it does not manufacture a
selected face. The real production before/after render, presentation, apply and
terminal receipt remain required. Context is rechecked after rendering, before
presentation and before apply. Face recovery keeps its separate FaceRef/graph
proof and support bank. A pre-existing native reachability gap was closed: both
request and rendered-review validators now share the exact existing nine face
targets plus the three pre-existing global target names. Native acceptance does
not bypass engine source admission: smoothing/background remain refused on
derived sources, and every face still requires its exact existing owner/review.

Global recovery vectors bind the immutable composite digest and extent while
original file stamps and digest remain separate provenance. The existing Rust
raster reruns normalized vectors at the actual proxy/full source dimensions.
Existing float attenuation mixes only this operator's before/after delta, not
original RGB over other edits. Exact zero/full coverage endpoints and shared
geometry order remain unchanged. No second undo owner is introduced.

Project v23 remains unchanged. The central creative project walker validates
recovery against each decoded enclosing source, including disabled rows, inactive
versions and history. Live state restore validates before mutation. Persisted
intent remains amount plus normalized vectors; ephemeral semantic banks and
resolved-pixel proofs are not saved. Reopen still requires actual current-source
analysis before the fabric effect can render/export; original-file observations
are never promoted to derived evidence.

## Integration map

- `creative_derived_fabric.py`, `fabric_controller.py`, `fabric_export.py`:
  measured confidence/scale and actual pixel ownership; unchanged solver.
- `creative_derived_global_recovery.py`, `effect_recovery_runtime.py`:
  retained global source identity, vector raster/export and pixel/provenance proof.
- `creative_derived_recovery.py`, `effect_recovery_preview.py`,
  `effect_recovery_state.py`: distinct reviewed global consumer context and exact
  mutation binding, preserving face ownership and receipts.
- `export_snapshot.py`, `export_recipe.py`, `export.py`:
  frozen evidence, canonical float stamps and actual full-source transport.
- `creative_document_host.py`, `creative_document_base.py`:
  narrow command and direct-library snapshot/spec admission.
- `ui/src-tauri/src/effect_recovery_api.rs`, `effect_recovery_host.rs`:
  exact shared native target predicate, existing capture/presentation/receipt
  fences unchanged; no UI protocol expansion or new unsupported global targets.
- `creative_document_project.py`, `server.py`: enclosing project/history source
  validation before publication. Existing FabricPanel and recovery UI routes are
  reused; App/main size does not grow for this feature.

## Remaining work and acceptance boundary

All-clothes fine creases are not coarse creases, upper/lower garment separation,
link controls, garment blemishes, sweat removal, edge repair or garment synthesis.
These remain separate handbook requirements. Smoothing needs actual effective
skin/channel ownership and preview/export filter cache contracts; allowing only
an unmasked strength command would not close the ordinary skin-edit workflow.
Background adjustment and background replacement have separate acquisition,
review, full-resolution segmentation and geometry-aware recovery dependencies.
Neither is enabled by this slice. Shared transfer still needs explicit per-target
identity review and target-owned analysis, never copied source masks.

Transparent/HDR photo return remains explicitly refused without flattening or
clipping. Existing budgets remain; no unconditional 24 MP or latency promise.
Fixtures are authored for evidence mutation, foreign/disabled targets, actual
float transport, review expiry, persistence and native target validation. They
have not been run. Real local QA must check models/native libraries, weave and
print preservation, repaired-image coexistence, tiled/full parity, recovery
endpoints, undo/redo, save/reopen/recovery/package, stale/cancel/replay and memory.
