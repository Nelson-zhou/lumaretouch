# Acceptance handoff: every executable check remains UNRUN

Static checks performed: Python AST parsing of eight newly authored Python source/fixture files; parsing supplied JSON and exact eight-ID extraction; SHA-256 inventory. These establish syntax/traceability only, not imports, type correctness, compilation or behavioral correctness.

## Authored executable fixtures (UNRUN)

- Rust `core/colour_grading/lib.rs` tests: partition-unity mask grid; balance direction; real blend overlap; signed-zero/HDR neutral exact; independent global wheel; selected shadow brightness; nonfinite rejection with untouched output.
- Python `engine/tests/colour_grading_fixtures/test_recipe_contract.py`: complete recipe round-trip, explicit null/NaN/bool/unknown-algorithm rejection, independent batch copies, cancel frame restoration and refused commit, newer preview supersedes older, idempotent commit with one history transaction, status after revision change, document revision invalidation.
- Python `test_native_contract.py`: neutral RGB16 identity; shadow/midtone/highlight tint on linear patches; HDR >1 retention; >500 unique levels across a 1000-code RGB16 ramp; cancellation leaves source unchanged.
- TypeScript `model.test.ts`, `workflow.test.ts`: global range independence, radial wheel saturation, scalar invalidity, one active plus one replacement pending intent, latest-only display and document-switch stale response rejection.

## Required integration/E2E evidence (not established)

1. Authorized offline Rust build and ABI loader; full Python imports; UI typecheck/build; run the above fixtures with exact commit/source hashes.
2. All eight handbook IDs navigate to the mounted panel. Mouse/touch pointer capture, cancellation, keyboard arrows/Shift/Home, numeric edits, range/all reset and enabled/disabled transitions work. Expose all selected brightness values. Colour wheel orientation matches displayed tint hue.
3. Display confirmed preview then Apply records exactly one complete gesture; cancel/Close returns actual committed frame. Rapid drag/repeated Apply, late frame, interrupted load, close/reopen, history edit during preview, another tool action, switch photo/session, dropped/duplicate replies, timeout/query/reload all preserve latest intent and don't silently mutate wrong document.
4. Project save/reopen with all four wheels nonzero; undo/redo restore exact recipe; malformed present field rejects before workspace changes; legacy omission is neutral; per-photo state survives navigation without leakage.
5. Dedicated preset include/exclude/reset, replacement not accumulated effect, portable recipe round trip; mixed-source batch 1–1000 images preflight-all, per-target domain check, one group history and all-target rollback on failure. No implicit overwrite of unrelated edits.
6. Preview/export stage order and exact recipe equal at same resolution; original RGB16 TIFF gradient retains precision; no double application across tiles; float HDR positive/negative retained before terminal transform; non-sRGB ICC source properly converted or rejected. Compare neutral bit hashes and active CPU/native output tolerance.
7. Visual review on skin, neutral grey, bright coloured lighting, very dark tones, saturated out-of-gamut colours and HDR speculars. Check hue continuity at 359/0, blend/balance trajectories, brightness transitions, absence of banding and undesirable coloured black. This original algorithm may need refinement; no quality pass is asserted.
8. CPU/GPU supported machines, 24/45/100MP memory and latency; cancellation at chunk boundaries and no partial publishing; CPU bridge GPU transfer cost. Validate failure if native .so missing or ABI wrong. Capture actual timings, not target claims.

Current source status for all eight IDs: SOURCE_CONNECTED_UNRUN after the explicit shared integration grant. Runtime and visual status: UNRUN. No product-family completion percentage is justified by this work.
