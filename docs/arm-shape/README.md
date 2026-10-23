# PC32473 arm family: source-integrated, runtime and quality unaccepted

## Exact baseline and primary semantics

- Feature: `PC-32473`.
- Original control: `PC-32473-C-5d25f1744f`.
- Original requirement: `LNX-REF-PC-32473-C-5d25f1744f`.
- Original control path: `AI瘦手臂&瘦手臂`.
- Related module case: `PORTRAIT-008`, which is NOT evidence that this specific
  subcontrol has been implemented or accepted.
- Original map entry: `AI开发资料包/功能需求验收映射.json`, around lines 5100–5110.
- The Linux guidance/manual is a roadmap, not permission to pretend source work
  is a working commercial clone. Preserve its required arm family, not a new one.
- Mapped original source: https://www.pixcakeai.com/guide/32473
- Official current explanation, inspected 2026-10-23:
  https://wiki.pixcakeai.com/guide/9412.html, arm subsection.

The official explanation says both modes adjust arm lines. The AI mode focuses
more on arms, affects other body regions less, and permits left/right unlocking.
It does not disclose the arm slider's numeric range, neutral/default, sign,
segmentation architecture, learned deformation weights, hidden-joint policy or
pixel-for-pixel output. Those must not be invented as official specifications.

Our 0–1 parameter (UI 0–100), zero default, positive thinning, default unlinked
editing, nine cross-sections, 0.22 numerical gain, 1.8/1.4 falloff multipliers,
visibility thresholds and partial upper/forearm policies are explicitly ORIGINAL
implementation choices. Independent ordinary-mode controls are a local usability
extension, not a claim that the commercial ordinary mode has that exact UI.

## Honest status

Status: SHARED SOURCE INTEGRATION AUTHORED; RUNTIME/QUALITY NOT ACCEPTED. The
arm workspace, native mailbox, server command, shared render/export consumer,
project/history validation and package stage now have actual source routes.
Registration is NOT a claim that the product was executed or accepted. There is
no screenshot, tested output, installed-model claim, image quality pass or
pixel-perfect commercial parity claim.

Performed only source reading/editing, primary-source reading, Python/TypeScript
syntax-AST inspection, JSON inspection and file hashing. No product imports,
execution, tests, Rust compiler, typecheck/build, inference, installs, software/
model downloads, Git writes or external Codex were performed for this arm work.
Shared source edits were explicitly granted for this integration turn.
Root owns commits/pushes; Qoder owns later local execution and photographic review.

Static inspection found the normal user-data SAM install receipt absent in this
executor. That is a limited filesystem observation, not a statement about every
user machine or an exhaustive environment status. The producer fails visibly if
its already admitted optional extension is absent or mismatched. Nothing here
installs, downloads or substitutes a new model.

## Actual ordinary-versus-neural strategy difference

There is ONE visible family `lnx.arm_shape.v1` and one strength per internal
side/segment. A segment stores exactly one actual strategy and one support pointer:

1. `reviewed-contour`: 18 explicit source-image silhouette clicks (nine measured
   transverse distances on each side). No prefilled contour values are admitted.
   The reviewer sees actual shoulder/elbow/wrist points, measured contour markers,
   transition markers and ownership/exclusion rectangles.
2. `sam2-prompted-contour`: calls the existing `prompted_mask_source.Predictor`
   against the bound canonical source. Real visible joint centres provide only
   positive prompts along the actual segment; the explicit reviewed ownership
   window and exclusion regions guide the generic model. The model produces
   three actual image-conditioned masks. Every mask remains visible, including
   rejected candidates. The user chooses a valid candidate and reviews it. Widths
   are traced from that exact binary mask, not entered manually, copied from pose
   ratios or fabricated when inference fails. The same numerical kernel can use
   those genuinely different contour inputs with a tighter local transition.

SAM2 is a generic prompted object selector, NOT an arm semantic classifier. The
implemented AI path is an ASSISTED IMAGE-CONDITIONED PROPOSAL. Fully automatic
arm-semantic segmentation remains an explicit gap. A full-person or torso-leaking
candidate is refused, never clipped into an arm and then called segmentation.
A failure does not call the manual kernel under an AI label. No trained arm
geometry network or commercial smoothness parity is claimed.

The retained selection includes exact source file/dimensions/orientation, BodyRef,
full pose-point digest, candidate index, prompts/box, actual inference input hash,
pinned checkpoint/config/code identity, installed runtime inventory digest, actual
CPU/CUDA/ROCm device, model score, lossless actual binary mask/hash, observed
ownership snapshot and derived widths. Model score is explicitly NOT an arm
recognition confidence. Export/reopening verifies the exact inference input hash
from canonical full-source pixels. Replay uses the retained reviewed mask, does
not claim new inference, and does not require reinstalling model weights.

