# Local-mask batch and preset transfer: written scope

2026-10-22. Implementation is written and statically connected, not executed or
accepted. No tests, builds, typechecks, model installation/download or inference
were run for this package. Existing colour action pickers, SAM provenance and
LMR2 colour-range inversion are retained.

## Exact handbook mapping

The frozen AI package `功能需求验收映射.json`, PC-32454:

- child 25, 批量同步: `PC-32454-C-6f957b4d8b`, Linux ID
  `LNX-REF-PC-32454-C-6f957b4d8b`.
- child 26, 保存预设: `PC-32454-C-3ab57dd1e3`, Linux ID
  `LNX-REF-PC-32454-C-3ab57dd1e3`.

The [official local-adjustment guide](https://www.pixcakeai.com/guide/32454)
specifies batch append/replace, mask-type selection and excludes brushes from
batch/presets. Linear/radial/colour/luminance masks can transfer. The Linux
handbook's batch contract also requires a frozen source version, target set,
module scope, conflict strategy, preflight and scoped undo. These IDs are not
evidence that PC-32454 as a whole is complete.

Primary implementation references consulted, not copied as an RGB8 pipeline:

- [darktable drawn masks](https://darktable-org.github.io/dtdocs/en/darkroom/masking-and-blending/masks/drawn/):
  retain source-space vectors and transform the resulting masks with pixels.
- [darktable copy/paste](https://darktable-org.github.io/dtdocs/en/module-reference/utility-modules/shared/copy-paste/):
  explicit selective copying, append/overwrite distinctions and exclusion of
  unsuitable internal mask/display data.

## Real independent consumers, not metadata-only export

`lnx.local_grade.v1` carries complete groups: each has its own grade tuple and
ordered mask operands. `_local_grade_layers` persists at most eight independent
groups and 128 objects, with a cumulative 128M enabled mask-pixel limit and the
existing Rust work budget. The source selector can additionally show the legacy
object-scoped grade slot, for nine source candidates; selecting too much for a
target fails preflight rather than truncating the recipe.

Actual render order remains deformation → enhancement → exposure → levels →
curves → HSL → LUT → legacy grade → independent local-grade groups → background
→ geometry. No-group renders do not reorder the old chain. Each independent
group grades the previous result, then mixes through its own composition.
Source masks use `align_source_grade_mask`, the same real displacement grid and
edge/unchanged policy as image pixels. RGB remains float through mixing and the
RGB16 master path. Geometry/ranges rasterize through Rust LMR2 at full output
resolution, not by copying a preview raster.

Session capture, undo/redo, project v5, inspection and RGB8/RGB16 tiled export all
consume the groups. V1–v4 projects explicitly migrate without inventing groups;
pre-v5 tags containing new group fields are rejected. Group-only edits block
neutral RGB16 passthrough. See [consumer details](local-grade-consumers-2026-10-22.md).

## Selection and transfer policy

The UI exposes types (whole-photo portrait categories, portrait background,
custom), then individual complete source groups with names/types and explicit
nonportable reasons. All groups start selected. A brush/SAM group is not silently
deselected: users must explicitly exclude the whole group, or preflight fails.
Selecting only some types of a mixed group fails instead of deleting its
subtract/intersect operand. Saving a preset uses the same two-level selection.

- Append preserves every target independent group, its order and parameters,
  plus the legacy grade/mask/LUT linkage, then appends new complete groups.
- Replace removes only complete target groups of the explicitly selected types.
  Source group checkboxes select what is copied, not arbitrary target deletions.
  If the selected types fully match the old object-scoped grade, replace clears
  that slot and its LUT-strength linkage. Actual LUT data and amount do not
  change. A type-excluded legacy slot remains untouched. This is disclosed in
  preflight. There is no forced legacy promotion or analysis-resolution change.
- Linear/radial geometry requires explicit relative-position rebasing when
  source identity differs. Normalized points/axes map onto the target's full
  original image; aspect ratio can change the geometry. No object alignment or
  identity search is implied. User must review the diagnostic and final result.
- Colour and luminance rules run on each target's own original pixels.
- Semantic groups recompute whole-photo six-class portrait categories on each
  target using the exact source model SHA-256 and confidence policy. This is not
  selected-person matching, generic subject detection or complete silhouettes.
  Missing/incompatible actual model bytes block preflight; no automatic model
  installation/download occurs.
- Brushes are not portable. SAM prompts/input digest/model provenance remain
  photo-bound and cannot be copied or rebased. Existing target prompts may stay
  in unchanged target groups and are validated/recomputed only on that target.

All enabled operands are required, including subtract operands. No missing mask
means global, and no empty composition becomes full-frame. Disabled retained
brush/SAM operands also prevent declaring a selected source group portable.

## Frozen review, receipts and undo

Batch preflight freezes the source modules, selected group IDs/policy, each
target's prepared merged groups, source SHA/full dimensions, file stamp and
dependency identity. The actual target raster is checked at proxy resolution
and its full-resolution work/memory budget is checked before confirmation.
Commit checks target identity/revision, source/dependency stamps and frozen
scope; it cannot accept a new selection or strategy. Live target replay is
strict and precedes parked target writes. Unknown receipts are queried, never
resubmitted as fresh mutations.

Preset apply has its own bounded, expiring, one-use preflight token. It freezes
the preset and current target revision before showing review; only that token
can apply local groups. Ordinary nonlocal presets retain their previous flow.

The first twelve batch targets have cyan source-coverage thumbnails; every
target has actual recomputation, per-group nonzero coverage counts and explicit
failure reasons. These RGB8 proxy images are labelled coverage diagnostics,
not full-resolution/final deformed-effect proofs. Empty coverage is visible.
The full image pipeline does not use this thumbnail as its mask or source.

Batch undo restores only selected modules. It preserves exact old local fields,
including LUT linkage when replace cleared it, and refuses to overwrite later
local/legacy/LUT dependency changes. Unselected exposure and other modules are
not restored. Normal preset/group edits use the existing one-action undo stack.

## Editing and acceptance boundary

Independent groups are visible and editable: name, enable, four grade values,
order and deletion; each group's mask objects keep their editable parameters,
range inversion, order, deletion and geometry-redraw path. Frozen source
capture proof, terminal receipts and history apply to these edits too.

Each independent-group capture sends an explicit `group_id`. The engine computes
that group's own saved ordered composition through the shared Rust raster adapter
and packs its alpha into the existing LRCP source capture. Native ownership binds
the requested group to descriptor `mask_group_id`; UI checks the same scope before
display/presentation/apply, and both native redemption and engine preparation
reject a mutation targeting another group. Selecting another group invalidates
the old capture and its draft. Missing/removed groups cannot fall back to the
legacy stack. Legacy captures keep a null/omitted group ID and their old meaning.

Cyan coverage is on by default for group edits. A separate “查看本组已保存范围”
action shows the saved mask without writing history. Disabled groups can inspect
their saved composition without enabling their grade. Missing operands show a
suspended, zero-coverage diagnostic, never a fabricated whole-image selection.
Drafts are not misrepresented as recomputed coverage. Final canvas/export uses
the real group. Group grade sliders currently edit a draft and require explicit
confirmation; continuous processed-photo feedback while dragging is not yet
implemented or accepted in this package.

Authored, unrun checks cover source selection, unsafe operands, append/replace,
LUT-link preservation, source rebinding, frozen preset review, project migrations
and real float/RGB16 group consumers. Runtime installation, UI interaction,
cross-photo visual quality, memory and performance remain for local validation.
