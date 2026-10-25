# Fabric sweat host and rendering boundary

Status: AUTHORED / UNRUN. No builds, tests, imports, type checks, model execution,
photographic evaluation or performance acceptance was performed for this slice.
The shared integrator owns live registration and should record its actual state.

## Existing owners and supplied ports

`fabric_sweat_host.Review(Ports(capture,render,budget))` owns only two ephemeral
metadata records. It does not publish, own receipts, read file paths supplied by
UI, create a second project state, or save corrected image pixels.

`capture()` supplies `Capture(source,input_sha256,repair_sha256,fence,encoded_rgb,
recipe)`. RGB must be immutable FULL canonical float32 encoded working-sRGB-D65
SDR after the existing ordered repair replay, before garment or portrait effects.
The source loader must authenticate original/creative provenance, input digest,
repair sequence and actual document state. Public transport never supplies this
object. `fence` must cover current document ID/epoch/revision and all normal render
inputs; merely hashing source name/dimensions is insufficient.

`render(recipe)` supplies `Rendered(encoded_rgb,source,input_sha256,repair_sha256,
candidate_sha256)`. Its pixels are the complete normal output with that candidate
replacing only `_fabric_sweat`. Other edits remain. Its digest must be the existing
`optics_candidate_identity.fingerprint(recipe)`. Capture checks around rendering
reject concurrent changes. No default isolated renderer is accepted.

`confirm`/`clear` return `ConfirmedEdit`; the existing transaction owner calls
`assert_publishable` inside its lock immediately before replacing `_fabric_sweat`,
then uses normal history/frame/receipt publication. No caller should report this
internal intent as committed. A published result invalidates private review data.
Uncertain writes are reconciled by the existing request owner, never re-dispatched.

## Numerical composition

`fabric_sweat_measure.prepare(encoded_rgb,recipe,byte_budget,cancelled)` rasterizes
manual source masks through the existing Rust local-mask implementation, converts
canonical source pixels to linear RGB and measures the new Rust algorithm once.
The runtime must compare the recipe's input/repair digests against actual captured
pixels before calling it. Prepared arrays are immutable bytes-backed full-grid
fields; facts are copied JSON. They carry no authority by themselves.

`apply(current_encoded_rgb,prepared,amount,byte_budget,origin_yx,cancelled)` slices
that same field for true source-grid export tiles. `apply_field` accepts an already
sliced field and leaves the caller responsible for exact origin/scale proof.
`apply_linear` is available to a linear-RGB pipeline. Do not remeasure each tile,
measure a display proxy, or apply the same operation in two pipeline stages.
Encoded application restores exact original bits wherever native output was
unchanged, preventing gamma-round-trip changes outside the target.

Measurement budget is conservatively `196*N + 160 MiB`; the 4 GiB admission cap can
refuse large sources. It is a bound, not measured RAM or performance evidence.
The caller additionally accounts for other resident/parallel renderer buffers.
Missing installed ABI refuses nonzero work; no Python/OpenCV replacement or
runtime compilation occurs. `clear` does not require native processing, although
its current capture port still needs a readable canonical source.

## Research and honest limits

OpenCV's official [illuminationChange documentation](https://docs.opencv.org/4.12.0/df/da0/group__photo__clone.html)
was inspected on 2026-10-25. Its local gradient/Poisson approach supports the
concept of selection-scoped illumination changes, but the API is 8-bit and its
textureFlattening intentionally removes texture. Neither is copied or used as
this float pipeline's sweat detector. The new Rust method is original and has no
new weights. The retained official PC-32477 specification provides UI requirements;
this host slice did not claim to re-open that site's complete live guide.

Manual reference uniformity, support coverage, clipping and gain limits are
admission conditions, not proof of correct garment ownership or photographic
quality. Patterned/multi-material garments, severe chromatic stains and missing
clean reference remain limited. Automatic detection, full requirement acceptance,
batch/aliases and real-device quality/performance remain open.
