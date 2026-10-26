# Explicit hand proposal setup — AUTHORED / UNRUN

This source closes the manual-file-placement gap **for an already prepared,
reviewed application runtime**. It does not claim a fresh machine has MediaPipe.
No model download, dependency installation, product import, readiness probe,
inference, test, build or typecheck was executed in this source change.

## Route and scope

- Hand panel → explicit Install / Cancel / Status / CPU recheck.
- Existing `prompted_model` native process owner, fixed `hand-landmarker-v1`
  whitelist → selected engine interpreter → `hand_shape_setup`.
- Existing model-owner file lock, cancellation/subprocess runner and curated
  resumable downloader; no second native installer, arbitrary URL or photo path.
- The internal manifest supplies the exact official URL, 7,819,105-byte size and
  SHA-256 in MODEL-PROVENANCE.md. This profile rejects URL changes, including
  redirects to another asset. Existing HF profiles retain their own policy.
- Partial bytes remain untrusted; exact Range response, total size and full
  SHA-256 are required. Ignored Range restarts; a full corrupt partial resets.
- Staging is verified again, then a bounded isolated CPU probe consumes those
  verified bytes via `BaseOptions(model_asset_buffer=...)`. The probe constructs
  the actual HandLandmarker and detects on a generated 64×64 blank RGB image.
  It is a runtime capability check, not proof of hand-detection accuracy.
- Only successful staging publishes to the existing application-owned hand
  model path. Readiness is published after the model; interruption fails closed.
  A receipt binds the probe version, model hash, selected executable stamp and
  selected package metadata plus the actual bounded hand producer source hash/path. The loaded producer origin is checked against that distribution source. This is a freshness receipt for a trusted base
  environment, **not cryptographic authentication of its entire native stack**.
- Offline status rehashes the model and checks that receipt. The panel's explicit
  “refresh current source and capability” action obtains current engine status;
  actual proposal inference checks readiness again and consumes verified bytes.
- Missing / mismatched MediaPipe 1.1.1 is explicit before download. No `pip`,
  global package modification, environment switching or hidden auto-install.
  Optional runtime distribution approval remains under requirements-mediapipe.

Linux Python ≥3.10, 64 MiB free staging space, 2 GiB probe address-space cap,
60-second CPU limit and 90-second supervisor timeout are conservative authored
budgets, **not measured device minima**. Manual geometry is independent of setup.
Closing the panel does not cancel the native owner; explicit Cancel does.

## Local acceptance still required (all UNRUN)

Run authored mocked fixtures only under local test authorization, then validate
missing runtime, wrong version, read-only disk, symlink/nonregular assets, corrupt
bytes/receipts, Range/restart/hash failures, disconnection/resume, cancellation
in transfer/probe/publish, simultaneous extension ownership, repeated clicks,
panel close/reopen, stale engine/photo context, capability refresh, selected
interpreter identity, actual MediaPipe API/packaging compatibility and device
resource budgets. Validate actual hand photos separately, including jewelry,
occlusion, contact, mirrored handedness and multiple hands. These are reliability
limits requiring human review, not automated detector claims or license bans.
