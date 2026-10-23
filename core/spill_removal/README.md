# Fixed-alpha colour estimation and guarded spill correction

Source-only, UNRUN. Original std-only Rust and Python adapter under the repository
licence. No model, copied implementation, downloaded code/assets, runtime build,
global desaturation or alpha erosion. Packaging builds this cdylib as
`liblrt_spill_removal.so` and places it in `engine/src/lumaretouch_engine/bin/`.
ABI 1 is documented in `spill_removal.h`. A missing core fails closed.

## Conceptual sources, not imported implementations

Germer, Uelwer, Conrad and Harmeling, *Fast Multi-Level Foreground Estimation*,
ICPR 2020: https://arxiv.org/abs/2006.14970 and
https://arxiv.org/html/2006.14970v1 . Its fixed-alpha compositing model and local
regularized colour estimation motivate a coarse-to-fine joint F/B solver.
Mature implementation reference: https://pymatting.github.io/foreground.html and
https://github.com/pymatting/pymatting/blob/master/pymatting/foreground/estimate_foreground_ml.py .
PyMatting is MIT licensed: https://github.com/pymatting/pymatting/blob/master/LICENSE.md .
Those sources were read in the browser, not copied, downloaded or installed.
Our schedules, seed guards, box-preserving line steps, reflected-colour branch,
application contract and parameters are original engineering choices, not
Germer/PyMatting or proprietary product defaults. No quality claim follows from
the sources or from these unexecuted fixtures.

## Immutable analysis contract

Input is the immutable effective straight linear-sRGB-D65 source and the actual
reviewed foreground alpha, both finite float32 in [0,1]. Reject HDR analysis
without silently clipping. Do not feed current edited pixels, replacement
background, opacity-weighted composition coverage or edge-adjusted alpha into
estimation. The core cannot authenticate review receipts; callers must verify
source identity, dimensions, matte provenance and review state before calling.
Alpha is fixed and never returned or modified. Field cache identity must bind
the effective source, reviewed alpha, strength, estimator version and scale.
For a returned creative composite, effective source means that immutable derived
asset, not the physical original file retained solely as provenance.

## Actual estimator

The joint F/B image uses a halving pyramid bounded to 1024 on either side and
1,048,576 pixels. At each level area-average the original inputs rather than
repeatedly resize intermediates. Initialize from actual trusted colour seeds;
bilinearly prolongate F/B and run deterministic red-black local relaxations.
There are 24 rounds at the smallest level (both dimensions <=32), then six at
each larger level. The per-channel local objective is:

    (a F + (1-a) B - I)^2
    + sum_j (0.002 + 0.15 abs(a-a_j)) [(F-F_j)^2 + (B-B_j)^2]
    + 0.002 [(F-I)^2 + (B-I)^2]

Its 2x2 normal equations are solved jointly, not by dividing by a tiny alpha.
A single six-component line step from old F/B toward the solution maintains
the SDR box without channelwise clipping; pure observed colours are anchored.
This finite relaxation is not a converged constrained optimizer. If any F/B
component is already on an SDR boundary and its unconstrained update points
outward, the common step can become zero and stall all six components at that
pixel, including components that could otherwise improve. The fixed iteration
schedule does not guarantee the constrained optimum or recovery from this stall.
At every full-source pixel a further 2x2 solve uses the true source I and alpha,
with the interpolated F/B as 0.02-weight colour priors. Out-of-range solutions
abstain. This is coarse-guided full-source evaluation, NOT full-resolution
spatial F/B optimization and NOT an upsampled proxy matte or corrected image.

Two full-source seed maps carry actual near-clear background (alpha <=0.02)
and foreground (alpha >=0.98, >=ceil(8*scale) pixels from non-opaque coverage).
Foreground propagation cannot cross alpha<0.05. A straight subject support
path is additionally checked. Two-pass propagation can omit winding support;
it is not advertised as an exact geodesic solver. Three or more nearby seed
samples must agree; high foreground/background colour variance abstains.
No alpha morphology is used to change coverage. Depth only selects priors.

