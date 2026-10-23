# Independent teeth brightness and yellow reduction

Source baseline febb5dee058fb98dae8ae42556ab0db3656fe06d. Authored source only;
all tests, builds, numerical, natural-photo and performance acceptance UNRUN.

## Exact requirements, not new tooth reconstruction

- LNX-REF-PC-32469-C-6eb0bef21b: 牙齿美白/明度.
- LNX-REF-PC-32469-C-5462a41c9a: 牙齿美白/祛黄.
- Existing parent LNX-REF-PC-32469-C-5669d11a65: 牙齿美白.

The baseline manual's teeth section and mapping JSON lines 3016–3053 specify
independent child controls. No numeric range/default is disclosed. This implementation
uses 0..1 normalized amounts with neutral zero as a local design, not an official
numeric claim. Existing `/teeth` remains the old coupled whitening effect; the new
`/teeth_brightness` and `/teeth_yellow_removal` are independent, additional operations
in the same canonical `lnx.enhance.v1` recipe. Legacy projects are not silently
migrated into a new look. Simultaneously active old/new controls intentionally combine.

Official source: https://www.pixcakeai.com/guide/32469 . Live tool access to that
page failed during this slice; exact semantics were read from the supplied manual,
refine specification and requirement mapping, not reconstructed from memory.

## Primary technique evidence and licence

Adobe's first-party teeth-retouching guide separates selected teeth, yellow
saturation adjustment and lightness adjustment:
https://www.adobe.com/uk/creativecloud/photography/discover/how-to-whiten-teeth.html .
GIMP's mature open-source documentation explains separate colour-range saturation
and lightness adjustments:
https://docs.gimp.org/2.10/en/gimp-tool-hue-saturation.html .

These are technique references, not copied algorithms, proprietary equivalence or
photo-quality certification. Original Rust implementation is GPL-3.0-or-later with
the repository. No GIMP/Adobe code or model weights were copied. Existing MediaPipe
landmark dependency and its existing licensing remain unchanged.

## Actual support and colour computation

The new controls do not detect or invent teeth. Canonical runtime validates the
actual target FaceRef, MediaPipe analysis and effective original/derived source.
The existing geometric/photometric mouth gate is computed from the frozen source,
not a colour-graded preview. For the new controls, its result is intersected with
the actual inner-lip contour and an inward sampling-footprint margin. The wider
original mouth pool is retained for relative brightness/saturation statistics;
restricting that statistical pool to teeth alone would incorrectly compare teeth
against themselves. Closed mouth, tiny regions and empty retained support refuse.
Legacy-only recipes retain their existing support and effect unchanged.

This remains a heuristic, not semantic tooth segmentation or an occlusion proof.
Tongue, braces, reflections, lipstick, highly unusual lighting and small/occluded
mouths can be ambiguous. No user-reviewed dental segmentation receipt is claimed.
The normal source/current canvas comparison is available; dedicated support-painting
and dental-support approval are not introduced in this slice.

One Rust kernel operates on encoded working-sRGB float32 and actual source-owned
coverage. Brightness raises HSV value with a monotone shoulder below .965, without
filling black pixels or replacing texture with white. Already brighter highlights
are not darkened. Yellow reduction lowers saturation only in a smooth yellow hue
range, with exact neutral treatment for non-yellow colours when brightness is zero.
It is not blanket desaturation, tone reconstruction or a claim of CIE lightness.
The two amounts do not activate one another. Coverage zero/neutral corrections
preserve pixels; wrappers apply a float32 correction delta to the original values.
No source RGB8 conversion is added. Nonfinite/out-of-range working input is refused
rather than silently clipped by the new solver. No alpha/HDR support is claimed.

## Integration and persistence

- `ops/enhance.py`: validated leaves and separate active-support predicates, while
  `SUBS` remains exactly three mask planes. Both new leaves use the teeth plane.
- `teeth_colour_apply.py`: NumPy and Torch hosts call the same native solver.
  CPU transfer is limited to the nonzero support bounding rectangle. This is not
  a GPU kernel or a latency claim. No numerical fallback exists.
- `people_effects.py`, `people_pipeline.py`: actual target-local source preparation,
  canonical overlap ownership and the same common geometry warp for RGB/support.
- `vram.py`, `brow_shape_consumers.py`, `export.py`: legacy preview, joint-geometry
  route and regenerated full-resolution export support, including strict-mode
  rebuild when transitioning into/out of the new controls.
- Native/UI transport exposes actual independent child sliders. Canonical people
  targeting, overrides, inheritance and existing transaction/undo owner are reused.
- Enhancement preset scope serializes scalar intent only. Target-local support is
  rebuilt; no source mask, landmark or FaceRef is copied. Canonical batch transfer
  validates the new leaves through its existing target-owned source and rendering
  path rather than a second batch implementation.
- Original/derived-source consumers retain their existing identity gates. No
  original-image analysis fallback or guard bypass is added.
- Packaging stages the actual Rust library and source/licence, never runtime builds.

## Explicit remaining limits

This closes source paths for two previously missing controls, not the whole teeth
family or a functional acceptance. Teeth blemish/brace removal, edge completion,
alignment and replacement with new teeth are not implemented by this colour solver.
Dedicated teeth recovery is not present and is not required by these exact three
entries; unrelated recovery brushes must not be labelled as tooth recovery.
Natural-photo boundary leakage, perceived whiteness, restorations, colour casts,
RGB16 export round trips, device transfer cost, memory and packaged binary loading
all require actual authorized tests. Existing old acceptance data used procedural
portrait fixtures and cannot validate these new controls.

Generic legacy preset application onto a returned creative source remains explicitly
refused by the existing derived-transfer module allowlist and a second guard before
any `_precompute` access. This slice does not pretend an original-source precompute
is derived-source evidence. Direct derived people controls and the explicit reviewed
confirmed-face parameter batch route use genuine effective-source analysis. A
separately adapted derived legacy-preset route remains unfinished.

The native polling callback is carried through both hosts. Export uses its existing
progress/cancellation callback; preview uses the engine shutdown flag (not the benchmark stop event). This does
not introduce a new asynchronous per-slider cancellation job or responsiveness
claim. Native numerical loops and staging copies are still unmeasured.
