# Crown height and side hair volume: original geometry core

Status: AUTHORED / UNRUN, 2026-10-25. No build, import, inference, test execution,
render or photographic acceptance has been performed for this family. Static
review and source/model hashing are not evidence of a passing runtime.

## Scope and preserved controls

One independent family, `lnx.hair_volume.v1`, has independently versioned crown
and sides subrecipes. It preserves `control:PC-32472:2` (negative lowers visible
crown, positive raises) and `control:PC-32472:3` (negative reduces side width,
positive increases), including linked or independent image-left/image-right
amounts. Image side is not inferred anatomical side. The reference does not
publish a numerical range, neutral/default values or the difference between
its two crown variants. Our signed `[-1,1]`, zero neutral, initial linked state,
profile and gain are original implementation decisions, not reverse-engineered
commercial values. No invented second crown algorithm or version-equivalence
claim is made.

This changes actual source contour coordinates. It is not complete-head
uniform scaling, hair colour, gloss, unification, filling, hair generation,
hairline movement or a box relabelled as a hair segmentation. Existing
`core/head_size` and all previous algorithms remain unchanged.

## Smooth compact field

Each manually reviewed crown or side strip supplies normalized breakpoints
`x=[a,b,c,d]`, `y=[a,b,c,d]`. The tensor plateau `[b,c] × [b,c]` contains actual
observed hair boundary/interior samples. The surrounding source transition is
explicitly reviewed; each fade margin is at least 4 original pixels, plateau
width/height at least 2 pixels and outer bounds at least 1 pixel inside source.
These are numerical admission thresholds, not a claim of sufficient resolution
for photographic quality.

The one-dimensional window is zero outside `(a,d)`, one on `[b,c]`, and uses
`s(t)=6t^5−15t^4+10t^3` on both fades. It is C2 at every join, with
`0≤s≤1` and `max |s'|=1.875`. Each forward contribution is `A wx(x) wy(y)` in
one axis only: negative y for positive crown; negative x for positive image-left;
positive x for positive image-right. `A` is the requested signed amount times
10% of that strip's smallest original-pixel fade margin. This fixed versioned
gain does not change with preview resolution and is not silently reduced.

At/below the crown lower boundary the crown field is exactly identity. At the
side inner boundary and outside its vertical strip, the side field is exactly
identity. Protected regions must be outside the complete support/reach; there
is no dense semantic weighting or after-the-fact hole-cutting that invalidates
the derivative proof. Overlapping crown/side strips may combine for one owner.
Image-left and image-right supports must be strictly disjoint in x.

## Global bound and inverse

For strip i, let `mx,my` be its minimum x/y fade margins. The gradient norm of
its scalar displacement is bounded everywhere by
`ki=|Ai|·1.875·sqrt(mx^-2+my^-2)`. Since sides cannot overlap, a global Frobenius
bound for the full displacement Jacobian is
`K=sqrt(k_crown²+max(k_left,k_right)²)`. This bounds its spectral norm. Admission
requires `K≤0.45` and `D=sqrt(A_crown²+max(|A_left|,|A_right|)²)≤128` source
pixels. The analytic forward determinant is checked at every inverse solution.

For `F(p)=p+u(p)`, `||Du||≤K<1` gives global injectivity and a contracting inverse
iteration `p[n+1]=q−u(p[n])`. The compact support is strictly within the source;
the map is identity outside it, so its global inverse preserves the source
domain. Runtime still explicitly checks every final source coordinate, including
off-grid queries. No clamp, extrapolation, reversed-point fit or identity
fallback is used. Up to 64 iterations must achieve step ≤1e−9 and forward
residual ≤1e−7 source pixels. The forward determinant must be within
`[(1−K)²,(1+K)²]`; inverse determinants use the reciprocals. Nonconvergence,
nonfinite data, bounds violations and source-domain escape refuse the request.

The proof applies to this original hair family, not to arbitrary existing TPS
fields or a mixed final chain. Parent composition must retain its existing
aggregate safety checks and source ownership exclusions. A sampled final-chain
test does not replace an analytic all-domain proof.

## Native ABI 1

The dependency-free GPL-3.0-or-later crate is `core/hair_volume`. Its C header
documents buffer ownership. Lengths count doubles:

- recipe4: `[1,crown,left,right]`.
- support24: three source-normalized `[x0,x1,x2,x3,y0,y1,y2,y3]` profiles,
  crown/image-left/image-right order. Inactive profiles must be all-zero.
- state30: `[1,width,height,crown,left,right]` plus three pixel-space profiles.
- facts19: three support rectangles `[x0,y0,x3,y3]`, then displacement bound,
  gradient bound, forward determinant lower bound, residual tolerance, iteration
  limit, source width and source height.

All buffers must be live, aligned, correctly sized and disjoint; arbitrary raw
pointer ownership cannot be established by address arithmetic. Concurrent writes
are forbidden. A complete admission pass precedes all evaluate output writes.
Forged state is revalidated even for empty/neutral calls. Python copies borrowed
inputs and returns bytes-backed immutable state/deltas. Missing installed native
code is an explicit packaging blocker, never a fallback to an unrelated effect.

## Common sampler contract

`HairVolumeField.evaluate(q)` returns inverse displacement `delta`, where source
coordinate is `q−delta`. Prepare once at original dimensions. Whole-source
canonical ALIGN=8 proxies conjugate both x/y scales using pixel endpoints;
only exact endpoints are normalized for division roundoff. Interior off-grid
points are untouched. Composition must evaluate at the preceding chain's actual
off-grid coordinates and sample image/RGB/alpha/source-owned masks once through
the existing common sampler. This family does not own a pixel sampler, camera
crop, render cache, history stack or parallel people graph.

The Python preparation and consumption APIs are in `hair_volume_runtime.py`.
`require_prepared` must verify every active source owner and its exact record,
recipe and any additional protected rectangles before consumption. Support,
semantic evidence and original/derived source identity must remain frozen for
preview, export and replay. No source path is consumed by this module.

## Verification still required

Authored Rust and Python `_unrun` fixtures cover directions, independent controls,
fixed regions, off-grid inverses, analytic determinants, immutable bridge
buffers, malformed/aliased inputs, neutral bypass, evidence/review ownership,
source mismatch, protected contacts and missing native packaging. They have NOT
been executed. Compiler/ABI/sanitizer checks, the actual common-sampler
composition, numerical stress tests and real-photo visual/photographic acceptance
remain separate gates before this is described as tested or production-ready.
