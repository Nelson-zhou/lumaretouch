# M13 optional generation foundation: NOT AVAILABLE

Source baseline: d62cccb3d4d28a230823391ae3dbe80fcc235e26. Authored source and
static inspection only. No dependency installation, model download, imports,
compilation, tests, inference, photographic review or performance measurement.
Neither requirement below is complete, source-connected to the product UI, or
functionally accepted. This isolated foundation must not add a completed ledger ID.

## Exact official scope

- LNX-REF-WF-158249-a8278ceb16, AI祛路人: automatic candidate selection;
  brush/lasso additions and subtraction, cancel/invert, feather 0–1000;
  selection-to-layer; two candidates per generation; editable mask and batch recipe.
- LNX-REF-WF-127932-22318776c0, 祛路人层属性: result switching and regeneration;
  mask density, feather, add/subtract. The official density range is not published.

Supplied manual lines 753–758 and 916; mapping records at lines 14018–14029 and
14390–14401. Primary live sources read 2026-10-23:
https://www.pixcakeai.com/guide/158249 and
https://www.pixcakeai.com/guide/127932 . Protecting the main subject is an additional
safeguard here, not a claim that the adjacent smart-removal tool's documented
protection control is an exact AI-passerby control.

## Real model selection, not deterministic heal

Kandinsky 2.2 uses the actual prior and inpaint decoder, with two independent
seeded prior/decoder calls. Existing deterministic `ops/inpaint.py` is not this
model. The repository's self-built `ops/lama.py` is not the official LaMa
architecture and is not assumed compatible with official LaMa weights.

Official project https://github.com/ai-forever/Kandinsky-2 directly links:
- https://huggingface.co/kandinsky-community/kandinsky-2-2-prior
  revision 9fc51ad5732afc5d031724219d22e6c42179c5a8
- https://huggingface.co/kandinsky-community/kandinsky-2-2-decoder-inpaint
  revision db790ad5cbcabed886f069ef2710774657621702

Both model cards declare Apache-2.0. Diffusers v0.29.0 is Apache-2.0, pinned at
39aa3909e8e2dfe30f4807aedaadf42c1d8b1a8f. Licences:
https://github.com/huggingface/diffusers/blob/v0.29.0/LICENSE and
https://github.com/ai-forever/Kandinsky-2/blob/main/license . This is original adapter
and numerical code; no upstream source, dependency distribution or weights are
copied. A future packaged distribution must include applicable licences/NOTICEs
for the dependencies and model files it actually distributes. This research is
not proof of an arbitrary user-supplied checkpoint's identity or rights.

## Verified source contract

Read explicit `KandinskyV22PriorPipeline` and `KandinskyV22InpaintPipeline` at the
pinned Diffusers tag. Inpaint Git blob b5ba7a0011a14058a01f53c34ef5dfe476e28708;
prior blob f2134b22b40b70ab26e3225de08cead28542f34f. Their paths are under
`src/diffusers/pipelines/kandinsky2_2/` in the upstream repository.

Image tensor input is encoded working-sRGB [-1,1]; white mask means repaint.
Mask thresholding and latent neighbour expansion mean decoder preservation is NOT
pixel identity. `output_type='pt'` returns raw decoder values. The adapter applies
the upstream numpy-output SDR transform `(sample+1)/2`, clamped to [0,1], only to
GENERATED values, retaining float32 rather than using Pillow/RGB8. Raw digest,
range and clipped component counts are receipted. Nonfinite/gross outliers fail.
This explicit model-output transform is not HDR support and never clips source.

## Source and patch limits

Original Rust preparation accepts full canonical linear-sRGB-D65 premultiplied
RGBA float32 plus full-source selection/protection coverage. Opaque SDR only,
including validation outside the ROI; transparent/HDR input is refused. RGB16
source detail is not quantized through RGB8. Original files remain unchanged.

An integer native-pixel ROI is at most 768×768. RGB uses edge padding to 768²,
without resampling. Padding coverage is zero. Any positive protection excludes
that source pixel completely. Initial soft selection is retained independently
of the binary model mask. Final fusion coverage cannot exceed eligible selection;
its density is an implementation parameter, not a claimed official numeric range.
Rust converts actual generated SDR float pixels to linear premultiplied RGBA.
Outside coverage/protection, transparent patch pixels leave the original untouched
when the canonical compositor is eventually connected.

