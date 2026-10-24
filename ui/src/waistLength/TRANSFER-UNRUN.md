# Waist scalar transfer UI/native source implementation

Requirement `LNX-REF-PC-32473-C-5d33f285bb` remains PARTIAL / UNRUN.
This is authored source wiring, not an execution, image-quality, browser or
full-resolution acceptance claim.

## Implemented source paths

- Existing preset/batch workflows now route exact `lnx.waist_length.v1` alone.
  The UI only offers the scope when the engine reports it transferable. Mixed
  scopes and people/local-mask/reference/XMP transfer combinations are refused.
  Bulk preset selection excludes both exclusive body-length scalar scopes.
- Portable data is only `{version:1, amount}`. `waist_transfer` is frozen,
  target-owned review evidence, not preset data. The current target must supply
  its own single enabled body, four waist markers, waist-specific reviewed
  support and own-face association. The engine verifies those dependencies;
  UI/native validation checks exact proof shape, identities and bounded images.
- Shared `bodyScalar/transferModel.ts` and `BodyScalarTransferReview.tsx` retain
  the torso public interface while avoiding a copied workflow or renderer.
  The waist review key adds its operation namespace and includes the preflight
  token/request, current source/body/face/support/bank identities and both PNG
  digests. Each target needs both PNGs verified, browser decoded with exact
  dimensions, and its own explicit checkbox. These are full canonical-chain
  before/after render thumbnails supplied by the engine, not waist diagrams.
- The UI/native command uses `waistReviewAck`, serialized as `waist_review_ack`.
  It is distinct from `torso_review_ack`. Pending UI state deep-copies ordered
  acknowledgments; native command registration binds the original request,
  scope, token and acknowledgment list in the existing receipt host. A success,
  unknown or claimed receipt must match them. An explicit unclaimed no-write
  rejection can omit accepted identity only when it contains no mutation
  evidence. Neither query endpoint resubmits a mutation.
- Uncertain waist application/commit cannot be released through the ordinary
  inspect-and-end button. It remains query-only. Important residual: the
  current native query reads the retained mailbox, not authoritative engine
  reconciliation. A malformed/lost terminal receipt may remain uncertain;
  repeated polling is not a promise that it will resolve. There is no blind
  replay, cancellation claim or manual uncertainty bypass in this addition.

## Source-only fixtures

- `transferModel.unrun.test.ts`: scalar-only proof, target/source/body/own-face
  identity, review-key invalidation and operation isolation, image shape and
  digest verification, ordered acknowledgments, explicit no-write rejection.
- `transferWorkflow.unrun.test.ts`: preset and batch route/gates, distinct fourth
  batch acknowledgment argument, mixed-scope refusal, stale/dismissed context,
  original receipt binding, uncertainty preservation and query-only behavior.
  Workflow image payloads are synthetic metadata fixtures, not valid rendered
  photographs. Mock transport recovery does not establish mailbox recovery.
- `ui/src-tauri/src/waist_transfer_protocol_tests.rs`: distinct acknowledgment
  family, shared proof/PNG validation and scalar-only parameters. Its borrowed
  tiny PNG fixture is synthetic transport input, not waist-quality evidence.
- Existing torso source-shape assertions follow the shared renderer; torso
  operation ID, acknowledgment field and three-argument call compatibility are
  retained. The UI test list has not been silently broadened or executed.

## Still requires authorized execution and physical acceptance

Typecheck/build, Rust and UI tests, live engine/bridge behavior, both PNG display
failures, changed bytes with unchanged hash, slow image decode, checkbox reset,
repeated click, cancel/Escape/reopen, document/row/revision/source change, stale
markers, more than one enabled body, missing own face, original and derived
sources of different sizes, unknown terminal and rejected rollback, exact scoped
group undo/redo, unrelated body operations, project reopen, real portraits and
genuine full-resolution before/after comparison are all UNRUN.
