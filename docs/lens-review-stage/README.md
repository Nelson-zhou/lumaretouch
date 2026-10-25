# Lens source review stage: AUTHORED / UNRUN

This isolated source adapter implements `ui/src/lensBlur/model.ts` and the genuine
ABI-1 aperture bridge. It does not register a command, publish a document,
maintain a second history owner, or complete the end-to-end lens feature.
Only the two new Python modules and this documentation directory are owned here.

## Host interface

All full-data functions require `budget=Budget(...)` and optionally
`cancelled=predicate`. No NumPy, native DLL, inference, image decoder, download,
or filesystem discovery occurs on module import. All image creation here is
runtime work, not a photograph or acceptance result generated during authoring.

- `Budget(max_bytes, max_candidate_taps=250_000_000,
  max_refinement_pixels=64_000_000, timeout_seconds=120.0)` validates explicit
  resource ceilings. Bytes are 16 MiB through 4,000,000,000; timeout is positive
  and at most 600 seconds. Defaults are admission limits, not speed promises.
- `capture_source(asset, owner, *, budget, cancelled=...) -> CapturedSource`:
  accepts the actual complete edited creative RGBA asset, not an original-file
  identity attached to edited pixels or an RGB preview. `owner.source.sha256`
  must equal `asset.id[7:]`, dimensions must agree, and the complete canonical
  asset identity and float32 premultiplied linear-sRGB-D65 pixels are validated.
  `owner`, `asset`, and `source_image` properties return fresh dictionaries;
  pixel/profile/original/PNG backing data are immutable bytes.
- `capture_depth(wire_asset, source, *, budget, cancelled=...) -> CapturedDepth`:
  accepts an actual source-owned `manual/user_supplied_depth` u16-le full-frame
  raster. Exact dimensions, orientation, mapping, canonical Base64, byte count,
  binary digest and provenance are required. The host authenticates the user
  selection; strings or a digest are not proof that a user supplied a raster.
- `prepare_manual_plane(command, source, *, budget, cancelled=...)
  -> CapturedDepth`: accepts exactly the UI `prepare_manual_plane` command,
  including `acknowledged_manual: true`, current owner, request and session.
  Produces only the declared quantized constant; acknowledgement ID is the
  original request ID. The capture is additionally bound to that session. The
  generic raster importer cannot create this path merely by supplying its label.
- `context(source, session_id, depth=None) -> dict`: returns exact `LensContext`.
  Without depth, the state is `manual-required` with no raster. With a plane,
  source PNG identity is unchanged and the message explicitly distinguishes
  an artificial editing baseline from AI or measured scene depth.
- `prepare(command, source, depth, *, budget, cancelled=...) -> Candidate`:
  validates and captures the exact `LensPreviewCommand`, rasterizes corrections
  on the genuine full source, calls `lens_aperture_native.apply`, validates the
  canonical output asset, and returns actual full-frame before/after PNGs.
- `Candidate.review`, `output_asset`, `token`, `recipe_sha256`, `no_change`,
  `refinement_sha256`, `processing_depth_sha256`, `retained_bytes` are the return
  boundary. `Candidate.validate_apply(command)` only correlates an exact
  `LensApplyCommand` with the candidate; it does not commit, verify a live owner,
  prove user presentation, or issue a successful receipt.

Captured records contain only immutable bytes/scalars. A frozen dataclass around
a mutable dict or ndarray is deliberately not used. Returned dictionaries cannot
mutate the saved candidate. Do not deserialize or fabricate captured Python
objects from a wire request; construct them through these source-stage factories.

## Existing owner and lifecycle responsibilities

The parent must freeze current complete editing state and call the existing
`creative_document_base.capture_current_asset` using a **job-local AssetStore**.
That existing helper interns intermediate import/capture assets. Passing the
long-lived document store to it would leak failed/cancelled acquisition data;
this adapter takes no AssetStore precisely to avoid that side effect.

The parent supplies the real document ID, epoch and canonical revision, and owns
an authenticated immutable capture of the full edited source. It must pass a
cancellation predicate covering source replacement, document/epoch/revision,
session cancellation and newer-preview invalidation. Recheck this owner at the
atomic existing history transaction, after preparation and immediately before
publication. Stage correlation does not replace these live-state checks.

The host retains bounded session/candidate leases outside transient UI mounts.
Drop old captures/candidates on replacement, confirmed cancel or expired lease;
fence the entire cancelled session against late completions. An unresolved apply
is not cancellation. Apply needs the same candidate token, recipe digest and
both PNG digests, the explicit reviewed flag, and the host's existing durable
request/receipt ledger. Never rebuild a different candidate when applying.
Intern the admitted candidate only inside the existing atomic publication path.