The source budget is 32 million pixels; this is not a runtime memory/speed claim.
The model generates only a bounded context patch, not a native 24MP image. Larger
removal regions require a separately reviewed algorithm and are not resized
silently. Floor/texture reconstruction, subject identity, repeated patterns and
quality are unvalidated. Two genuine attempts can coincide; no fake diversity.

## Blocking admission evidence

Five published safetensors SHA256s are recorded in the bundled manifest. Exact
weight sizes, pinned-revision membership, config/tokenizer byte hashes and remaining
runtime compatibility pins are not yet substantiated. Hugging Face metadata reads
failed/cache-missed and a tokenizer page returned HTTP 429; requests stopped.
No alternative was used to evade that rate limit. Model bytes were not downloaded.

`verify_pack` intentionally returns `upstream_manifest_incomplete` before model
imports. Owner-provided checksums cannot promote themselves into reviewed upstream
pins. There is no ready pack or installer in this slice, even if model files exist
locally. Exact dependency version metadata alone does not authenticate installed
code bytes; completing code-distribution/hash admission is also a release gate.
No generation endpoint or UI control is enabled, and no dummy candidate is shown.

## Actual source boundaries and next integration

- `creative_generation_manifest.py` holds incomplete reviewed pins explicitly.
- `creative_generation_pack.py` verifies local inventories only; no network, caches,
  installer, pickle files, symlinks or owner-authored self-approval manifest.
- `creative_generation_backend.py` calls real explicit prior/inpaint classes twice,
  checks cancellation between steps/stages, and returns an atomic pair plus evidence.
  Cancellation cannot interrupt an individual model kernel or weight loading.
- `core/creative_generation_patch` and its Python bridge prepare/fuse actual pixels.
  The build script is authored only, not invoked by application startup.
- `creative_generation_stage.py` binds immutable canonical source/mask asset IDs,
  native ROI, seeds and settings, then stages two content-addressed protected patches.
  It writes no document, asset store, disk, history or UI state. Its returned patch
  placement is the source ROI origin; ignoring this would misplace the result.
  It does not claim that an input mask was user-reviewed. No live route calls it.

Remaining material work, in dependency order:
1. Verify missing upstream metadata, complete authenticated runtime distribution
   admission and establish a separately installed compatible pack. No download was
   performed here. Exact versions alone are insufficient code authentication.
2. Validate actual numerical, runtime, cancellation, resource and photo behavior on
   an authorized machine. CPU availability is not a feasible latency guarantee;
   optional CUDA compatibility/VRAM requirements have not been measured.
3. Add versioned candidate records to creative document schema, with every candidate,
   frozen input, selection/protection and editable fusion geometry retained by
   package/history/asset reference traversal. Existing image/group schema is not
   silently repurposed and inactive candidates must not be garbage-collected.
4. Add native bounded job/revision ownership, pending fences, receipts and uncertain
   outcome reconciliation. Commit through the existing single creative history
   owner; review both candidates before publishing, preserve original source.
5. Wire source-space manual selection/lasso/feather, actual protected-subject review,
   two-result switching/regeneration and editable fusion. Regeneration uses its
   declared frozen input, not an accidental already-generated composite.
6. Adapt canonical return/export and source-only preset/batch recipes with target-local
   selection/protection/review. Never copy generated masks or subject analysis across
   images. Existing opaque SDR return guard remains unchanged.
7. Select/license/implement a genuine automatic passerby proposal separately.
   OneFormer semantic masks and prompted SAM2 are not unwanted-person classification.

Neither the two exact M13 requirements nor all 32 creative tools are complete.
Other material handbook work should continue while pack verification is unavailable.

Mask-byte authenticity and matching dimensions do not prove that a user selected
those pixels on this source. The isolated staging API records the association but
cannot authenticate its provenance. A future reviewed controller must issue and
verify source/job-owned mask receipts; passing a same-sized foreign mask directly
to this low-level API is not a reviewed transfer path. Effective selected pixels
outside the requested ROI are rejected by Rust rather than silently discarded.
