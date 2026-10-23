# Dedicated ID-background recovery, not legacy background recovery

Baseline `a0df3773a71be344efb2ef0da2982e9c1d8216cf`. Source-only integration. Fixtures are AUTHORED / UNRUN; no product imports, execution, tests, builds, typechecks, inference or downloads were performed.

## Requirement reconciliation

The supplied handbook lines 575–579 lists a recovery brush for ID-background replacement. The AI requirements mapping identifies `LNX-REF-PC-32481-C-0f284fcda5` (证件照换背景涂抹笔). This is distinct from PC-32475 spill removal/manual spill brush (`e999ab085a`, `4bc238dfa1`) and the original-shadow family (`442ced0175`, `ab010073e3`, `48553e2d03`, `c959928d7a`, `b1b766d4ce`, `9e1c732ff8`, `0513155f3d`). Those features are not implemented by a recovery blend and remain unfinished. The prior ID document records official guide 32475 inspection; 32481's traceability remains supplied-document evidence, not a new live-page verification claim.

The existing `background_replace` recovery target surrounds the separate legacy `vram.apply_background` stage. ID replacement executes afterwards in `IDBackgroundStage`. Reusing the legacy target would leave the ID compositor unchanged. This slice introduces the distinct `id_background` target instead.

## Pixel and ownership contract

The ID recovery consumer receives the exact edited input to ID replacement and that operator's output. It attenuates only their difference. Full recovery preserves upstream exposure, tone, local edits and other retained processing; it never blends an unedited original photograph over the result. Recovery uses the existing float-pixel attenuation contract, with exact zero/full-coverage endpoints. Only coverage is 8-bit; working pixels do not round-trip through an 8-bit bitmap.

Normalized recovery vectors remain in the existing source-owned recovery recipe. Their disposable coverage is transported once through the same actual deformation used by ID fields, then later manual/optical/crop geometry proceeds normally. Full export rasterizes vectors at full source dimensions and slices fields through existing tile windows. No recovery proxy is enlarged into a full output image.

`id_background_recovery.py` binds the current ID recipe, source, independent selected/retained support, immutable background bundle, actual installed fields and relevant input/deformation state. Both original and returned-composite sources require this consumer proof. Source, recipe, asset, support or field changes invalidate review; clear/disable of the last stroke also retains consumer checks across application. Disabled retained vectors remain durable without requiring an active ID model merely to validate saved intent.

Actual ID preparation still owns matte/support acquisition, high-bit/ICC asset handling, mutual exclusion and full-resolution composition. No model compatibility was invented. Opaque SDR returned-source admission remains explicit; transparent or signed/HDR inputs are not clipped or flattened to make recovery eligible.

## Review, history, export and persistence

The existing source capture, producer-rendered before/after preview, presented-preview acknowledgment and terminal receipt owners are reused. The source image authorizes coordinates; the production before/after pair authorizes the actual effect change. Native and UI review additionally pin the exact requested recovery target, not merely any supported target. No new command registration, `main.rs` edit, second queue or undo stack is introduced.

Recovery uses the existing one-gesture history and rollback path. Project validation checks ID/recovery source agreement recursively through active and historical records without running a model. Full export binds the prepared ID alpha/background fields and recipe to the recovery consumer; tile attachment and final ID export completion recheck the same content. Reference-color provenance now excludes pixels replaced by the actual ID stage, adjusted only by its own recovery, without restoring provenance already lost upstream. This is not permission to use unadapted derived reference-color planners.

Integration: target schema and durable vectors in `effect_recovery_state.py`; source/consumer proofs in `id_background_recovery.py` and derived recovery admission modules; preview/runtime/controller hooks in the existing recovery owner; numerical stage connection in `vram.py` and `effect_recovery_stage.py`; export finalization in `id_background_runtime.py`; project admission in `id_background_project.py`; native target proof in `effect_recovery_api.rs`/`effect_recovery_host.rs`; UI target and receipt validation in `ui/src/effectRecovery`.

## Legacy common-background residual

Legacy/common replacement is still proxy-bound. `id_background_legacy.py` creates a color-key or custom saliency matte from current proxy inputs; `_bg` persists its uint8 proxy matte and export resamples it. It lacks the complete immutable effective-source, full-resolution acquisition/replay and correlated reviewed mutation contract needed to admit derived sources honestly. Its native function is currently in `main.rs`, with an old uncorrelated `bg_done` interface. That path stays guarded.

A future coherent legacy slice needs durable source/matte/model ownership, genuine effective-source acquisition, reviewed document/revision receipts, full-resolution replay and history rollback, followed by the legacy recovery consumer. The repository's `ops/birefnet.py` is a custom SHA-gated saliency implementation; compatibility with official BiRefNet checkpoints is not established. Neither renaming it nor routing legacy controls silently into ID replacement would satisfy these requirements.

## Required local acceptance

Still UNRUN: original and derived source brushes; zero/full/fractional coverage; source/deformation alignment; changing ID recipe/support/background while a review is open; supported-but-wrong target replies; disabled/cleared ID intent and recovery; stale or mutated installed/export fields; full/tiled output agreement at RGB16 and differing dimensions; project/package/recovery reopening; undo/redo and source-switch history; no silent alpha/HDR fallback; and memory-budget refusals. Spill removal, original-shadow extraction, legacy full-resolution replacement and broader unsupported planners remain unfinished. Source integration is not functional acceptance or handbook-wide completion.
