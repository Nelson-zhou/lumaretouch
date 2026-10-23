# M14 derived-source body acquisition, review and export

Source-only continuation of `fb75d09ce4252afebeed850e6c2aed0e0af28dd8`.
Product imports/execution, native builds, tests, type checks, inference,
photographic/numerical/visual acceptance: **UNRUN**. This is not whole M14 or
32-tool acceptance.

## Handbook scope

Return `LNX-REF-WF-127932-a9c143a25d` and recoverable history
`LNX-REF-WF-127932-c7783ea5fb` now feed the existing measured-body owners.
Manual baseline lines 560–565 lists body shaping controls; existing exact IDs:

- Shoulder square `LNX-REF-PC-32473-C-1b5aae1f25`; width `57c31b17e1`.
- Slim legs overall `LNX-REF-PC-32473-C-6519e4b67b`, thigh `2cebb24a12`, calf `c63c7afe15`.
- Arm `LNX-REF-PC-32473-C-5d25f1744f`; waist `8268ea3e37`.
- Neck length `LNX-REF-PC-32473-C-903ca47834`, width `614d728bcd`.
- Leg length overall `LNX-REF-PC-32473-C-d79658697a`, thigh `eefc19db17`, calf `17fb085b4c`.

Short suffixes above share `LNX-REF-PC-32473-C-`. No new body algorithms,
anatomical measurements, hidden-part completion or generation are claimed.

## Actual pixel ownership

`body_pose_commands` supplies `creative_derived_source.analysis_rgb`, not original
`_src_rgb` relabelled with a composite ID. Acquisition freezes source/document
binding and verifies returned source, actual submitted RGB8 hash, input extent,
and unchanged current pixels before publishing observations. Existing MediaPipe
33-point evidence, visibility/presence thresholds, model hashes, explicit BodyRef
selection/replacement and incomplete-census limitations remain authoritative.

`creative_derived_body` admits exact native envelopes for six existing command
families. Native review, numerical validation, target/graph/association fences,
receipts and publication remain the only edit owners. All retained records,
census keys and support assets, including disabled/dormant intent, must belong to
the effective source. Query/cancel and exact retained receipts remain reachable
without creating a new mutation. No raw mask or source path is accepted from UI.

Existing review panels now say current source rather than incorrectly implying
the physical original. Their images are unedited effective-source references;
body geometry still displays in the existing edited main canvas.

## Immutable arm SAM input

`creative_derived_arm_input` makes a distinct model-only representation from the
full canonical working-sRGB float32 source. It refuses alpha/HDR through the
existing canonical decoder, rounds opaque SDR to RGB8 with explicit half-up
quantization, then applies the existing pinned whole-frame LANCZOS long-edge
2048 transform. Full float render pixels are not replaced with this input.

An immutable packet owns source ID/extent, transform version, dimensions, byte
hash and existing SAM input hash. At most 12 MiB RGB8 bytes are cached for the
current canonical ID/transform, never a 24 MP float buffer per history state.
The private worker directory receives those bytes, not the original pathname;
the child validates descriptor, bounded regular file size and hashes before the
existing predictor runs. Model/config/runtime hashes, device receipt, actual
candidate masks, measured contour refusal, scope/exclusion review, cancellation
and parent-death behavior remain unchanged. No automatic installation/download.

Preview replay validates that packet; full-resolution export repeats the same
model-only transform on the actual canonical float source and checks the retained
SAM input hash. Original RGB8/RGB16 decode remains unchanged. SAM resolution is
not native-resolution anatomical ground truth. Memory admission remains bounded;
no global budgets were raised and no 24 MP performance acceptance is claimed.

## Export, common geometry and history

`export_snapshot` captures body state for both original and derived sources.
`body_pose_source_proof` separates effective immutable content from physical
original provenance. The latter still anchors relocation/change checks, but is
never a derived model input. Body-only exports receive a correctly bound empty
portrait owner rather than borrowing another document's faces. Frozen target
state/private owner is used, not current live document identity.

`creative_derived_body_export` validates body bank/extent against the canonical
asset; original digest/stamp changes still refuse. The canonical export resolver
stamps an ephemeral row-wise full-float pixel digest immediately after decoding;
body preparation verifies it. This is internal exporter ownership, not a public
API to authenticate arbitrary supplied arrays. No ephemeral proof enters history.

`people_owned_inputs` and `people_engine_runtime` forward checked body ownership,
pathless SAM replay inputs and all existing hair/makeup/recovery banks. Existing
Rust body evaluators and the canonical body-then-face inverse composition remain
unchanged: no extra bitmap warp, proxy field enlargement or original mask copy.
Full float export and fresh-current creative capture use that same route.

Source-switch history uses full per-source snapshots, never a sparse patch
between sources or a union of original and derived support banks. Same-source
sparse history is preserved. Restored revision/association fences remain
monotonic. Saved history validation now includes unreferenced support source IDs,
so dormant foreign-source assets cannot hide through save/reopen.

## Integration map and verification

- Host admission: `creative_document_host` → `creative_derived_body` → native body transports.
- Acquisition/reference: `body_pose_commands` → actual derived analysis RGB → existing pose producer.
- Arm proposal: registered host → immutable packet → existing owned worker → existing reviewed candidate.
- Preview: `people_owned_inputs` → `people_engine_runtime` → `body_pose_render` → existing joint native map.
- Export: `export_snapshot` → proof/decode checks → canonical export source → pixel stamp → people/body preparation.
- History: host passes pre-restore source state → `body_pose_document_history`; no new undo owner.

Authored UNRUN fixtures: derived body commands, immutable arm input, body export,
body history, runtime forwarding; existing derived-effects forwarding fixture
updated to a canonical empty body bank. Static Python AST and source whitespace
checks only. Actual models, native geometry, file export, project/recovery/package
roundtrips, cancellation, two-body overlap and 24 MP memory/performance need the
external local QA owner. UI text edits were not built/typechecked/rendered.

## Remaining boundaries

- General local masks and prompted hair masks still use original-file source
  contracts and remain fenced. This arm-specific packet does not admit them.
- Global/body effect recovery, repair/inpaint/source patches, lighting and other
  unadapted effects remain fenced; existing face-only recovery scope is unchanged.
- Cross-image/shared-person transfer and generic batch remain fenced until each
  target owns actual analysis and explicit identity review. No source masks copy.
- Transparent/HDR photo return remains explicitly refused, never flattened/clipped.
- Missing optional pose/SAM dependencies, insufficient memory, occluded/ambiguous
  joints or unsupported measured contours produce explicit refusal, not fallback.
- Body field quality and all runtime acceptance remain unverified.

## Primary practice and licensing

Google's [Pose Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
uses actual image/NumPy input wrapped as an sRGB MediaPipe image and exposes
pose-count/confidence controls. We preserve those actual-input semantics rather
than deriving a body from face boxes.
The [pinned SAM2 predictor](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/sam2/sam2_image_predictor.py)
specifies RGB image input in HWC form and values in [0,255]. The 2048 cap and
half-up float bridge are this application's explicit model-input policy, not an
upstream full-float guarantee. Existing pinned model/config and archived notices
in `docs/arm-shape/README.md` and `docs/model-licenses/` remain unchanged.
No new upstream code/model was copied or downloaded. Existing original Rust
consumers are reused; no new third-party licence surface was introduced.

## Subsequent source adaptation

[Derived local masks](DERIVED-MASKS.md) records the next source-only slice and
remaining repair/shared-transfer boundaries. This body slice remains historical.
