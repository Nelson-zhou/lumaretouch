# Visible-hair directional smoothing — source-only readiness

**AUTHORED / UNRUN.** No build, test, inference, photograph review, performance,
platform or release acceptance has been performed. A packaged matching native
library is mandatory; the Python boundary never builds or substitutes one.

This original GPL-3.0-or-later module does not reuse neck/skin smoothing math.
It changes no geometry, synthesizes no missing hair, detects no people, removes
no flyaways, and cannot recover clipped texture. Only host-authenticated,
resolved, manually reviewed owned visible hair may reach its numerical inputs.

## Frozen ABI and numerical domain

`hair_smoothing.h` exposes ABI 1 / algorithm 1 plan, measure and compose functions.
Exact native contiguous/aligned buffers must be pairwise disjoint and stable
through the call. Source is immutable full canonical working-sRGB D65 SDR f32
RGB, at most 32,000,000 pixels. Texture scale is **observed** 1..8 canonical
pixels, never inferred from a proxy or silently clamped. Python `plan((h,w), s)`
checks the native plan against its frozen mirrored arithmetic.

Measurement receives target/context weights already intersected with the
operation's independently reviewed person-owned visible hair and a separate
hard-protection plane. Positive target centers must be inside positive context
unless hard protected. Hard protection is a veto, not a softer target weight.
All RGB, mask and setting values are finite and bounded; no hidden clipping.

## Finite dependency support and local direction

Encoded source pixels are decoded to linear luminance, then natural-log
luminance. Central finite differences produce tensor products. Two direct
finite-support sums (horizontal then vertical, radius `ceil(scale/2)`) yield the
structure tensor. A signless tangent is perpendicular to its principal gradient;
coherence and minimum/maximum tensor energy gate unreliable/strong transitions.
Signal tensors deliberately do not use global cumulative sums: source texture
outside an admitted footprint cannot leak through cumulative-roundoff history.

The exact conservative dependency halo is
`ceil(scale/2) + 1 + ceil(2*scale) + 1`. An integer-only support integral verifies
the entire closed square is in bounds, context-positive and hard-unprotected.
It cannot overflow at the admitted pixel bound. This covers every gradient,
tensor, corner-direction and bilinear luminance tap, including zero-weight
bilinear neighbors. Eligibility is returned separately from texture/direction
signal and counts only positive unprotected target centers.

Four symmetric pairs sample 0.5, 1, 1.5 and 2 times the observed scale along the
local tangent. Every sampled corner must have coherent direction within the
fixed signless tangent agreement threshold. Either strong transition rejects
the pair/candidate, rather than permitting a one-sided blur. Symmetric robust
weights regularize local log luminance with conservative 0.45 strength,
coherence and target coverage. Stored signed gain is bounded by `ln(1.10)`.
Tiny proposals are exact zero. Dark, near-clipped, bright and strong-transition
gates are **engineering heuristics, not physical highlight/occlusion recognition**.
They do not replace explicit skin/scalp/ear/accessory/other-person protections.

No complete context is a refusal. Complete context with absent direction or
fully gated proposals is successful **no signal**, not an application claim.
Reported `changed_pixels` counts source proposals, not current/output changes.

## Frozen composition, preview and memory

Composition consumes CURRENT linear SDR RGB and the solved scalar field. One
common `exp(amount * gain)` factor is bounded by common RGB SDR headroom; no
independent channel clamp is used. Thus existing chromatic ratios are retained
apart from ordinary floating-point error; perceptual hue invariance is not
claimed. Amount zero, field zero, black and exhausted positive headroom preserve
input bits. Negative gains remain allowed on bright current pixels. Encoded
pipeline adapters round-trip only genuinely changed pixels.

Canonical fields are solved once per immutable source/support/repair identity.
Tiles only slice by their actual expanded source origin. The host may project a
field conservatively for display, but must veto any ineligible interpolation tap
and mark it display-only; such a field cannot authorize export or pixel review.
Overlapping owners are rejected by the ownership host and again where frozen complete-context
eligibility overlaps. The immutable exact eligibility remains beside each field through prepare/replay.
Neither face ordering nor a priority winner is a
permitted collision solution.

Checked measure plan is `120*N + 8*(w+1)*(h+1) + 16 MiB`, bounded by 4 GiB. It
includes caller input residents (21N), stable wrapper snapshots, native scratch,
output, frozen retention and validation allowance. Retained gain/eligibility
cost is 5N. The host additionally accounts unrelated analyses, repairs, masks,
other operators and concurrent work. Compose admission is 80N + 8 MiB. These
are conservative refusal bounds, not measured peak RSS/VRAM. Allocation uses
fallible reservations. Inputs, layouts, aliasing, dimensions, overflow, memory,
finite results and cancellation are checked before publishing outputs. On any
nonzero native status all caller outputs remain untouched. Foreign invalid
pointers or a misbehaving foreign callback are outside Rust panic containment.

## Authored but unrun acceptance

`engine/tests/test_hair_smoothing_numeric_unrun.py` authors native/wrapper
fixtures for zero identity, actual directional signed signal, source-vs-current
separation, ratio/headroom preservation, hard halo veto, absent direction,
missing ownership/context refusal, independent neighboring-owner pixels,
cancellation and transactional ABI failures. They are **not executed** and are
not a replacement for requested final Qoder local testing with real native
source crops, mixed output crops and support eligibility.

Before quality acceptance, inspect real 8/16-bit/RAW originals with resolved
straight/curly/wavy hair; low contrast, dark hair, bright/specular texture,
wisps, scalp, ears, skin, accessories, crossing people and ambiguous contacts.
Verify explicit masks, no-signal/refusal wording, source/output crop mapping,
canonical-versus-tile equality, undo/reopen/virtual copies/export, cancellation
and repeated/out-of-order receipts. This source delivery makes no such claim.
