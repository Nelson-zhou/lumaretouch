# Portrait-aware crop: integrated source path, acceptance UNRUN

## Exact requirement and scope

Preserved original controls: `control:PC-32478:9` (portrait-aware crop),
`:15` (head-top whitespace), `:16` (head proportion), `:17` (face position),
`:18` (saved crop rules). Official semantics and primary licences are recorded
in RESEARCH.md. These IDs are preserved control IDs, not invented LNX hashes.

The current-photo path is manual-assisted, not automatic crown detection.
The existing installed face model supplies newly measured chin/face-center
proposals on a hashed display proxy of the complete edited source. The user
selects the intended person and explicitly marks/reviews the actual crown,
chin and center. No original pre-edit landmarks are reused across deformation.
The original Rust scalar planner produces a bounded rectangle, not new pixels.

## Stable module boundary

- `core/portrait_crop`: separately packaged GPL-3.0-or-later scalar planner,
  ABI 1 and capabilities 15. Missing/mismatched library refuses this operation.
- `portrait_crop_state/native/planner`: versioned geometry contract. The prior
  `lnx.crop.v1` sampler and persisted crop state are unchanged.
- `portrait_crop_capture/review/project`: immutable complete edited-source,
  fresh model proof, exact full before/after rendering and candidate binding.
- `portrait_crop_controller/host`: serialized service and read-only cancellation
  events; bounded engine-lifetime request identities and image leases.
- `portrait_crop_engine`: existing crop geometry, one document fence, existing
  history record and normal project/autosave state. No second undo owner.
- `portrait_crop_routes/recovery`: global uncertain-write admission, verified
  reopen boundary and terminal-only recovery revision accounting. A provisional
  unknown receipt does not taint a later confirmed successful apply. Query may
  clear only the exact crop-owned taint and matching current-workspace receipt.
- Native mailbox and UI module: exact original request echoes, real source and
  before/after PNG proofs, manual ACK, bounded polling and query-only recovery.
  Read cancellation means a request until the original computation unwinds.

Registration uses the existing command catalogue, reader control lane, native
engine epoch, dedicated Tauri API and an app-lifetime workspace component.
The old crop/rotate modal remains available and unchanged. The new module does
not depend on hair-volume integration and may be captured independently.
This is built-in replaceable module registration, not runtime plugin loading.

## Honest limitations

- The official full automatic AI experience is not accepted or reproduced.
  No skull/hairline/ear reconstruction or hidden-anatomy inference is claimed.
- Nonzero existing rotation is explicitly refused. The old sampler crops before
  rotation; the module does not silently reset rotation to fit a proposal.
- Rule ranges, denominator and horizontal-axis convention are original local
  design choices because official documentation does not publish them. Vertical
  face position is implied by crown, headroom and head proportion, not a falsely
  independent slider. Requested and integer-rounded achieved values are distinct.
- No padding, content generation or silent rectangle clamp. Infeasible requests
  remain rejected with their original intent intact.
- Crop-rule preset saving (`:18`), batch/cohort transfer and arbitrary-rotation
  composition are unfinished. This slice does not claim them as supported.
- Existing opaque SDR full-candidate source/budget limits remain. RGB8 review
  images do not claim RGB8 master precision, HDR/alpha support or 24MP acceptance.
- Verified reopen recovery is scoped to the same live native engine epoch. An
  ended/replaced engine cannot establish the old request outcome; that historical
  uncertainty is not automatically cleared by context changes. An explicit app
  restart and authoritative saved-project reopen is a separate recovery boundary,
  not evidence the old write failed or succeeded. No cross-epoch reconciliation
  is claimed.
- No numerical parity, runtime, performance, UI or photographic quality acceptance
  has been performed. Tests and native build commands are AUTHORED / UNRUN.