The mask is bit-packed/base64 in bounded 4096-character chunks inside the shared
immutable support envelope, not a cross-photo binary cache. A source edit, changed
pose, candidate, model, mask byte, contour measurement, strategy or ownership
snapshot invalidates its corresponding fences. The original RGB8/16 is retained;
SAM's admitted RGB8, long-edge-2048 input conversion is for selection only.
Inference-scale boundaries are not native-resolution anatomical ground truth.

## Model source, checkpoint license and existing supply-chain boundary

Only reuse the already admitted optional SAM2 extension:

- Code: https://github.com/facebookresearch/sam2/tree/2b90b9f5ceec907a1c18123530e92e794ad901a4
- Upstream README: https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/README.md
- License: https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/LICENSE
- Checkpoint: `sam2.1_hiera_tiny.pt`, 156,008,466 bytes; pinned metadata revision
  `36f406a75c9be63c7f429da63246273f028c6fd4`.
- Weight SHA-256:
  `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`.
- Source config SHA-256:
  `f932eac1c6241e910031b2f000a81cd9f8a8d4896e2277ab5ffb721f378b188d`.

The pinned upstream README expressly licenses both model checkpoints and code
under Apache-2.0. The upstream demo fonts are not used. The existing archived
license, README and config were inspected and their SHA-256 values match
`docs/model-licenses/sam2.1-hiera-tiny-provenance.md`:

