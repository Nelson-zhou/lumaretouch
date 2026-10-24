# Torso scalar transfer: authored, UNRUN

This change only authors source and fixtures. No application, renderer, inference,
test runner, compiler, typechecker, build, download or acceptance run was invoked.

## Contract

- The only portable recipe is `lnx.torso_length.v1: {version: 1, amount}`.
- Torso is a standalone scope. It cannot auto-associate ownership or combine with
  face mapping, persistent association, background, other module or review families.
- Every eligible target retains its own uniquely enabled BodyRef, verified actual
  face binding, support and review hashes. Both bank hashes and source/people graph
  hashes are part of the frozen review key.
- A bounded (8 targets) review shows each target's actual full-pipeline before and
  after render, sampled only after the full-resolution render. The images are not
  source thumbnails or inferred placeholders.
- Native PNG framing/CRC/SHA and UI byte/SHA checks precede browser decoded-size
  checks. Both decoded images plus an explicit per-target checkbox are required.
- Apply/commit forwards `torso_review_ack` with the exact ordered target IDs,
  reviewed revisions and displayed PNG hashes. Terminal receipts must echo that
  pair; receipt lookup does not resubmit writes.
- Old token, target/source edit, body/face/support change, stale bank, missing
  target proof, foreign reference, malformed PNG or old acknowledgment must fail.

## Required future acceptance, not yet performed

1. Compile/typecheck and run authored unit fixtures in an authorized environment.
2. Open actual one-body original and creative-source photos with independently
   reviewed target support; verify preset save/import/preflight/apply and batch
   review/commit/undo/redo, including zero amount.
3. Load both target images, check each target and verify a changed review resets
   readiness. A broken image, wrong digest, false dimensions or ninth target must
   never enable commit. Close/reopen and target-context edits must revoke review.
4. Refuse multiple enabled bodies, disabled/missing selected body, missing target review, unresolved
   ownership, changed actual face and source-support-copy attempts.
5. Inspect full-resolution head/hair/arms/background seams and compare the native
   target rendering with final export, including existing unrelated effects.
6. Verify timeout, rejected ack, replay, rollback failure, process restart and
   receipt query preserve the original request/token/pair without duplicate writes.