Let Y(x)=0.2126R+0.7152G+0.0722B and chroma(x)=x-Y(x)(1,1,1).
For mixed pixels, project positive chroma(I-F) onto the normalized original
background chroma axis and remove only that component. Reject weak or excessive
signals, disagreeing F/B priors, high reconstruction residual and absent seed
support. Low alpha confidence fades rather than dividing by alpha. Reconstruction
residual alone is not evidence of a correct decomposition.

For near-opaque pixels, the matting equation cannot identify reflected colour.
A SEPARATE heuristic compares source chroma with an independently seeded
interior foreground prior. It removes only a small positive projection toward
the background-minus-interior chromatic axis, within ceil(8*scale) pixels of a
real clear-background sample. It requires low perpendicular chroma residual,
similar luminance, an opaque support path without sharp luminance jumps and
multiple agreeing seed colours. Confidence is at most half that of the mixed
branch. Deep interior, absent independent prior and same-hue foreground/backdrop
ambiguity are exact no-ops. Thresholds are conservative original choices that
have not been numerically validated or tuned against a production dataset.

## Apply to current edits, not cached source

Preparation returns raw HWC delta and HW confidence; confidence already includes
requested strength ONCE. Optional reviewed erase/restore coverage multiplies
confidence only and cannot create evidence where native confidence is zero.
The caller must apply spill before its existing ID-background replacement.
Given CURRENT edited linear RGB C:

    d = delta * confidence
    k = min(1, min((1-Cc)/dc where dc>0), min(-Cc/dc where dc<0))
    if k<1: k = max(0,k) * (1-2^-20)
    result = C + k*d

All channels share k, preserving the luminance-null correction direction; no
channel clamp is allowed. Zero d/confidence is bit-exact neutral. Finite current
HDR pixels outside [0,1] remain exact rather than being clamped into SDR.
Non-finite current RGB is rejected. CPU uses float64 row intermediates then
float32 output; tensor consumers may use float32 with a 2e-6 comparison tolerance,
but neutral pixels must stay exact. Colour transforms are owned by the parent
pipeline; do not mistakenly apply the linear correction directly in encoded RGB.

## Full source, proxies, tiles, cancellation and memory

Prepare a complete render-domain field before export tiling, then crop fields
using exact source tile coordinates. Never estimate independently per tile.
A preview may prepare its own whole scaled source/alpha with explicit
render_scale, but proxy correction/alpha cannot substitute for export. Spatial
support radii scale from source pixels; scaled proxies can abstain more often.

Maximum input: 32 million pixels and dimension 65536. Conservative local peak
admission: 64*N + 64MiB <=2GiB. It covers original/copy source+alpha, output
delta/confidence, two full-source seed maps, bounded F/B/reduction scratch and
row scratch. Checked arithmetic and fallible large Rust allocations precede
use. The caller MUST additionally admit other retained ID-background, edited
RGB, packed CPU/GPU fields and export buffers against its shared budget. This
estimate is not a promise that every 32MP pipeline request fits 2GiB.

Validation, map passes, field production and relaxation poll cancellation per
row. Reduction additionally polls after at most 4096 accumulated source samples,
including within a single coarse output row; this bounds scan work, not wall-clock
cancellation latency or allocation time. A cancelled or failed
call never publishes its partial output arrays. Return statuses distinguish
bad parameters, unsupported pixels, cancellation, memory and numerics. No
iteration-until-converged loops, runtime builds or proxy-export fallback exist.

## Honest limitations and verification status

Incorrect/coarse alpha, translucent hair without clear seeds, textured or
multicolour backgrounds, high-frequency colour transitions and tiny subjects
can force abstention or an incorrect estimate. Real green/blue clothing, hair
or makeup can be indistinguishable from reflected backdrop colour; the same-hue
guard reduces risk but cannot prove colour truth. Real material edges and
highlights can mimic the opaque branch. Deep opaque spill is not recovered.
Manual erase/restore and reviewed before/after comparisons remain necessary.
This source change is a partial, conservative implementation, not complete
official PC32475 acceptance or a numerical/visual/performance certification.

Rust unit cases and Python contract fixtures are authored but UNRUN. No local
imports, application execution, compiler, tests, typechecker, inference,
download, install or Git write was performed for this delivery.