Neutral output is determined by exact full-resolution canonical float bytes,
not by visually equal PNGs or radius labels. Its asset is the source asset,
`no_change` is true, and the parent must preserve revision/history no-change
semantics. Native availability is still checked and the actual native bridge is
called for neutral intent. Missing native code is not a successful identity.

## Geometry and refinement

Source points are normalized centres: `(u*(W-1), v*(H-1))`. Brush radius is the
stored fraction of `min(W,H)`, not proxy dimensions. Each polyline segment is a
round-capped capsule, including a single-point stroke. Distances use bounded
float64 blocks. A stroke takes maximum capsule coverage, so repeated points and
denser pointer events do not repeatedly accumulate flow within that stroke.

Coverage is one inside `R*(1-feather)`, then `1-smoothstep(t)` to zero at `R`.
Zero feather is a hard disc. A transition narrower than float64 coordinate
resolution reduces to the same hard-disc boundary, avoiding division by zero.
Strokes composite in saved order, once each:

`result = result + (sign - result) * coverage * amount * flow`

Clear has sign -1; blur +1. Full clear is exactly -1 even after full blur.
Zero amount/flow is a genuine numerical no-op, not deletion of stored intent.
Capsule pixel examinations, whole-plane resets/compositing and final conversion
are counted before allocation. The complete vector set is rejected if over
budget; no stroke or point truncation occurs. UI limits are exactly 64 strokes,
8192 total points and 2048 points per stroke, plus the 512 KiB complete command.

Actual manual depth samples map to source centre `(x,y)` at depth centre
`((x+.5)*dw/W-.5, (y+.5)*dh/H-.5)`. Bilinear sampling clamps only at true raster
borders, uses u16/65535 in float64, and rounds once into the full-source native
float32 plane. The processing-plane digest is retained separately from the UI
raster digest. Resampling does not invent measured spatial detail.

All five aperture names map directly to the bridge; source-pixel radius is
unchanged. The native minimum falloff is 0.000001, stricter than the UI's generic
positive-unit validator. Smaller values are rejected, never silently clamped.
There is no optical, physical focal-length/f-number or proprietary-parity claim.

## Precision, images and resource admission

Canonical output retains genuine full-size float32 linear premultiplied RGBA,
including transparency, negative channels and HDR within the native bound.
Original/profile provenance bytes are retained. There is no RGB8 render path,
matte, source clipping, rescaling, screenshot or mock result substituted for it.

Before/after PNGs are display-only nearest-centre samples of those actual full
frames, with the same aspect and dimensions, at most 1280 per edge and one
million display pixels. Their RGBA alpha is explicitly quantized for display;
straight display RGB uses the existing native sRGB SDR transfer. Only this
separately labeled presentation copy clips signed/HDR values. The unmodified
float output asset is the only application candidate. PNG chunks, CRC and SHA
are created from the actual bytes; wire fields match the UI's exact PNG schema.
The original and after PNG never come from unrelated paths or URLs. Extremely
thin frames that cannot preserve the whole-frame contract at two pixels per
edge are rejected rather than stretched, cropped or upscaled.

One heavy source-stage job is admitted at a time; the slot is released in a
`finally` block on every exit. The stage combines caller source/depth retention,
conservative per-pixel working storage, native snapshots, output/immutable
conversion, brush working planes, PNG/JSON allowance and native scratch. It also
checks the actual visible CPU memory estimate and passes a total candidate-tap
ceiling to the native bridge. Each native/refinement/depth/display bounded step
polls the same cancellation/deadline predicate. Full-array hashing, immutable
conversion and canonical validation are checked at operation boundaries, not
preempted mid-library-call. No hard real-time latency guarantee is made.

Per-job admission is not an aggregate lease budget for all documents. The parent
must also bound retained source/depth/candidate objects and concurrent non-lens
work. There is no global image cache or persisted stage asset to collect after
failure. An unavailable/ambiguous CPU memory reading fails closed.

## AI and verification limits

Model-derived provenance and subject focus remain rejected in this release.
The separate optional model adapter still has unresolved exact code/config
provenance gates. No installer, inference request, learned confidence or subject
mask is fabricated here. Supplying a `model` label cannot bypass that gate.
Enabling a future model requires a reviewed integration retaining its genuine
full-precision processing field, not converting the UI u16 map back into a
claimed original float model result.

Source reading/editing and file hashing are the only authoring activities.
Product imports/execution, AST/static parser checks, tests, build, typecheck,
native execution, image generation, inference, installs, downloads and real-photo
acceptance are **UNRUN**. The fixtures below are specifications, not executed
results. Shared native/server/history/UI registration and end-to-end verification
are outside this isolated stage's ownership.
