> Historical original-source slice. The subsequent derived reviewed transport and
> shared float primitive are documented in DERIVED-COMMON-BACKGROUND.md; the
> original v1 compatibility contract and remaining neural limitations below remain.

# Common background: deterministic full-source key replay

Status: source implementation only. No product imports, execution, numerical tests,
builds, typechecks, model downloads or inference. This is a bounded original-source
legacy path improvement, not completion of M14 or a new official AI feature.
Baseline: `82f129e120f9a179d90fafd62d9ad641efb81031`.

## What changed

New `color_key` commands keep a versioned `key_recipe` in the existing `_bg`
document/history state. It binds the actual original file SHA256 and dimensions,
algorithm contract, frozen source-proxy border reference, the reference grid,
tolerance and softness. Solid output color remains explicit in `_bg`. No new
history owner, source image, generated image, asset store or model is introduced.

The reference deliberately stays the same border median used by the previous
command on that proxy. It is NOT claimed to be a full-resolution border analysis.
At export and 100% inspection, the complete original RGB8/RGB16 pixels are evaluated
against this exact reference. There is no proxy-matte upsampling for the new
recipe. RGB16 is explicitly divided by 65535 before key evaluation, avoiding the
old helper's non-uint8 unit-range assumption. The final field is float32. Preview
retains the existing uint8 matte cache, so full-resolution output is not promised
to equal an enlarged proxy or its quantization exactly.

A 32 MP ceiling and existing cgroup-aware memory admission bound allocation.
One full float matte plus 256-row scratch is prepared before tile attachment;
tiles slice that field under the existing geometry/halo and recovery ordering.
This admits ordinary 24 MP geometries when memory permits, not an unconditional
24 MP performance or runtime acceptance claim. Cancellation discards incomplete
fields; file stamps and source digests fence full decode/preparation/render.
No source float/HDR is clipped to enter this path.

## Persistence and history

The existing project asset encoder handles cached matte arrays. Project validation
checks present recipes recursively, including history. No legacy record is auto-
migrated: an old recipe-less bitmap remains `legacy-proxy-resampled` at export.
The custom neural backend also remains proxy-bound. `bg_done` and export metadata
separate new deterministic replay from those paths.

New recipes survive proxy switching by retaining metadata, discarding the cached
matte, and rerasterizing on the new source preview grid with the frozen reference.
Their history signature includes recipe intent, not disposable bitmap contents.
Rehang source validation fails closed and does not delete new recipe intent.
Historical records retain their prior legacy migration behavior.

## Integration map

- `common_background_source.py`: validation, source capture, decode proof, export
  preparation/finalization, live source verification, proxy preservation/rehang.
- `id_background_legacy.py`: the existing command captures the versioned recipe;
  no new native command or fake reviewed receipt is claimed.
- `id_background_runtime.py`: its already-shared background source lifecycle
  invokes common verification before ID-specific early returns. It does not
  reinterpret the common recipe as ID state or alias recovery targets.
- `server.py`: source preflight and decode stamp; existing proxy reset/rehang use
  extracted common helper. No `main.rs` changes or additional command registration.
- `export_recipe.py`: new replay bypasses only the old bitmap-resample block;
  cross-file transfer rejects source-owned recipes before generic early return.
- `export.py`: preparation before recovery and tile slicing; finalization at both
  exposure-prepass and final output boundaries; explicit quality metadata.
- `id_background_project.py`: recursive common recipe validation.
- `history_policy.py`: source/recipe-aware semantic signature.
- `photo_grain_runtime.py`, `optics_transfer_engine.py`, `reference_color_engine.py`:
  direct common decode ownership before full-source spec construction. This covers
  the shared grain/colour/detail/tone preview path and target/reference renders.

## Why not replace this with the ID compositor?

The audited source contracts are different. Common `ops.matting.composite_t`
clamps input/mix to SDR and converts encoded backgrounds; ID uses prelinearized
material fields, preserves exact alpha=1 input and permits upstream values outside
SDR. Common currently aligns matte conditionally; ID aligns packed alpha and
background. Their stage positions and recovery targets differ. Replacing one
with the other would alter existing appearance and coordinate semantics.

This slice reuses the existing deterministic key and common compositor, not a
second incompatible engine. A future shared low-level implementation must encode
those compatibility distinctions explicitly and undergo numerical validation.
No Rust/Torch numerical equivalence is claimed from source inspection.

## Requirement reconciliation and precise residuals

The preceding dedicated ID recovery slice addresses the separate supplied-map
item `LNX-REF-PC-32481-C-0f284fcda5`. This common source-replay slice does not add
that item again or complete PC32475 spill removal/original-shadow requirements.
It closes an engineering prerequisite in the existing legacy M6/common path while
M14's broader returned-source integration remains incomplete.

1. Derived common acquisition still requires structured native review/correlation,
   immutable effective-source transport and consumer-bound recovery evidence.
   Existing derived guards remain. No original source analysis is reused.
2. The existing neural backend is a custom SHA-gated saliency network. Its declared
   `INFER_LONG_EDGE=1024` is not applied by its current call path. No official
   BiRefNet checkpoint compatibility, full-resolution neural acquisition, hair
   segmentation or output quality is claimed. No code/model/license was imported.
3. Existing common `background_replace` recovery continues around its own actual
   operator. This slice does not promote it to the independently reviewed derived
   consumer contract, nor alias it to `id_background`.
4. Common image-background asset selection, source/ref picker review, alpha/HDR
   transport, spill removal, original-shadow segmentation and broader shared
   transfer remain explicit follow-up work. Existing ID high-bit assets are not
   removed or narrowed.
5. Legacy unversioned proxy records are supported as legacy, not silently upgraded.
   Reissuing a color-key command creates the new recipe; no automatic appearance-
   changing migration occurs.

Fixtures in `engine/tests/test_common_background_source_unrun.py` are authored
and UNRUN. AST/JSON/hash and whitespace checks are source-only evidence.

Proxy-switch limitation: the pre-existing document loader clears its entire
undo/redo stacks when changing proxy dimensions because other legacy pixel-bound
layers cannot be migrated. This slice preserves the current common key intent,
not arbitrary old pixel-layer history across that global reset. Undo/redo on a
stable proxy continues through the existing owner; no second history is added.