- License: `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.
- README: `eea69ee1042fb30933c5ca5019fbf0f6f9366cec5e792109281b5023a4f1589c`.

Reuse existing notices/license distribution, no new vendor code or weights here.
The producer verifies and consumes the SAME checkpoint/config bytes, and verifies
the installed source/runtime inventory. The pinned source archive digest remains
installation-observed, not a pre-reviewed archive hash; ancillary installed
packages are not a new hermetic lock. Arm work does not silently strengthen those
claims. No model inference or license-enforced install was run here.

## Visibility, ownership and unsupported scenes

Static shared required-anchor policy is preserved via four internal operations:

- `lnx.arm_shape.left_upper.v1`: actual landmarks 11→13.
- `lnx.arm_shape.left_forearm.v1`: 13→15.
- `lnx.arm_shape.right_upper.v1`: 12→14.
- `lnx.arm_shape.right_forearm.v1`: 14→16.

These are policies inside one arm family/requirement, not four invented features.
One visible forearm can work while its hidden upper segment and other arm remain
neutral. Linked/whole-arm requests require every requested segment's own matching
strategy support/review. If one fails, the whole candidate refuses before publish.
No fallback to whichever arm happened to pass. An explicit zero does not need
hidden anatomy, model installation or a native load.

The reviewer must confirm actual visible endpoints, entire segment visibility,
no crossing, no strong foreshortening, clear torso contact border, single-person
ownership, visible skin/sleeve material only and reviewed transition pixels.
Occlusion, low confidence, crop, short source geometry, depth ambiguity, folded/
self-overlapping arms, ambiguous inter-person ownership and unclear torso-contact
borders are not reconstructed or repaired. Loose sleeves mean visible sleeve
contour shaping, never anatomy beneath fabric.

Automated rejection is deliberately conservative:

- Actual mask pixels outside the explicit ownership window or in exclusions fail.
- When all actual torso-corner points are reliable, any mask intersection with
  their observed torso polygon fails. Missing torso points are NOT fabricated;
  explicit visible-source contact/ownership review is still mandatory.
- Actual other-body observation boxes and retained faces reject selected pixels.
  Replaying requires the same live observation snapshot. Detector census is not
  complete and is never represented as proof that no undetected person exists.
- Gaps, disconnected transverse pieces, missing axis foreground and unbounded
  contour cross-sections fail. A candidate is never repaired by erasing evidence.
- The actual field's conservative support disks reject known other bodies/faces
  and explicit exclusions; observed opposite-arm axes and sharp folds can refute
  safe ownership. Conservative disks can reject otherwise plausible cases.

Arm focus is relative, not perfect isolation. Background and garment texture in
transition support may move. Boundary fixtures, patterned backgrounds and contact
poses must be reviewed locally; do not promise zero damage or naturalness yet.

## Geometry, preview, masks and export ports

`core/arm_shape/lib.rs` is a small original dependency-free Rust ABI. It evaluates
compact smooth inverse fields at actual requested coordinates. Contour profiles
use C2 interpolation and side-specific radii; joint/end taper is C2 identity.
Python admits source/review/ownership, packs original/render pixel geometry and
exposes `evaluate(points)`, `resident_bytes()`, `shape`, actual support bounds,
source record, exact input-binding digest and conservative maximum displacement.
The field is not an image warp. The registered render coordinator supplies actual
leg fields and preserves independent hair/effect inputs; it does not import an
inactive consumer merely to advertise support.

`arm_shape_adapter.prepare_common` supplies actual arm subfields to the existing
canonical per-BodyRef chain. `body_pose_geometry.effective_order` is now the one
ordering authority: v1 shoulder-only if legs/arms are neutral; v2 shoulder→leg if
legs are active but arms neutral; v3 shoulder→leg→left upper→left forearm→right
upper→right forearm when any arm segment is active. In every case the actual
body inverse precedes the shared face inverse. Installing or reviewing a neutral
arm does not relabel the older geometry identity. Unknown enabled intent still
refuses rather than disappearing.

`body_pose_render.prepare` gathers actual leg subfields and the arm adapter adds
actual arm subfields; the common shoulder adapter validates exact active intent
coverage and composes once. The common layer retains prepared binding/source,
association, memory, support-overlap and Jacobian guards. Off-grid composition
evaluates the next subfield at already displaced coordinates. No sum of separately
sampled maps, duplicated BodyRefs or repeated RGB sampling is allowed.

Preview and export replace the shared prepared geometry only. The canonical common
map must be used once for RGB8/16 and consistently for semantic/recovery masks and
retouch deltas. Original-resolution export rebuilds fields and verifies full-source
selection pixels rather than enlarging a preview map. For both RGB8 and RGB16
output, active SAM replay uses the same canonical true-bit-depth/ICC source decoder
as the proposal, not the output-bit-depth buffer (particularly RAW and high-bit
TIFF to JPEG/PNG). Its extra full-source allocation is explicitly budgeted. This
verification invokes no model and does not replace the export source. Preserve independent hair,
face, leg, shoulder and late-colour effects in their existing host paths.

`publication_receipt` requires the actual prepared common-map object and actual
rendered pixels after publication. It records the map hash, output hash/type,
source/render dimensions, one source sample and exact body operation order. Merely
constructing a field, sending a request or returning a placeholder cannot claim a
published preview. All receipts keep `runtime_quality_accepted=false`.

## Registered host and UI source contracts

These source routes are connected; runtime behavior and quality remain UNRUN.

- `ArmHostAdapter`: atomic batch recipe/support review/enable mutations using the
  real host lock, exact document epoch/revision, source, BodyRef, full body/people
  graph digests and association revisions. Host `prepare` must produce actual
  common geometry. Host `publish` must atomically retain bank/history and publish
  either actual prepared output or an explicitly original/unapplied correction.
- A bounded private per-engine-epoch journal fsyncs an atomic receipt claim before
  publication and retains the actual result. Duplicate identical IDs query it;
  changed-content ID reuse fails. Initial pending claims conservatively remain
  unknown if the terminal write is lost. Post-rename sync failure keeps the
  in-memory content index consistent with the observed file. A local publication
  verification rejection cannot be overwritten by an older pending record.
  Reconciliation checks both operation family and exact request digest against
  the canonical body owner's actual frame/history outcome. Process restart uses
  a new document epoch; this is not a restart replay queue or proof that an old
  uncertain publication succeeded.
- `ArmProposalHost` and `ArmProposalJobs`: host validates the same envelope and
  supplies its own canonical source path plus actual source ownership evidence.
  The client supplies only segment, region and explicit device. A spawned owned
  read-only process calls actual SAM inference. It uses the existing fail-closed
  cgroup-aware RAM admission (source buffers plus 2 GiB reserve), admits one active
  owned model job at a time, binds parent death and imposes CPU/wall 180-second
  deadlines. This is not a measured GPU-peak guarantee. Registered read-only
  admission refuses overlapping image/model jobs and active inspection work,
  preserving their captures instead of cancelling unrelated reviews. Other
  mutating/resource work cancels only the owned arm proposal. Validated selected
  masks are retained before releasing the model allocation and preparing the
  common map. Query/cancel/release are explicit;
  cancellation IDs remain tombstoned. Popup/source replacement requests release;
  engine shutdown closes the owner and parent-death binding fences orphan work. Bounded
  atomic result files avoid partial-frame pipe/queue deadlocks if a worker is
  killed during delivery; no blocking result pipe is read under the host lock. No installation is triggered.
- Bind `HostPorts.proposal_get` to the verified proposal host's status lookup.
  Neural review refers to a completed retained job/candidate, not caller-supplied
  masks or widths. Raw manual review cannot manufacture an AI receipt.
- Registered native command: `arm_shape`, with exact outer request ID plus one
  of `view`, `select`, `execute`, `status`, `proposal_start`, `proposal_status`,
  `proposal_cancel`; native `mailbox_status`/`release` never re-enqueue work.
  Edit and proposal inner IDs differ from transport IDs. Replies are
  `arm_shape_result` protocol 1. Execute/status return the actual inner receipt;
  view/select return the canonical source PNG; proposal routes return actual
  proposal results. Native validates the bound graph, source, body, masks and
  receipt identity, retains process-lifetime tombstones, reserves a cancellation
  slot and fences engine replacement. Read-only requests do not invalidate
  existing capture lifetimes or advance image/document state.
- `ArmShapePanel` and `ArmSupportEditor` require a host-provided actual view and
  a preview explicitly bound to the unedited canonical source, not the retouched
  effect preview. They show per-side/segment status, strategy, scoped linking,
  real masks and reviewed contour/transition markers. Actual mask bytes/hash are
  verified before its review button enables. Stale source/body/person contexts
  cancel unapplied work and never substitute fake successful previews.
- Panel controllers must live at app/document lifetime, not per popup. Closing a
  popup must not lose an uncertain mutation ledger. New target selection fences
  old responses; latest unsent edits may coalesce, uncertain edits never resend.

Actual shared source integration includes `body_pose_operations`, the one body
ordering authority, `body_pose_render` and `body_pose_host`, all `people_owned_inputs`
preview forwarding, original export preparation, native router/lifecycle/ready
capability, app-lifetime arm controller/proposal owner, source preview acquisition,
existing body-family workspace, exact requirement routing, shared gesture history
and distributor stage. No common validation was weakened. The original Rust ABI
is staged with original GPL source and existing MediaPipe/SAM notices; no model
or runtime installation occurs during startup or package staging.

## Durable state, history and cross-photo intent

Use the existing BodyRef bank v2 / project container v14 (preserving v13 read
compatibility). There is no alternate
arm-person bank. Immutable support assets are source/operation/body/point-digest
owned. Parameter intent may survive reanalysis, but old reviews/assets/association
must not be rebound to new observations. Every project and undo/redo/export tree
must be validated before live mutation through `validate_project_records`.

Family history patches preserve unrelated operations, body observations,
associations and append-only assets, with exact people/protected-graph digests.
Replay refuses changed graph/recipe/ownership rather than reidentifying people.
Cross-photo transfer requires explicitly confirmed same anonymous person, current
source/target graphs, and target-owned matching-strategy support/review for every
named segment. Only recipe intent transfers. Source masks, geometry, support,
visible-joint authorization and stable identities never cross photos. The host
must prepare the entire target candidate before publishing it. The explicit
intent-transfer helper is a guarded port, not an automatically enabled generic
batch/preset operation. Existing generic scopes do not copy the body bank, poses,
reviews or arm masks across photographs; existing hair and semantic batch/preset
behavior is preserved.

## Local acceptance handoff

`engine/tests/fixtures/arm_shape/acceptance.json` contains separately numbered
AUTHORED UNRUN cases mapped to the exact original requirement. Python and TypeScript
contract tests and Rust inline tests are authored, not executed. Synthetic masks
and all-zero-confidence synthetic observations are schema/negative fixtures, never
real MediaPipe/SAM outputs or evidence of photographic acceptance.

Local work must compile/package the original Rust ABI, run tests and UI checks,
exercise native/IPC/history/project/export lifecycles, run the admitted installed
model on permitted real portraits and inspect final-resolution pixels, masks,
backgrounds and visible sleeve contours. Include single-visible-arm, partial
forearm, linked bilateral failures, candidate contamination, two-person/contact,
RGB8/16, proxy/export equivalence, no-source-resample duplication, cancellation,
lost replies, late stale responses, document close, reopen and transfer. Preserve
actual input/output/model/runtime receipts and screenshots with accepted cases.
Every case remains UNRUN and quality NOT_ACCEPTED until those results exist.
The expanded fixture has 64 cases, including registered routes, shared-map
identity, real mask replay for high-bit sources exported as RGB8, native loss/
cancel races, journal faults, cross-family request collisions, and v14 reopen.

## Static review corrections before freeze

A separate source-only review identified lifecycle defects that were corrected
before this manifest: repeated/stale result reconciliation, missing document
clear, cancellation racing a delayed start, and queue delivery after a killed
worker. The final protocol uses bounded atomic result files, retained bounded
cancellation tombstones/closed-owner fencing, and original-request guards. Slider
interaction retains a single gesture ID; history stores only changed-operation
referenced support assets. These are inspected source corrections, NOT test passes.

## Shared integration review corrections

Source-only review additionally caught and corrected: post-rename journal index
drift on failed fsync; a pending claim that could hide successful publication
after a lost terminal write; loss of a publication-verification rejection during
receipt recovery; cross-family request-ID reconciliation; and RGB8 export of
RAW/high-bit sources using a different selection input than the original SAM
proposal. Read-only proposal admission now refuses conflicting allocations without
discarding captures. These are source corrections, not executed fault-injection
passes. The exact frozen changed-file manifest records the final source bytes.
