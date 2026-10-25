# Smallest honest end-to-end implementation map

All steps below are future work. The current handoff authors only research
documents. It does not make any requirement accepted, enable a control or change
an export backend. In particular, an isolated callable neural model is not the
AI超清 workflow, and a disabled button is not completed implementation.

## A. Parallel-safe module ownership

| Proposed independent owner | Responsibility | Existing integration boundary |
| --- | --- | --- |
| ai_clarity_manifest / pack | Fixed code/weight/runtime provenance; local-only verification; structured unavailable reasons | Follow the strict separate optional-pack pattern in creative_generation_pack, not an owner-supplied environment checksum as the provenance authority |
| ai_clarity_backend | Exact official architecture and safe strict loader; explicit RGB-f32 forward; bounded inference; no UI/history/network | Replaces neither ops/upscale nor current experimental ops/realesrgan; distinct backend ID prevents compatibility confusion |
| core/ai_clarity + narrow native bridge | Original canonical transfer/admission, optional global float downsample, source-space coverage fusion, exact neutral/zero-coverage copying | Reuse existing canonical format and native-first numerical boundaries; separate new module, not changes to expression/lens cores |
| ai_clarity_regions | Genuine source-bound face/body/background semantic definitions and reviewed masks | semantic_sources and body_skin_semantics are evidence inputs only, not complete face/body masks |
| ai_clarity_stage / job | Immutable full-source capture, request/model/settings/mask receipts, cancellation, resource reservation and temporary result staging | creative_document_base.capture_current_asset for full current photo edits; CreativeRenderer for the current creative graph; creative_derived_source for returned-base identity |
| ai_clarity_state / controller / host | One reviewed draft and one atomic Apply through current document owner; replayable intent and immutable result record | creative_document_controller and creative_document_host commit through existing history; versioned schema/storage changes reviewed together |
| ui/src/aiClarity + Tauri port | Four honest strengths, region review, actual full-source comparison, Apply/Cancel, progress/error state | App/CreativeWorkspace only gets a narrow owner hook/entry; no new duplicated document or undo stack |
| ai_clarity_recipe / batch | Scalar/model intent transfer, per-target full capture + local masks/inference, job receipts and per-target failures | Existing recipe/task/preset owners; no copying another target's output or mask |

Names are proposals, not existing modules. Parent integration should assign these
non-overlapping owners before edits. Existing expression/lens work can continue
without touching this new docs directory. Future shared host/App/protocol/schema
changes require one integration owner, not simultaneous competing edits.

## B. Dependency order and honest stop conditions

1. Resolve the actual optional pack first: exact checkpoint rights coverage,
   upstream-authenticated SHA256/length and reviewable runtime distributions.
   PROVENANCE.json deliberately leaves missing fields null. Keep install and
   inference unavailable until this gate is complete. Do not install from a
   mirror or set an arbitrary SHA to make status green. If official provenance
   stays unresolved, research a separately admitted mature restoration model;
   keep this requirement open rather than claiming deterministic sharpening.
2. Implement the adapter/preparation in isolation and retain absent-pack refusal.
   Pin the native scale, architecture, global padding, output transfer, float
   downsample and tile policy. Do not call the existing custom network with
   official checkpoints. A tensor shape smoke check is not quality acceptance.
3. Establish region semantics and coverage review. Whole-image-only neural
   restoration can be explicitly partial functionality, but cannot close the
   four-strength requirement. Missing segmentation must be unavailable or
   clearly manual, never skin masks silently relabelled face/body.
4. Capture the actual current image at full resolution and native precision.
   An original photo may contain existing edits; a returned composite has a new
   effective source hash; a creative document may contain multiple transformed
   layers. Freeze the appropriate *current* rendered source with its graph
   identity, not whichever pathname or thumbnail is easiest. Treat an older
   creative document and newer main-workspace edits as distinct snapshots; use
   the existing explicit fresh-current transition where appropriate.
5. Stage inference/result/fusion off the live graph. Compare at the same source
   coordinates and native dimensions, using current full-quality inspection
   contracts with an actual restored asset. A low-resolution preview may be
   disclosed for display but cannot be substituted for export or full-source
   review. Show interpolation scale separately from native pixel inspection.
6. Apply only after final source/document/revision/token ownership checks. One
   history transaction inserts or updates the real restoration image layer and
   its operation record. Repeated Apply is idempotent by receipt; an uncertain
   send is reconciled, not blindly reissued. Cancel, source switch, close, undo,
   newer edits and stale completion leave the original graph/result unchanged.
7. Reuse existing result-layer alignment/position/size/opacity/rotation. Do not
   count the transform controls as the model feature or add a fictitious
   two-candidate/regenerate UI borrowed from passerby removal.
8. Persist frozen source, masks/evidence, raw restored native-size result,
   parameters/model receipt and layer placement. Asset records and creative
   document/layer schemas currently reject unknown keys; do not append arbitrary
   inference fields into them. Design a versioned operation record and migration,
   reference traversal and snapshot format before integrating. Include hidden
   results and every undo frame in save/recovery/package retention; keep the
   existing blob and manifest size budgets and atomic commit order.
