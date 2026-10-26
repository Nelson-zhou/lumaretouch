# Ordinary automatic white balance — source-connected, runtime UNRUN

## Exact scope

This slice connects **`control:PC-32455:8`**, `ui/src/spec/refine.json:5278`,
`白平衡/自动白平衡`. The neighbouring **AI 校准白平衡** (`:5269`) and
**AI 校准曝光** (`:5323`) remain open and unchanged. Corrected manual WB and the
121-pixel neutral picker are not renamed as automatic WB.

The new button performs a one-shot **classic statistical illuminant estimate**.
It is not AI, neutral-object detection, physical light recognition, as-shot RAW
WB recovery, or a guarantee that the photographed scene contains neutral objects.
Uniform dominant-colour scenes can pass spatial stability and still be corrected
incorrectly. The UI says so and offers the ordinary existing Undo operation.

No tests, native builds, TypeScript typechecks, product imports, image inference,
downloads or installations were run for this slice. Historical WB test results
in other documents do **not** validate these changes. All added executable
fixtures and the end-to-end matrix are **AUTHORED / UNRUN**. Qoder owns local
runtime/photographic verification.

## Reachable ownership chain

1. `RetouchPanel` matches only the exact ordinary-auto leaf. `WhiteBalanceAutoControl`
   uses the App-scoped existing WB workflow, current input token and existing
   single-view/capture/flip/inspection exclusion gates. No optimistic gains.
2. Native `white_balance` accepts action `auto` with exactly request ID, current
   document load ID, engine-issued input SHA-256, recipe document ID and revision.
   Native generation is checked before dispatch. The existing WB `ReceiptHost`
   retains an immutable full request through `ReviewBinding`, not a second ledger.
3. `WhiteBalanceController.prepare()` checks identity, current editability and
   fingerprint **before** the generic document mutation fence. `AutomaticWhiteBalance`
   samples once from the frozen current pre-WB pipeline and calls the separate
   Rust helper. No manual-pick capture, ticket, presented acknowledgment or review
   evidence is invented. Diagnostics say `classic-statistical-estimate`.
4. The controller replaces `options.picked_gains` through **the existing
   `cmd_exposure(..., preserve_reference=True)` transaction**. Algorithm, reference
   white including null, manual temperature/tint, EV, contrast, highlights,
   shadows, saturation and other canonical layers are preserved.
5. The existing history owner records a non-coalesced step. Terminal success is
   emitted only after the exact baseline undo snapshot and stack transition are
   checked. An explicit `history_limit` lets native validation check the capped
   undo increment and cleared redo stack without hardcoding a second limit.
   The native host checks the immutable original request and preserved
   non-WB state; the UI queries this receipt rather than trusting queue acceptance.

`picked_gains` remains the sole serialized correction. There is **no new colour
layer, recipe operation or saved auto-estimator mode**. “Clear auto/picker correction”
clears this shared correction; WB reset additionally zeros manual temperature/tint.

## Input and statistical policy

The input token binds runtime workspace, load, canonical document/revision,
source asset and source/pipeline instances, source shape/dtype/device, projection,
retouch strength/channel/parameters and repair generation. It does not hash files
or inspect a screenshot while publishing document state. Preparation rechecks the
exact identity after sampling/calculation. The renderer's `wb-input` tap is before
WB/exposure; `_lin_t` converts this working-sRGB encoded tap to linear RGB. A
previous automatic or picker correction is never in the estimator's input.

Sampling reuses `color_action_sampling`'s geometry, warm-prefix admission, source
risk and coverage projection, and CPU/GPU available-memory checks. Projection
budget remains at most 8 Mi source pixels, 32 Mi rotated pixels and the existing
transient/headroom policy. The new sampler checks both proxy axes, both **integer
crop** axes and both rotated axes are at least 32: enlarging a 1-pixel or 31-pixel
crop cannot manufacture a 32×32 independent statistical grid. Only 1024 scalar
rows, not image rasters, cross the helper boundary.

Policy `stratified-trimmed-log-gray-world-v1`:

- Deterministic unique 32×32 stratum-centre samples, row-major; sixteen spatial
  cells of 8×8 samples each. No random seed or full-resolution sampling claim.
- Separately projected coverage must be at least `1−1e−6`; **any positive source
  clipping risk** excludes the sample. Risk is computed before interpolation from
  encoded channels `>=1` or `<0`. This is working-stage saturation, not RAW sensor
  clipping detection. Nonfinite/malformed data rejects the whole request.
- Exclude luminance below 0.01, any linear channel below 0.002 or at/above 0.98.
  At least 512 samples and 12 cells containing at least 24 accepted samples are
  required. Each cell uses a 20%-trimmed mean of log(R/G) and log(B/G).
- Median cell chroma establishes a centre. Require at least 12 cells within 0.30
  maximum absolute log-channel deviation and at least three supported cells in
  each quadrant. Estimate from the medians of those stable cells. These are
  conservative product thresholds, not externally calibrated camera constants.
- Existing manual gains are compiled with the current WB algorithm/reference,
  **excluding old picked gains and EV**. `neutral_gains(illuminant, manual)` supplies
  a replacement correction, accounting mathematically for the retained manual
  gains and preserving that estimate's manual-adjusted luminance. Repeat on the
  same input/manual controls produces the same correction, not accumulated drift.
