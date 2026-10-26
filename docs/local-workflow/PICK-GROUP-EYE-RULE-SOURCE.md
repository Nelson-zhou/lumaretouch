# Detected-group closed-eye hint exception — SOURCE ONLY / UNRUN

Date: 2026-10-26. Base: local `a8f3f70b096e77515f0995b72fe7678ae58cb8f3`,
matching published tree `0a1056485633b11b311fb9a60b4f01a492c86c93`.
Requirement: `ui/src/spec/workflows.json` workflow:230984, original AI挑图 rules
at lines 125–135; this implements ONLY the optional detected-face-count exception.
It does not satisfy the full AI-selection workflow or its laughter/sharp-face rules.

## Contract and authority

* Rule: `{version: 1, more_than: null | integer 1..31}`. Absent old settings and
  `null` mean **disabled**. Other versions, unknown fields, booleans, fractions,
  zero and thresholds >=32 are rejected. This is session-derived hint state,
  not a project edit, persistent preference or global default change.
* The sole group comparison is Rust `core/pick_group_eye/lib.rs` ABI1. It omits
  only if verified detected count **> N**, never >=N. Unknown count cannot omit.
  An observed 32 faces can establish >31 even at the detector cap, but cannot
  establish the actual number of people. Cap32 and possible misses are visible.
* Python preserves existing eye-aperture thresholds and other hint authority.
  No second Python/TypeScript >N decision exists. Rust missing/ABI mismatch is
  explicitly unavailable and retains the existing closed-eye hint. Default-off
  does not load the optional native library. No dynamic build/install/download.
* No laughter classifier, sharp-face blur exemption, focus inference, quota,
  aesthetic/scene/front-face score, best-pick selection, AI percentage, identity
  recognition or full people census. Existing proxy focus is not sharp-face truth.

## Real evidence, not old face metadata

`server._pick_measure_one` captures proof from the same `pc = fn(rgb)` used to
compute the minimum eye aperture. It counts only `pc.all_landmarks`, requires
real `mediapipe`, consistent native `num_faces`, 478x3 finite points, no manually
appended faces, detector cap32 and actual `detector_model_sha256` supplied by both
the result and loaded backend. Existing `face.py` hashes the exact immutable
model bytes supplied to MediaPipe; it is unchanged by this patch.

`Measures.face_detection` records schema/status, detected count, cap/reached,
backend, actual detector SHA256, resolved model path/stat, source path/stat,
decoded dimensions/origin and the matching eye aperture. A bounded read hashes
the current model bytes and verifies they equal the loaded model. No face or
failed detection yields no usable proof, not count zero. Synthetic/template,
legacy `faces`, row metadata and a different eye sample cannot enable the rule.

Model/source staleness, missing fields or mismatched aperture/dimensions are
unknown/refused. Cache reuse and cached rule evaluation rehash model bytes;
publication rechecks. Session presentation uses source/model stat fences and
hides known stale hints. Source stat `(dev, ino, size, mtime_ns, ctime_ns)` is a
best-effort change fence, NOT a source-content hash or atomic filesystem snapshot.
Concurrent external writes after a check cannot be ruled out. Model runtime
accuracy, possible missed faces and false positives have not been validated here.

## UI and cache lifecycle

The visible `PickGroupEyeReview` sits beside the existing OriginalFocusReview in
library controls. It shows only eye-rule evidence/status; it does not expose a
fake full AI picker. Draft changes are labelled unapplied and do not change hints.
The user explicitly applies the rule to 1–8 visible selected documents, submitting
indices **and exact document IDs**. Hidden/changed selection is refused. No
selection, active document, flag, rating, label, trash, edit/history, source file
or original-focus crop is changed by this action.

`pick action=group_rule` only uses existing fenced measurements; it never calls
a decoder or constructs/runs a detector. It replaces eye reasons/labels and the
rule state, preserving non-eye hints and human decisions. Missing/old/stale
cache is cleared with an explicit unknown/error; it does not schedule inference.
Changing N, enabling or disabling recomputes immediately on explicit application.
Disabling restores the normal threshold-derived closed-eye hint from the same
measurement. Rule failure never certifies open eyes or analysis success.

