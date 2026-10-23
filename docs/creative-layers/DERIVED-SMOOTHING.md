# M14 source-owned smoothing and its reviewed recovery

Source-only continuation of `d10d961af2f06a77d4e595ebe364fe1d8e92bf23`.
Runtime, numerical, native/UI, model, persistence and visual acceptance: **UNRUN**.
No claim that M14, all skin modes, or the 32 AI tools are complete.

## Handbook and algorithm boundary

The supplied handbook and requirement mapping were read. Relevant references:
`LNX-REF-PC-32465-C-43cab87b58` (texture smoothing),
`LNX-REF-PC-32465-C-bea3ce6586` (face/body high-low-frequency smoothing),
`LNX-REF-PC-32465-C-a21aee8184` (high-frequency enhancement),
`LNX-REF-PC-32465-C-de0bf0c851` (low-frequency flattening), and
`LNX-REF-PC-32465-C-529a17ddf0` (moist smoothing).
These are requirement scope references, not assertions that the existing guided
filter implements each named competitor algorithm or its separate face/body UI.
Return/history references remain `LNX-REF-WF-127932-a9c143a25d` and
`LNX-REF-WF-127932-c7783ea5fb`.

The current [official skin guide](https://www.pixcakeai.com/guide/32465) was read:
it distinguishes these modes and separately describes high/low-frequency controls.
No undisclosed parameter ranges are inferred. The
[MediaPipe primary segmentation guide](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter)
was also read: model category confidence is not automatically a usable edit mask.
The existing application keeps its conservative skin editing weight, derived from
body/face skin confidence before applying its confidence margin. The port uses
that actual installed editing field, not raw confidence, a silhouette, a face box
or original-file analysis.

The real existing torch guided-band decomposition, recombination and masked
float mixing remain unchanged. This is source adaptation, not a new AI model,
texture generator, Rust solver or substitute implementation. Existing licences
and notices are unchanged; no external code or models were downloaded.

## Real ordinary skin path

The ordinary skin UI already sends an explicit `skin` channel through native
`set_strength`. That path now has exact finite strength/filter parameters,
actual immutable-source analysis, model identity, source/repair pixel proof and
installed GPU mask equality checks. Existing measured semantic channel names may
be used explicitly; landmark-only/unrecognised names are not guessed. Positive
scope with no editable support refuses rather than claiming an applied effect.

The source remains the immutable returned composite. Original path/digest/stamp
are separate provenance. Repaired input must match its completed ordered replay,
not merely a matching extent or source name. Source/model/mask changes invalidate
review contexts and the downstream grading-prefix cache. Source-only guided
bands remain reusable when only strength or mask coverage changes; source/base
changes invalidate their caches. Tensor identity/version checks run before render
and cache hits. Filter result/band mutation is rejected, not silently reused.

A failed smoothing render restores the prior strength/channel/parameters. The
normal command/history owner still owns edits; no second undo stack is added.
Source/proxy switching preserves requested derived channel intent. A missing
skin mask can no longer become whole-image smoothing by clearing `_channel`
while leaving strength nonzero. Missing scope is visibly warned and suspended,
with original requested values retained; inconsistent actual evidence refuses.
Zero live strength needs no analysis and does not discard its requested scope.

Reopen analysis is requested for derived semantic smoothing or fabric even when
no face was retained. The existing actual model path receives derived pixels and
stamps their identity; it never manufactures a selected person. Missing models
remain an explicit prerequisite, not synthetic evidence. Full reopen/error UX and
backend-failure recovery still require runtime testing.

## Export and recovery

Frozen export snapshots retain bounded read-only selected-mask evidence and exact
recipe/model/source proof. These transient arrays do not enter document history
or project packages. Named scope is resampled once on the full source, then sliced
using the existing tile halo: `2 * texture_radius + 6 * radius`, plus existing
geometry requirements. The halo is not shortened. Canonical working-sRGB float32
source and ordered repaired base are verified before tile construction; each
actual tile and selected mask is bound after upload and before the real solver.
Absent landmarks are represented as an empty array, not a NaN/fake face.

Derived export cannot enter the old fallback that decoded the physical original
and inferred replacement skin masks. It verifies its own frozen evidence or
refuses. Exactly neutral unmasked old derived snapshots remain compatible. A
retained named channel, even at zero strength, still requires valid evidence for
export under the existing strict channel contract; this limitation is explicit.

`skin_smoothing` now joins fabric in reviewed global recovery. Its review context
includes source, strength, channel, all filter parameters, measured mask and
repair evidence. Production before/after, presented receipt and exact apply proof
remain mandatory. Existing source-normalized Rust rasterization and operator-only
float attenuation are retained. Project/history validation checks disabled rows
and source identity too. Native routing already supported this target; existing
source/capture/presentation/receipt fences are unchanged.

## Integration map

- `creative_derived_smoothing.py`: recipe, measured mask, snapshot/export and
  canonical source proof; live recovery context.
- `creative_derived_smoothing_runtime.py`, `vram.py`: actual installed source/mask,
  solver/prefix cache fences without replacing math or tile halos.
- `creative_smoothing_host.py`, `server.py`, `people_open.py`: neutral/suspended
  rendering, source/proxy scope retention, failure rollback and actual reanalysis.
- `creative_document_host.py`, `creative_document_base.py`: exact command and
  snapshot/spec admission, including direct-library callers.
- `export_snapshot.py`, `export_recipe.py`, `export.py`: immutable selected field,
  canonical full-float input and exact export tile transport.
- `creative_derived_global_recovery.py`, `creative_derived_recovery.py`,
  `effect_recovery_runtime.py`: reviewed smoothing ownership and visible status,
  with background still refused.

## Remaining gaps and acceptance

Separate face/body controls, neutral-grey modes, moist smoothing, skin gloss,
face fullness and other skin handbook controls are not completed by this port.
Background/studio/ID/sky effective-source consumers and background recovery remain
separate. Shared transfer still needs explicit per-target identity review and
actual target-owned analysis. Alpha/HDR photo return stays refused without
flattening/clipping; no new precision or unconditional 24 MP/latency claim.

Source checks include AST and whitespace only. Authored fixtures remain UNRUN:
actual mask mismatch, foreign model/source, conservative coverage, float export,
repair order, cache mutation/hits, recovery review expiry, disabled persistence,
proxy scope retention, and missing-model/neutral behavior. Actual skin texture,
protected detail, boundary halos, full/tiled parity, GPU/CPU/cache timing, undo/redo,
reopen/package/recovery and memory measurements remain local QA work. Full live
proof capture includes CPU/GPU evidence checks; zero model inference during a
slider change is not a claim of zero transfer cost or measured interactive speed.
