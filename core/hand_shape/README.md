# Hand shape numerical core — AUTHORED / UNRUN

Original GPL-3.0-or-later, dependency-free 2D geometry. This is neither a trained
hand-shape model nor a body-slimming rename. Palm-width, phalanx-width and joint-
width controls can supply distinct independently reviewed visible compact regions.
The numerical kernel cannot establish anatomy, visibility, ownership or licensing.
The host must supply source-bound visible support, explicit confirmation/correction,
keep-out protection, current ownership and a frozen operation order. Manual input
must be labeled **manual support**, not AI or a fallback neural result.

## ABI 1

`lrt_hand_shape_evaluate` is declared in `hand_shape.h`. At most 32 rows, each seven
f64 elements: `cx, cy, ux, uy, a, b, k`. `u` is a unit longitudinal axis; `a` and `b`
are longitudinal and transverse radii in the original canonical source space.
The accepted tiny axis roundoff is normalized once. Each radius is at least two
pixels; aspect ratio is 0.2–5; signed strength `k` is limited to ±0.12. These are
original local safety policies, **not disclosed PixCake parameters**. The host
keeps rows in original-source pixels. For proxy pixel `q`, the adapter evaluates
`D^-1 F(D q)` with diagonal `D=((source_width-1)/(proxy_width-1),
(source_height-1)/(proxy_height-1))`. It divides the resulting displacement by
`D`; the inverse determinant is unchanged by conjugation. This handles aligned
proxy rounding without rebuilding a falsely isotropic ellipse or enlarging a
proxy displacement map. Original-resolution export uses `D=I` and reevaluates
every query against the original compact primitives.

For target `q`, let `u` and `v` be longitudinal/transverse local coordinates,
`r=(u/a)^2+(v/b)^2` and `n=(-uy,ux)`. Inside `r<1`, source coordinate is
`p=q+n*k*v*(1-r)^3`; outside it is exactly `q`. Positive `k` narrows visible width.
Output is `q-p`, not `p`. Rows compose in supplied order at the actual preceding
source coordinate; there is **no displacement-LUT addition or pixel sampling**.
The host composes this field with its other inverse fields before sampling RGB or
masks once through the existing owner.

## Safety argument and limits

The inverse derivative determinant for one row is
`1+k*((1-r)^3-6*(v/b)^2*(1-r)^2)`. The factor in parentheses is in `[-32/49,1]`.
Thus each row has determinant at least 0.88 with the allowed signed strength.
For fixed longitudinal coordinate its transverse map is strictly increasing and
fixes the two ellipse endpoints. It maps the ellipse onto itself, fixes the
exterior, and is C2 at the compact boundary. The map is globally injective; a
finite composition remains injective with positive determinant, including away
from sampled points. No iterative inversion or hidden landmark is required.

Exact rotated ellipse envelopes must fit inside a one-pixel source inset. Queries
must be finite and within the whole source. Each row preserves its ellipse and
therefore the source rectangle. Total displacement is conservatively bounded by
`sum(abs(k)*b)` and must not exceed the explicit caller budget, itself at most
128 pixels. Evaluated chain determinants outside 0.25–4 refuse the whole request;
this extra distortion threshold is query-local, not a claimed global distortion
bound. Global absence of folding follows from the primitive proof above. Host
common-map edge, overlap, protection, derivative and displacement checks remain
required; this core does not override them or silently reduce requested strength.

Pointer alignment, span arithmetic, exact lengths, limits and output aliasing are
checked before reading. Allocation validity and absence of concurrent mutation
remain the FFI caller's obligation. A complete dry pass precedes all output writes;
there is no heap allocation, partial result, image resampling or runtime compile.
Zero-point requests still validate primitive state and budgets. Zero rows produce
identity. Error codes: 1 buffers/schema; 2 primitive; 3 source; 4 budget; 5 map.

## Verification status

`tests.rs` contains authored **UNRUN** fixtures for neutrality, each geometric
region size, compact support, off-grid derivative, ordered composition, NaN/domain
and primitive rejection, budget, alias/span checks and whole-candidate failure.
No compiler, tests, build, model inference, runtime imports, rendering, quality or
performance checks were executed. `packaging/build-hand-shape.sh` is only an
explicit distributor build entrypoint for later authorized Qoder validation.