The separate **重新测量…（例外关闭）** button explicitly invokes the EXISTING
FaceMesh/proxy-measurement pipeline with default sensitivities and force=true.
It resets freshly measured selected source hints to disabled; other reused
cache rows retain their own applied rule. Legacy measurement publishing is
source-path keyed: a new identity-bound request for a non-first virtual-copy row
is refused rather than silently writing onto a different document. It measures
the source, not edited virtual-copy output. This patch does not redesign copies.

The pick measurement algorithm/fingerprint advances to v4. Old v3 caches are
not reused. Rule settings and state are serialized with each hint. Omission is
explicitly `eyes_omitted_by_rule`, never an eyes-open/pass label. Unknown and
native-unavailable states are visible; `suggest=none` means no review labels,
NOT quality accepted. Existing `auto_deleted=false`, `auto_trashed=false`,
`overridable=true` and current human-mark precedence remain intact.

## Packaging and verification boundary

`build-pick-group-eye.sh` authors a dependency-free rustc cdylib build, wired into
existing stage-engine packaging with GPL source/notices. No external crate, new
model, package acquisition or runtime compilation is added. The script was NOT
run; no native binary has been produced or installed by this change.

Only source inspection/edits, Python AST parsing, JSON syntax and whitespace
checks were performed. No product imports, pytest, Rust tests, typecheck, build,
app launch, inference, calibration, image measurement or installation ran.
`core/pick_group_eye/tests_unrun.rs`, `engine/tests/test_pick_group_eye_unrun.py`
and `ui/src/pickGroupEye/model.unrun.test.ts` are authored **UNRUN** fixtures.
Dummy model/photo bytes and fabricated point arrays in fixtures are contract
inputs only, never claimed detector or photo evidence.

Qoder's later authorized checks must cover: off/default/old settings; N-1,N,N+1;
cap32; missing/no/failed/stale detection; source/model replacement; mismatched
aperture/dimensions; Rust absent/wrong ABI; rule change without any inference;
cache-only missing cache; identical repeated apply; selection reorder/removal and
hidden selection; busy rejection/stop/retry; same-path virtual-copy refusal;
current manual flags/ratings/trash/active selection/edits unchanged; non-eye and
original-focus evidence unchanged; actual UI acknowledgement and all TS/Rust ABI
wiring. Real multi-person photos, missed faces, low resolution, occlusion,
false positives, responsiveness and packaging remain UNRUN.

## Static-review lifecycle corrections (also UNRUN)

The proxy analyzer now sets a terminal wire marker before its final pick_done
and session snapshot. Shared pick running-state presentation honors it, while
actual worker admission still uses `is_alive()` until thread exit; no new job
can clear the old stop token early. The UI presents `pick_failed/action=analyze`
errors as well as cached-rule failures, including non-first virtual-copy refusal.
Authored fixtures cover terminal display versus retained admission and visible
measurement rejection; runtime confirmation remains Qoder's responsibility.

Pool reuse also selects the first source-path publisher owner BEFORE checking
cache eligibility. A missing/incompatible first-row cache never promotes a later
virtual copy's cache or independently applied rule. Non-first rows retain their
own hints; analyzing an unrelated photo cannot transfer a copy's exemption onto
the first row. This regression has an authored UNRUN fixture.

Worker measurement targets and all pooled sources now freeze exact row object,
document ID, path and workspace identity before launch. Every success, failure,
cache invalidation and final group invalidation write requires that same owner;
a same-path/same-ID replacement row is never substituted. Target ownership is
rechecked at admission, before/after measurement and publication; missing owners
do not emit pick_item. A replacement project can proceed, but the old worker
cannot mutate its rows. Authored UNRUN fixtures cover reorder, row replacement,
workspace change, ID/path mutation and all three publication shapes. This is a
narrow publisher fence, not a new global project/session lock.
