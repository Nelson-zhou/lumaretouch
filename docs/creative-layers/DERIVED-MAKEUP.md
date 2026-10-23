# M14 returned-source reviewed makeup consumers

Source-only continuation of `db90a3515327b23d19e1d7f7af36922c33e765b0`.
Runtime, native, numerical and visual acceptance: **UNRUN**.
This continues handbook `LNX-REF-WF-127932-a9c143a25d` (return for further
editing) and `LNX-REF-WF-127932-c7783ea5fb` (unified history). It does not
complete M14 or the 32 AI functions; these are ports of existing consumers,
not newly invented generation or inferred anatomy.

## Coherent admitted families

| Operation | Existing intent contract | Required independent review |
| --- | --- | --- |
| lnx.lipstick.v1 | 13 patterns, five textures, colour, strength | Upper and lower visible lips |
| lnx.blush_makeup.v1 | 12 patterns, colour, strength | Both visible cheeks |
| lnx.eyeliner.v1 | Six patterns; linked/independent left and right | Visible, open upper eyelid per requested eye |
| lnx.eyelash.v1 | 14 patterns; left/right and upper/lower links | Separate root and extension regions per requested part |
| lnx.brow_makeup.v1 | 14 patterns; linked/independent brows | Separate brow and adjacent visible forehead skin |
| lnx.iris_makeup.v1 | 11 patterns, strength | Both measured iris/pupil polygons and highlight exclusions |

The prior eight local portrait operations and reviewed eye-light remain admitted.
Exact family state validators retain all enum, colour and finite numeric domains.
Leaf validation temporarily disables only linked equality, as the existing
people_edit owner does; complete atomic candidate recipes still enforce both-eye
and upper/lower equality before publication. No shared person/group target is
admitted. Photograph-wide scalar intent still resolves each target face against
its own measured analysis and reviewed support rather than copying selected-face
geometry.

## Actual source, analysis and review ownership

`creative_derived_makeup` defines exact operation/action/support sets; it does
not create another asset, recipe or history owner. Reference and review requests
need complete captured document/graph/association fences, an exact local FaceRef
and actual derived MediaPipe precompute proof. Each existing host also requires
the selected enabled face and a previously shown matching reference before review.

All full-frame references use the effective-source helper fixed by the previous
slice. Iris has a separate crop path: `iris_makeup_reference.acquire` now uses
`analysis_rgb`, verifies exact effective source and FaceRef, validates analysis
and masks against the actual RGB dimensions, and rechecks source/face evidence
after making the crop. It does not upsample to invent detail. The eight-pixel
minimum measured iris radius, bounded image and source-pixel-centre crop mapping
are retained. The physical-original comparison buffer is never relabelled.

Each support family continues its existing immutable content hash, source hash
and extent, FaceRef/analysis revision, landmark digest and geometry validation.
Preview and runtime validate retained descriptors even when neutral or disabled.
The preview ports forward the canonical bank under each explicit family input;
runtime checks each descriptor against its supplied bank, not a merged fallback.
Existing export freezes and forwards the same target-owned support bank.
Normalized source vectors are rerasterized at actual output dimensions, not
stretched from a proxy mask. Iris retains its own measured polygon semantics.

Lipstick still requires measured excluded support and a semantic-model hash.
Blush still requires measured skin and excluded support plus the model hash.
The other makeup consumers retain their actual exclusion/support prerequisites.
Review is not a replacement for missing inference, occluded anatomy, tiny eyes
or unsupported geometry. Such requests refuse; no all-white synthetic mask or
source-image analysis is substituted.

## Concrete consumers, colour and history

`people_render_runtime` now creates lipstick/blush review rasters for derived
sources and invokes the existing eyeliner/eyelash/brow/iris adapters. The existing
`people_effects` path invokes lipstick/blush layers only for active recipes.
Exact-neutral recipes avoid unnecessary native work. All use current target
working-sRGB pixels and existing Rust-backed solvers/colour-transfer contracts.
Derived full-source export remains float32 with divisor one. Native failure or
any requested-face refusal prevents a successful partial render.

The five existing palette actions admit only save/remove plus explicit #RRGGBB
colour. Existing document-owned libraries retain their six-colour bound and
ordinary receipt/history semantics. Eyedroppers remain fenced sampling of the
current proxy-output float capture, not a source-reference image. RGB8 rounding
belongs to the selected colour value, not the canonical derived source.

No alternate graph, undo stack, source store or output codec was added. Existing
project/recovery/package support records and validators remain the persistence
owners. No third-party engine or algorithm was copied; existing licence headers
and primary practice references in the previous creative-layer docs are retained.

## Integration map

- `creative_derived_makeup.py`: exact family contracts, action envelopes, leaf
  validation and owned support/bank forwarding helpers.
- `creative_derived_effects.py`: integrates that exact registry; preserves
  source/graph/analysis fences and shared/recovery exclusions.
- `people_owned_inputs.py`: validates and forwards canonical family banks.
- `people_render_runtime.py`: per-family bank checks, review rasters and concrete
  consumers on derived sources; hair/body separation unchanged.
- `people_effects.py`: existing lipstick/blush layers on active derived recipes.
- `iris_makeup_reference.py`: actual source crop and before/after ownership checks.
- Five full-frame review editors use current-source wording. Iris already uses
  its source-pixel crop presentation and retains the same geometry editor.
- New UNRUN fixtures: `test_derived_makeup_contract.py` and
  `test_derived_iris_reference.py`; previous effects/eye-light fixtures updated
  to the cumulative admission set, without removing hair/recovery/shared fences.

## Verification and remaining scope

Only static source/AST/whitespace/hash inspection is performed here. Fixtures
use synthetic contract evidence and mocked consumer boundaries where stated.
They are not proof of real inference, native rendering or photographic quality.
Local QA must still cover every pattern/texture and bilateral mode, stale or
missing reviews/semantics, native failure/all-face atomicity, preview/full-source
parity, linked undo/redo, palette history, save/reopen and recovery/package replay.

Still fenced: hair/body, semantic/local mask editing, repair/recovery brushes,
source patch and shared person/group transfer. Existing makeup recovery/batch
controls are not made available by admitting their scalar/review consumers.
Transfer still needs target-owned measured analysis even for neutral intent,
dormant-original-slice handling and explicit cross-private-document identity
review. Alpha/HDR photo return remains refused, not clipped or flattened.
Proxy/minimum-detail and thin-canvas bounds remain; no unconditional 24 MP or
whole-handbook acceptance claim is made.