9. Return through the existing original/derived-source contract. Original files
   stay untouched; new-image versus update-original changes only the intended
   source row/history. Reanalysis binds to exact resulting pixels, not stale
   original landmarks. Export renders the same persisted result at full size,
   never a cached comparison preview or a new unstated model run. Opaque-SDR
   guard remains; full alpha/HDR support is still explicitly unfinished.
10. Add recipe/batch work after single-image round-trip is sound. Transfer
    versioned settings/model choice only, re-evaluate every target's source,
    semantic masks and resource needs. Freeze queue identities and expose
    target-specific failure/cancellation, with no live-editor target swap.
    Original and returned rows must both be checked, not accepted because they
    share an original file hash. No hidden background download on queued work.

## C. UNRUN acceptance plan

No listed check was run for this research. These are required future checks,
not passed tests, source coverage assertions or invented numeric thresholds.

| Gate | Evidence required before accepted functionality |
| --- | --- |
| Provenance / offline pack | Exact upstream membership, SHA256 and length; relevant code/weight licenses and notices; pinned authenticated runtime; no hidden auto-download/import side effects; malformed/symlink/unknown files and mismatched hashes rejected before inference |
| Architecture | Strict official params_ema/params load; correct x2 unshuffle/23-block topology; no random-weight success, key dropping or generic pickle execution; malformed keys/tensors and x4-as-x2 misuse refused |
| Input precision | Real RGB8 and RGB16 including dark uint16 ramps <=256, non-sRGB ICC, high-frequency detail and generated floats; no 8-bit staging, value-based bit-depth guess or double divide; zero settings and zero-coverage bytes exactly preserved |
| Alpha / HDR limits | Partial/zero alpha, negative channels, >1 values, NaN/Inf and unsupported ICC/precision are rejected without source change, including exceptional pixels outside requested regions; no flatten/tone-map/clip fallback |
| Source identity | Original/current-edited/returned-composite/current-layer-graph cases; canonical hash and geometry binding; crop/rotation/transform provenance; false original proof, same-sized foreign asset/mask and stale analysis rejected |
| Model numeric semantics | Channel order, transfer, exact scale/output dimensions, right/bottom padding, raw/generated output range statistics and explicit clamp; float-native-size reconstruction compared against an independently inspected pinned forward path |
| Whole versus tiles | Actual admitted weights on small inputs; odd/tiny dimensions, all edges, x2 parity phase, complete halo and downsample support, seams/contrast/hair/text tests; thresholds established before approval; no blanket byte identity claim |
| Resource behavior | Measured peak CPU/GPU/spool/copy bytes for realistic sources including 24 MP RGB16; output/full-buffer admission before allocation; documented performance/cancel granularity; OOM and tile exceptions abort atomically with no partial layer |
| Regional meaning | Whole/face/body/background independently measured and reviewed; clothing/eyes/lips/hair boundaries and unknown class handling; overlapping regions and chosen strength algebra; valid-empty versus missing masks; no person-instance claims from whole-image masks |
| UI / protocol | Genuine before/after asset, native-size zoom, source-coordinate alignment; adjust/review/Apply/Cancel; double click, Back/Close, stale result, interrupted send/reconciliation, source switch, undo/redo and missing-backend states |
| Persistence | Save/reopen/recovery/package with original and derived images, opaque RGB16, hidden result, masks/receipts and every history frame; source hash unchanged; unavailable model retains settings and owned result bytes without rerunning |
| Full export / return | Same frozen source and accepted result in creative view, 100% inspection and final output; proxy-resolution independence; original/new-image return; layer transforms; final format quantization only; existing export-only scaling remains separately labelled |
| Batch / presets | Settings transfer only; target-local capture/masks/model run; mixed original/returned targets, cancellation, stale source, unsupported image/region and insufficient memory per target; no copied source output/masks or false queue completion |
| Photographic quality | Authorized diverse real portraits, clothing/hair, backgrounds, defocus, motion blur, compression, low light, skin tones, group portraits and fine text/patterns; inspect hallucinated facial texture, rings, plastic smoothing, false text/detail and identity changes. Report residuals rather than assert recovery of truth |

A quality comparison against existing Lanczos/sharpen is useful, but outscoring
one metric is not proof of faithful restoration or equivalence to a proprietary
service. Human review and clear learned-detail disclosure remain necessary.

## D. Research limitations / blocked actions

- Official GitHub text/metadata and public guide reads succeeded. One exploratory
  local lookup targeted nonexistent weights.py before locating ops/weights.py;
  the actual file was subsequently read. This was not an access denial.
- No rate limit, security denial or uncertain external mutation was encountered
  in this research. No alternate route was used to evade a restriction.
- Pinning the weights is blocked by absent digest metadata and the instruction
  not to download model bytes. Checkpoint-specific licensing remains unresolved
  in the inspected primary sources; no maintainer was contacted.
- Compatible runtime/install/real inference, source integration, tests, builds,
  typechecks, model quality and end-to-end UI/export verification are not run,
  not pending background processes, and not claimed complete. No extra external
  Codex task was started. Only NEW docs/upscale-research files are owned here.
