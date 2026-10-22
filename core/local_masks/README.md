# Composable local masks v1

Static implementation only. No build, tests, typecheck, performance measurement,
product interaction, or acceptance was executed for this change.

## Scope and ownership

- `raster.rs` evaluates brush, linear/radial, encoded-sRGB colour range,
  linear-light luminance range, supplied semantic probabilities, and full image.
  Rust also owns feather, opacity, ordered composition, and final quantization.
- `wire.rs` independently validates bounded binary tile requests.
- `main.rs` keeps one process alive for an entire raster, not one process per mask
  or tile. It holds only one request tile and current working fields.
- Python `local_mask_recipe.py` validates retained JSON, protects full-image
  objects, preflights budgets, normalizes integer RGB only within transport tiles,
  and handles bounded transport. There is no second Python raster algorithm.
- Python `local_mask_geometry.py` inverts the same `Projection` integer crop,
  snapped-quarter-turn rule, centre offsets, and arbitrary rotation as clone stamp.
- The controller owns source identity, revision/capture validation, semantic
  ownership, history, persistence, consumer suspension, and export attachment.

Requirements consulted: manual-text lines 615–616 and frozen refine PC-32454
controls 11–24. This does not claim AI smart/free/quick selections, edge
expand/contract/smoothing, batch synchronization, presets, or new semantic models.

## Retained recipe

`{version:1, domain:"source-normalized", objects:[...]}` has at most 64 objects.
An object always contains `id`, `name`, `enabled`, `operation`, `kind`, `opacity`
(0–1) and `feather` (0–100), plus exactly its kind-specific fields:

| Kind | Fields |
|---|---|
| brush | `points:[[x,y],...]`, `axes:[[dx,dy],[dx,dy]]` |
| linear | `start:[x,y]`, `end:[x,y]`, `cross:[dx,dy]` |
| radial | `center:[x,y]`, `axes:[[dx,dy],[dx,dy]]` |
| color_range | `color:[r,g,b]`, `tolerance:0..1` |
| luminance_range | `low:0..1`, `high:0..1` |
| semantic | `channel:string` |
| full | No extra fields |

Coordinates are normalized source pixel edges; pixel centres are `(x+.5)/width`
and `(y+.5)/height`. Axes are basis *columns*. The linear `cross` is independent
from `end-start`; retaining the second basis vector is necessary to preserve the
linear coordinate under an anisotropic crop/rotate/fixed-proxy projection. Merely
inverting two gradient endpoints and taking a new Euclidean dot product is wrong.

Linear intensity is clamped first basis coordinate: zero at start, one at end.
Radial intensity is `max(1-distance_in_basis,0)`. A brush is the union of swept
unit ellipses between consecutive points, at most 1,024 points each and 8,192 total.
The single-point case is an ellipse, not an empty gesture. Brush self-crossings do
not accumulate opacity. No proxy bitmap replaces these retained objects.

Colour range is normalized Euclidean distance in encoded working-sRGB (distance
between black and white is 1). It is not a perceptual Lab/Delta-E selector.
Luminance uses sRGB decoding and Y = .2126 R + .7152 G + .0722 B; interval endpoints
are inclusive. RGB must be immutable pre-retouch source RGB, never displayed,
retouched or deformed output. Extended finite source values are not clipped into
membership. Semantic inputs are same-domain finite probabilities in [0,1].

Feather 0–100 means spatial box-filter radius 0–5% of the shorter original source
axis, rounded up to integer sample support at each requested resolution. It is not
screen-pixel radius or brush hardness. Two separable passes use replicated source
edges and tile halos. This simple box feather is deliberately documented, not
presented as a Gaussian or parity claim. Opacity is applied once after feather.

Composition starts at zero and folds enabled objects in list order: add is max,
subtract is `max(a-b,0)`, intersect is min. Disabled objects are omitted. An enabled
zero-opacity intersect still clears the accumulated mask. An empty stack returns
zero, not full image. An optional full object is enabled/add/opacity1/feather0;
`check_transition` protects its complete identity/fields from edits/removal.
The controller rejects explicitly moving it; removing preceding ordinary objects
can legitimately shift its index. Controllers must use that transition check for
mutations, not only check_stack.

Missing enabled semantic or RGB dependencies raise `MaskUnavailable`. The entire
consumer must suspend, including when an unavailable operand was subtract/intersect.
There is no fallback to all-image/person/inverted-skin. Inputs that are present but
malformed also fail closed. Callers must not catch an error and reuse a stale mask.

## Python APIs

- `check_object(raw)` / `check_stack(raw)` return independent normalized objects.
- `check_transition(previous, proposed)` additionally protects full-image objects.
- `dependencies(stack)` returns `(needs_rgb, sorted_semantic_channels)`.
- `validate_budget(stack, (height,width))` preflights the exact tiled work plan.
- `raster(stack, shape, rgb=None, semantic=None)` returns H×W uint8 weights.
- `inverse_object(spec, object, valid, full_source)` returns one source-normalized
  object. `valid` is a numpy bool capture-coverage array; `full_source` is (W,H).

Float RGB is H×W×3 encoded-sRGB; uint8/uint16 RGB normalizes in a bounded tile.
Semantic maps are H×W float numpy arrays. Full GPU transfer is not hidden inside
this API. Metadata-only edits must not invert geometry twice. Brush coverage
crossing rotation padding is rejected; gradient control anchors must be valid,
but their fields may extend beyond a cropped view in original source space.

## Resource and wire contract

At most 64 million source/output pixels, dimension 65,536, 512×512 core tiles,
2 million pixels per halo tile, 16 semantic channels, 128 MiB packet, 512 million
charged pixel/segment/filter operations, 60-second overall worker deadline.
Admission includes feather initialization and brush segment bounds, not just
object count. The controller must admit the *whole proposed stack* at original
source size before mutation. If limits are exceeded, simplify the recipe; do not
silently resize/export a proxy mask. These caps are not a measured latency claim.

One mask output (up to 64 MB) is resident in Python. RGB transport is tiled, never
an entire source float conversion, and independent object fields are not retained.
The largest tile packet may still include RGB and several semantic fields, so
these limits do not constitute a guarantee of total renderer memory availability.
Transport uses Unix selectable/nonblocking pipes, matching the packaged Linux app.

Each request is framed by a little-endian u32 payload length. Payload: `LMR1`,
13 u32s (source W,H; tile x,y,W,H; core x,y,W,H relative to tile; object count;
RGB flag; semantic count), object records, optional RGB f32 LE triplets, then one
f32 LE tile per semantic channel. Each object has u8 kind, u8 operation, f64 opacity,
u32 radius, then the documented numeric geometry (brush starts with u32 count).
Semantic records carry u32 channel index. Object names/ids remain in retained JSON;
they are not executable worker input. Responses are u32 size then core uint8 bytes.
Both sides enforce exact lengths. EOF closes the worker; failure returns no mask.

`packaging/build-local-masks.sh` and the stage-engine build line package the worker
from this checkout. The engine reports a missing matching worker rather than
silently selecting a Python implementation.