- Both stored replacement gains and effective `manual × replacement` must lie
  in `[0.25, 4]`. Excessive gain is rejected, never clipped into fake success.

`automatic_main.rs` is independent of `core/curves/main.rs`; the latter's 16 KiB
limit is unchanged. The auto ABI is exactly **41,000 bytes**: eight-byte
`LRTAWB01`, LE uint32 count 1024, zero uint32 flags, three LE float64 manual gains,
then 1024 rows of five LE float64 values (RGB, coverage, risk). Extra/truncated
input is rejected. The JSON response is versioned, schema-checked and limited to
2048 bytes by the bridge. No Python estimation fallback exists.

## Transaction, interruption and recovery

- Exact no-op is returned from preparation, **before** document fencing, rendering
  or history. It does not increment autosave revision or clear redo.
- Prewrite refusal (stale input, missing helper, memory/coverage/stability/gain
  refusal) is visible and cannot taint committed autosave state. It never writes
  a sampled raster or saves a misleading “automatic” preset mode.
- Runtime rendering rollback uses the existing exposure transaction. The auto-only
  receipt restores the exact installed WB options/compiled gains/reference in
  addition to canonical exposure fields, then requires a successfully restored
  frame. Post-history checks prove unchanged recipe signature, original history
  snapshot identities/group, project dirty flag and edit timestamp. A conservative
  admitted-attempt **runtime revision fence is not rewound**; this is not a saved
  recipe/history edit and invalidates stale input tokens by design.
- Unknown render/rollback/history/receipt outcome remains unknown and blocks
  further native edits, undo, save/export and auto resubmission. It is never
  converted into success or an unverified “no write”. Original native queries
  remain available; there is no automatic resend or late-terminal overwrite.
- The native fence only settles from the retained validated exact auto terminal,
  not an unrelated `*_done`, raw success, wrong input or bare project-open event.
  A native no-write auto rejection sharing another owner's ID cannot settle or
  suppress that owner's real terminal. Duplicate-key/oversized auto result records
  become unknown only for the exact retained original auto request and RX engine
  epoch; malformed/unbound old-generation input cannot poison manual WB. Unknown review
  records cannot be evicted to admit another mutation.
- Merely navigating to another photo cannot acknowledge an uncertain auto action.
  The conservative UI recovery instruction is to restart the application and
  reopen a confirmed project if the original receipt cannot be established. This
  slice does not add a new in-session abandon/unlock protocol.

### Bounded shared recovery repair found in independent source review

`project create` writes a new empty project **but preserves live `_docs`**. It is
not recovery from an unknown edit. This slice also fixes that pre-existing escape
for final-canvas flip: native pending auto/flip owners reject create; a
`project_created` event cannot clear their fences or advance flip's recovery
generation. Engine project creation checks those owners' unresolved marker or
specific taint **before** project save, `runtime.switch()` or workspace rotation.
Only a validated state-replacing `project_opened` (or replacement engine for
native flip recovery) qualifies. Clean project creation and other owners'
existing policies are unchanged. Added auto/flip engine/native fixtures are UNRUN.

## Save, reopen, Undo/Redo, export and presets

These consume the canonical WB values through existing owners rather than
re-estimating: `white_balance_recipe.py`, `server.DOC_FIELDS`/state restore,
`history_controller.py`, `export_snapshot.py`, `export_recipe.py`, `export.py`,
`vram.set_exposure()` and `ops/exposure.py`. RGB8 and RGB16 use the same fixed
compiled gains at their existing output quantization boundaries. Full-resolution
export starts from the actual full-resolution source, **not an upscaled sampling
proxy**. None of those output implementations were replaced in this slice.

Independent review found and corrected a related existing reattach bug:
`_attach_pipeline` previously assigned the resolved renderer reference back into
the canonical recipe, changing `None` to `6500` on Redo/reopen for any non-neutral
picked correction (including the pre-existing picker). It now resolves 6500 only
for `pipe.set_exposure` and leaves the saved nullable reference untouched. Explicit
manual references still retain their existing value. The new authored actual
engine round-trip fixture covers both algorithms with null and explicit 7000 K;
it has not been imported or run.

Ordinary WB preset/transfer continues to copy the fixed resulting options and
manual controls/reference semantics. There is no per-target batch re-estimate,
cross-photo illuminant recognition or automatic exposure claim. Round-trip,
Undo/Redo and RGB8/RGB16 behaviour require the explicit UNRUN acceptance matrix;
source reuse is not a runtime pass.

## Packaging and static evidence

`packaging/build-white-balance-auto.sh` compiles only repository Rust sources;
`stage-engine.sh` stages the helper plus its source, this policy and existing GPL
license. No new models, third-party dependencies, notices, depth/superresolution
work or runtime acquisition. Readiness `white_balance_auto_protocol=1` requires
the matching helper's exact `--protocol` response. Missing/mismatched helpers are
unavailable; a newly installed package requires an engine restart.

See `automatic-white-balance-source-manifest.json` for exact source hashes and
`automatic-white-balance-unrun.json` for remaining local validation. Python AST,
JSON decoding and whitespace checks are source checks only. Rust/TypeScript parser,
build/typecheck, integration, UI, GPU and photographic validation remain UNRUN.
