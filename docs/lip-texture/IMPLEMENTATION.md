# Lip dark-furrow attenuation: partial requirement, acceptance UNRUN

## Exact scope and non-duplication

`LNX-REF-PC-32464-C-b6315c40ca`, PC-32464 `面部祛瑕疵/唇纹修整`, baseline traceability `control:PC-32464:13`.

The [official guide](https://www.pixcakeai.com/guide/32464), updated September 17, 2026 and read October 24, describes conspicuous lip texture, dry/dead skin and small cracks. It specifies no numerical range or algorithm. This slice implements **唇部暗细纹减淡**, a bounded original dark-furrow attenuation, and remains **partial** against that broader ID. Dry flakes, missing surface, deep cracks and reconstruction are not implemented or advertised.

Existing lip makeup controls saturation, brightness and dimensionality while retaining high-frequency lightness. Existing lipstick materials can reduce microcontrast, but that is coupled to material/tint/opacity, not a separate measured furrow operation. Existing facial wrinkle support excludes lips and treats surrounding skin. None is silently relabeled or changed.

## Method, primary evidence and licenses

The original GPL Rust method measures paired lateral source samples, their agreement and along-furrow continuity inside a measured lip surface. It selects a bounded narrow dark-line proposal and partially lifts it with a common linear-RGB gain, constrained by actual neighbouring evidence and gamut. It is not a broad blur, morphology alias, generic heal, generative model, semantic dryness detector or new lip material. Detection is frozen on the actual effective repaired source; it does not iterate on already corrected pixels.

[Steger's author-hosted technical report](https://mv.in.tum.de/_media/members/steger/publications/1996/fgbv-96-03-steger.pdf) discusses lateral line surroundings and asymmetric contrast, and warns that local gray-difference criteria alone create false hypotheses. The [published paper record](https://ieeexplore.ieee.org/document/659930/) identifies the related 1998 work. This is conceptual grounding only: the implementation is not Steger's Gaussian-derivative, differential-geometric or subpixel detector, and the research does not validate cosmetic lip repair. The copyrighted paper is not an implementation license. No external implementation is copied or represented as licensed Steger code.

Existing [official MediaPipe topology](https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/mediapipe/python/solutions/face_mesh_connections.py) supplies distinct inner and outer lip chains under its existing Apache-2.0 attribution. New source uses the already retained topology contract. No additional code, models or weights are downloaded or executed.

## Ownership and support

Exact FaceRef, verified canonical detector/semantic evidence and normalized 478-point digest bind geometry to the current original or immutable derived source. The existing excluded semantic plane is authenticated through its canonical analysis owner; it has no invented independent producer-proof record. It is a known-occluder veto, not lip segmentation or a face-skin certainty score. Lipstick visibility consent is not reused.

A separate measured lip ring protects outer vermilion boundaries, inner mouth/seam/cavity, corners and every other retained same-source face box, whether enabled or disabled. The source-window permission field has an admitted interior and inward feather; its unit values mean allowed geometry, not model certainty. Complete native sample footprints and intervening support must stay in the same surface without jumping across holes or the upper/lower seam. Insufficient valid interior is distinct from observing no eligible narrow dark furrow.

Normalized geometry is rebuilt at the actual render dimensions. Full-resolution export observes and solves its own source; it never stretches a preview correction. Strict local radius, dimension and memory bounds can refuse unsupported resolution instead of downsampling or widening applicability. No face-box fill, inferred lip pixels or copied target analysis is allowed.

## Canonical integration

- Strict versioned scalar recipe `lnx.lip_texture.v1`: version 1, amount in [0,1], exact zero neutral. No masks, model outputs, source samples, radius or measured axes persist as portable intent.
- Capability checks the actual packaged native ABI; readiness does not establish usable anatomy or photographic quality. Runtime does not compile or substitute another effect.
- Canonical people edits/history, nested active/undo/redo project validation, malformed no-face scalar and passthrough guards.
- One immutable source-owned local delta, before lip makeup and then the unchanged common geometry sampler. Native solves full windows, not independently per export tile.
- Common source-vector composition limits one scalar against actual upstream SDR headroom, without channel clipping. The existing brow composition algebra was extracted unchanged into a neutral shared helper with stable wrappers; its prior recipe and errors are preserved.
- Dedicated UI control, actual effective-source provenance versus shared intent, explicit selected strength, neutral recovery and stale/pending/uncertain owner fences.
- Presets and confirmed target-person transfer carry only amount and rebuild support from each target. Unsupported generic derived transport remains fenced. Requested target failures do not become silently skipped successful edits.

Existing canonical before/after preview is the review surface. This slice does not claim a persistent manual-painted support receipt or complete occlusion classifier.

## Remaining limitations

Natural grooves, painted lines, fine hairs and small cracks cannot always be distinguished from these measurements. Only a narrow orientation/scale and photometric class is addressed. Bright flakes, broad folds, deep/crushed fissures, missing tissue, deliberate lip art, unstable highlights and insufficiently resolved or occluded anatomy are not repaired. No moisturization, medical treatment, hidden-surface recovery, full official parity or photo-quality guarantee is claimed.

Native common linear RGB ratios concern the isolated source calculation. Composition against prior edits, later lipstick/colour and geometry can alter final appearance; there is no final hue or physical component-separation promise. Wider retouch alpha/HDR support remains unfinished and is not manufactured by clipping.

All numerical, native ABI, build, UI, photo, preview/export parity, memory peak and performance acceptance is **AUTHORED / UNRUN**. Source-connected wiring is not functional acceptance.
