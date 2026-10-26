# Reference-only colour consistency in full-image group review

**Source integration only; all tests, builds, app runs, image-quality and performance acceptance UNRUN.**

Original requirement: `PC-32455-C-53da929b74` / `LNX-REF-PC-32455-C-53da929b74` (多图色彩统一).
Original spec checked: `ui/src/spec/refine.json` → 多图色彩统一; `docs/development/handbook-traceability.json` → `control:PC-32455:3` under `refine:PC-32455`, still pending independent verification. No acceptance status is promoted.
Exact operation: `lnx.reference_color.v1`.

Existing coverage is documented in `docs/REFERENCE-COLOR-INTEGRATION.md`: manually choose a reference photograph; automatic ORB geometric correspondences and robust Rust linear-RGB patch fit produce a separate target-owned correction. This is NOT manual point picking, semantic AI style transfer, calibrated illuminant estimation, or identical slider copying. No new algorithm, dependency, model or weights are introduced here.

## Added path

A genuine saved reference-only preset in the existing store can now enter the same group panel as portrait presets. Its portable parameters contain the immutable local reference asset and strength, never another target's gains. Every selected parked original is measured separately once. Its frozen target fit is reverified, not recomputed, throughout review and commit. Targets need their existing document/source/portrait ownership established (open a newly imported document if requested), but **no face detection or skin preparation** is required, and the explicit skin-preparation endpoint rejects this colour-only profile before mutation. Existing edits are preserved subject to the normal full-source reference renderer's admission and authentic-scene support.

Each group has 1–8 distinct physical original targets, excluding the current editor, the reference document and identical physical reference source. Virtual/derived copies are outside this slice. Reference plus skin/global mixed presets are rejected, not partially applied. The immutable saved reference remains the authority even if its original editor subsequently changes; this is saved-reference intent, not a live-reference recapture command.

The existing full-source candidate renderer makes before/after **whole-image review representations** (bounded PNG display, not 1:1 pixel inspection). The panel shows existing fit/coverage/gamut warnings beside every pair, checks all page digests and actual display, then requires one explicit group acceptance. Candidate/source/revision/history/people proof checks run again before the existing canonical BatchSync atomic publication. No new history owner is introduced. The resulting existing GroupDelivery capability provides explicit scoped project save and ordinary export planner/job, not automatic delivery. Missing reference assets, unsupported provenance, insufficient correspondence, changed targets or budget exhaustion refuse the whole group.

## Primary design evidence checked 2026-10-25

- PixelCake official guide: https://wiki.pixcakeai.com/guide/9398.html — reference remains unchanged, same-scene use recommended late in grading, group undo/redo.
- darktable official color-mapping manual: https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/color-mapping/ — creative statistical Lab cluster mapping is a different purpose; not silently substituted for the existing illumination/brightness-matching contract.
- Existing mature OpenCV correspondence and exposure references remain in `REFERENCE-COLOR-INTEGRATION.md`. No external implementation copied.

## Authored acceptance, not executed

`engine/tests/test_portrait_group_reference_unrun.py` covers reference-only recipe admission and first-fit/verify-only reuse without skin analysis. Integrated scenarios still UNRUN: fresh no-face original ownership; same reference/physical alias refusal; mixed preset rejection; dissimilar scene refusal; stale source/revision/preset/reference asset; full image page and display gates; atomic commit rollback; whole-group undo/redo; original-precision export agreement; scoped project reference-bundle round trip; existing unrelated dirty edits retained; cancelled/expired/replayed review. Real wedding image quality, speed and memory remain unverified.
