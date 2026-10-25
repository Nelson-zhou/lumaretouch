# Reference-assisted fabric sweat correction

Status: authored source integration only. All builds, type checks, numerical,
photo-quality, interaction, export parity and performance execution are **UNRUN**.
The exact handbook leaves PC-32477:5, :6 and :14–:17 remain partial. This is not
an automatic sweat detector or a complete clothing-beautification family.

## One existing owner

`_fabric_sweat` is an immutable versioned recipe in the existing Engine DOC_FIELDS,
ordinary undo/redo and project serialization. It contains source dimensions/digest,
canonical repaired-input digest, ordered repair digest, amount, source-pixel radius
and four explicit brush roles. There is no second history/association bank.
The adapter uses the existing serialized engine lane and one history record per
confirmed candidate or clear. Native delivery reuses ReceiptHost; unknown writes
query the original ID and never resend. Clear uses no sweat native computation.

## Source and pixel stages

Reference capture reuses the full precision portrait source decoder and existing
ordered repair materialization/replay. It is not RGB8 display-proxy measurement.
The original file is not changed. Same-garment target, clean reference, garment
extent and protected region are manual declarations; no skin inverse or inferred
person silhouette pretends to be clothing evidence.

A full source field is measured once per immutable recipe and input. Ordinary
preview uses a nearest source-grid projection of this field and is explicitly a
display approximation. The final reviewed before/after and export use the complete
renderer and original-sized field, sliced at the exact tile origin. The mask image
is in source coordinates and may have a different aspect from a cropped output.
The operator runs after fine fabric shading and before studio/portrait/colour
consumers. Native correction is applied to current linear RGB with headroom bounds.
No-op pixels bypass gamma round-trip drift. Both RGB8 and RGB16 enter the same float
pipeline; neutral passthrough and reduced-capture optimizations must not drop it.

Changing source repairs requires clearing and reviewing sweat again. Full input
and repair hashes are verified before measurement/export; a mismatch refuses,
never silently uses a stale correction. New source imports start neutral. The
current-photo reference cannot be blindly copied through batch/preset export.

## Availability and limits

The dependency-free original Rust library is built only by the explicit packaging
script; no runtime compilation, download, model, numerical fallback or licence
change. Missing ABI reports unavailable. Manual same-garment evidence can be wrong;
confirmation is not image-quality acceptance. Complex prints, wet specular areas,
clipped material and heterogeneous reference regions can refuse or produce an
undesirable candidate. Inspect the complete comparison before applying.

The 32 MP source bound is an upper limit, not an availability promise. Full-source
source/repair capture, correction and ordinary rendering have separate conservative
budgets. CPU/native field application currently transfers preview tiles through
CPU; GPU parity, interactive latency, 24 MP RSS and batch throughput are unmeasured.
No claimed automatic cloth segmentation, multiple garment types, presets, shared
aliases, batch review or successful physical-device acceptance is added here.
