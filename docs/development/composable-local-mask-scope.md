# Retained local-mask objects: implementation scope

2026-10-22: implementation written, not executed or accepted. No product run,
test run, build, typecheck, regression campaign, commit or push for this slice.
The matching Rust local-masks executable must be built later through the existing
packaging stage; absence fails explicitly, not through a fallback approximation.

## Frozen mapping and real consumer

Handbook 局部调色 and frozen AI package PC-32454 controls 11–15 cover brush,
linear/radial gradients, color and luminance ranges; 17 covers feather; 18–24
cover retained object controls and composition. Objects feed the EXISTING grade
hue/saturation/value/amount consumer before deformation. They do not create a
local-adjustment layer framework. LUT remains global; exposure/HSL/curves/levels,
repair and other consumers are not silently reinterpreted as object-scoped.
Controls 1–9/16 have only the honest semantic subset documented separately in
semantic-mask-source-scope.md. Controls 25–26 batch/template workflows are not
claimed complete. PC-32454 as a whole is not complete or accepted.

## Input, editing and persistence

The frozen editor explicitly shows original working-sRGB source pixels with the
current crop and rotation, before repair, skin effects, deformation and grade.
Bound capture proof includes runtime document/revision/generation identities;
canonical retained geometry does not store those ephemeral identities. Exact
crop/rotation inverse maps captured brush/radial/linear geometry into normalized
source coordinates. Paths and affine axes, not proxy bitmaps, are retained.
Stored source SHA-256 plus full dimensions survive reopen; changed source files
suspend the effect instead of rebinding geometry. Runtime decoded-source stamps
and full-export decode stamps close stale-file windows.

Objects retain ID, name, enabled state, operation, opacity, feather and geometry
or range parameters. Existing objects can be edited, redrawn, ordered or deleted.
The full-image object cannot be edited, hidden, moved or deleted. Removing other
objects may shift its index without changing it. The common undo/redo state and
project v4 encode these objects, including inactive versions. Older v3 readers
reject v4 instead of silently dropping masks; v3 repair strictness is retained.
Legacy all/skin/brush scopes and brush assets remain distinct and compatible.

## Raster and preview truth

Rust performs the actual bounded tile raster, spatial feather, encoded-sRGB
color distance, linear-light luminance range, and ordered composition. Starting
from zero, add is max, subtract is saturating subtraction, intersect is min.
Enabled zero-opacity intersections therefore zero the result. Missing active
semantic operands suspend the entire composition, including subtract operands.
The process receives bounded RGB tiles only when ranges need them, not a
whole-image RGB subprocess roundtrip. Geometry is re-rasterized at source output
resolution for full 8/16-bit export and quality inspection; it is not enlarged
from a proxy mask. Snapshot node limits remain bounded at 65536 to accommodate
the recipe's bounded 8192 total path points.

The cyan saved-mask overlay is derived from this same composed mask and carried
in the source-input capture alpha plane; base display alpha is restored opaque.
It is a proxy diagnostic, not a full-resolution verification. Orange draft
contours are explicitly geometry guides, not proof of a selected pixel range.
Range eyedroppers sample the frozen RGB8 proxy and are explicitly approximate;
exact producer-owned valid row spans exclude rotation padding. Manual ranges
remain usable if pick-validity metadata exceeds its bounded budget. Controls
70/73 have this sampling path. Child 72 is now written as actual retained
colour-range selection inversion, not display inversion; child 75 is written as
linear-Y grayscale from the frozen RGB8 proxy plus actual saved-composition
coverage, not a CSS grayscale substitute or an unapplied draft preview. Both
remain unrun and unaccepted. The luminance map is display-only, preserves source
RGBA/proofs/history, and requires producer-owned valid rows to exclude padding.
Missing validity or suspended coverage disables that map explicitly. See
[range inversion and luminance-map scope](mask-range-inversion-and-luminance-map.md)
for exact frozen IDs, official/community sources, LMR2 worker requirements, and
the focused acceptance handoff. Range edits must be applied then viewed in a
new saved-mask capture to see their actual coverage. Per-object feather is source-normalized; its exact kernel,
range formulas and work budgets are documented in core/local_masks/README.md.

## Semantic ownership and failure boundaries

Available semantic sources are whole-photo portrait-model categories, not the
selected face, individual objects, pets, or a generic complete person mask.
Owner contract includes SHA-256 of the exact immutable model bytes supplied to
MediaPipe. Missing actual-model identity disables semantic creation only;
primitive/range objects remain independent. Missing analysis/model mismatch on
reopen suspends semantic consumption until compatible analysis is available.
Export does not borrow another photo's masks or silently broaden the effect.

Reviewed mutations use independent bounded receipts and common history fencing.
Unknown outcomes require querying the original request; they are not resubmitted
as fresh edits. Failure restores state/pipeline; failed rollback requires reload.
The implementation is statically connected, but runtime, visual correctness,
performance and interaction acceptance remain unverified by this development-
first slice.
