# Brow makeup source slice: implementation authored, runtime acceptance UNRUN

Base supplied: a904c5e8. Shared integration authorized at local a904c5e82cc936124678602be2f139194550d29e.
Canonical runtime/UI/IPC/persistence/recovery/export/preset/package routes are
source-wired. Reachability and visual/runtime acceptance remain UNRUN.
No product imports/execution, tests, compiler, build, typecheck, inference,
installation, downloads or Git writes were performed. Static AST/JSON/hash/source
inspection only. No commercial pattern artwork was copied or downloaded.

## Baseline and scope

Manual baseline lines 541–545; AI package 功能需求验收映射.json exact IDs:
- LNX-REF-PC-32471-C-f8c081796f: 14 effects, strength, independent left/right unlock.
- LNX-REF-PC-32471-C-cd82871a04: per-pattern recommended colours.
- LNX-REF-PC-32471-C-88e033710b: verified frame picker.
- LNX-REF-PC-32471-C-9fcbd519c2: integer RGB.
- LNX-REF-PC-32471-C-8b0e3a0ecc: HEX.
- LNX-REF-PC-32471-C-d192a9d749: favourites, maximum six without eviction.

Official reference inspected 2026-10-23: https://www.pixcakeai.com/guide/32471,
brow makeup and material colour sections. Reference does not establish our
pattern names, shapes, exact slider range or achieved visual quality. Local
strength 0–1 maps to UI 0–100. All 14 original profiles have distinct non-colour
width, offset, density or fibre distribution; recommended colours are separate.

## Anatomical and ownership constraints

Canonical lnx.brow_makeup.v1 has linked, left/right pattern/strength/colour.
One seven-leaf patch owns each edit; relinking adopts the selected side explicitly.
This does NOT replace lnx.brow_shape.v1 and never modifies its geometric recipe.
Rust paints bounded float deltas on a measured existing brow, not a pasted
rectangle. No original-brow removal, inpainting or hidden reconstruction claim.
Real MediaPipe 478-point evidence plus current semantic occluder exclusion is
required. Each active side needs TWO independent source-normalized brush masks:
visible brow and adjacent forehead skin. Dark local brow evidence is compared
with that separately reviewed forehead. No eye-light/eyeliner review is reused.
Blonde/low-contrast brows may conservatively refuse. Known occluder detection and
manual review are not complete segmentation. Small/cropped/foreshortened/hidden
or insufficiently reviewed brows refuse, not silently skip requested edits.
Both requested sides stage first; native failure cannot publish a partial side.

Original source vectors reraster at requested source dimensions. Frozen local
working-sRGB deltas use the existing LocalEffect preview/export compositor and
canonical recovery target brow_makeup. No alternative graph/history/recovery
owner. Neutral does not need native code or support availability. Native absence
refuses active edits; no runtime build, install, fallback or synthesized anatomy.

## UI and persistence

Fourteen shape thumbnails are illustrative, NOT accepted before/after evidence.
The verified capture controller pins current source, graph/association revision,
selected target and sampled side; it uses producer float frame presentation and
matching capture receipt, not canvas screenshot pixels. Recipe only enters
preset/batch ports; masks, review, source identity, palette and recovery do not.
Document palette requires ordinary correlated receipt/history/project lifecycle.
The host exposes reviewed_sides so one-side approval is never reported as both.

## Acceptance remains open

See acceptance.json. Local Qoder must build/install the explicit Rust library,
compile/typecheck UI, run authored contracts, and independently test real-photo
quality, multi-person scope/receipt races, cancellation, presets, six-colour
persistence, recovery, undo/redo/reopen, and preview/tiled original-size exports.
Static parsing/hashes cannot establish any of those outcomes.
