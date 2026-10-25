# Bounded storage and integration ownership

Status: DESIGN ONLY / no streaming backend or integration was implemented here.

## 1. Proposed interfaces

Use original Rust types behind a small region ABI, not Python ndarray callbacks
from the innermost numerical loop. These are proposed contracts, not existing APIs:

    ImmutableImageDescriptor
      extent, stride/format, canonical asset ID, content digest,
      original/profile blob IDs, owner/revision/epoch, immutable lease ID
    ImageRegionReader.read(rect, caller_owned_buffer)
      exact source-grid pixels, no rescale, no implicit color transform
    DepthRegionReader.read(rect, caller_owned_buffer)
      existing u16->bilinear f64->f32 mapping or verified constant certificate
    RefinementRegionReader.read(rect, caller_owned_buffer)
      exact ordered stroke rasterization or retained f32 field tiles
    PrivateImageWriter.write_core(rect, validated_f32_pixels)
      each source-grid output pixel exactly once; duplicate/overlap rejects
    PrivateImageWriter.finish()
      complete extent, canonical hash, content hash, readonly lease
    PrivateImageWriter.abort()
      discard uncommitted result and release reservations

Each read has exact coordinates, checked byte lengths and checked overflow.
Readers supply only requested regions plus declared halo. Metadata alone does
not establish immutable bytes or matching source identity. A writable ndarray,
path, mutable mmap, or file descriptor with writable aliases is insufficient.

Host freezes owner/recipe and holds input leases. Native code receives only
admitted buffers or trusted read-only descriptor handles. It never opens an
arbitrary caller-supplied path. Native callbacks cannot mutate/free inputs,
reenter a job, or publish partial output. Region validity is checked once at
ingest and, for untrusted external storage, verified again against chunk hashes.

## 2. Storage implementation

Prefer an original uncompressed little-endian row/tile blob for the first
implementation. It preserves every f32 bit and makes byte budgeting explicit.
JPEG/PNG/RAW are not random-access canonical tile stores just because they are
files. OpenEXR FLOAT tiled storage is a researched alternative, but adopting
it requires a separate codec/build/dependency audit; HALF would lose precision.

Private staging:

1. Reserve prospective disk bytes, resident buffers and retained leases before
   allocation. Check quota and filesystem free space; ENOSPC can still occur.
2. Create a job-private file with exclusive creation, restrictive access, no
   symlink following and no caller-controlled path traversal. A private directory
   plus content ownership is required; chmod alone does not close writable fds.
3. Write validated row-major canonical data or indexed tiles with exact coverage.
   Keep every writable handle private to the writer.
4. On finish, ensure coverage, flush and close all writer aliases, then create a
   read-only lease. Verify complete expected length and chunk/content hashes.
   Use crash-safe atomic metadata publication; a flushed pixel file without its
   complete manifest is not a completed candidate.
5. Cancellation/expiry deletes only owned uncommitted files. Published document,
   history, pending/unknown commit and export leases prevent collection.

Do not use whole-file mmap and claim a hard resident bound: page cache and dirty
pages can count toward a cgroup and grow across the whole file. Prefer bounded
explicit pread/pwrite buffers, bounded writeback, and measured cgroup/RSS
accounting. Linux cache advice is only a hint, not a proof. Disk-backed output
also requires disk quota and crash cleanup, not merely a small heap.

Retain original encoded bytes and ICC as independently identified immutable
blobs. Deduplicate by verified identity and reference-count/lease them, including
document/history/pending transactions. Do not sever original provenance to save
memory. Shared bytes should be charged once physically, with explicit logical
record accounting where existing policy requires it.

## 3. Preserve canonical identity without materializing full bytes

`creative_document_assets._identity` hashes a domain prefix and canonical JSON
header, followed by the length and bytes of content, original and ICC in that
order. Implement the SAME byte stream incrementally. Storage location must not
enter that identity. Tile layout is not a license to change row order or float
endianness. With out-of-order tile writes, finish performs a bounded row-major
read/hash pass. Do not hash concatenated tiles and call it the existing asset ID.

Separate content digest, full canonical asset ID and display PNG digest. They
are not interchangeable. Verify no-change by exact full content bytes plus
unchanged relevant metadata, using bounded comparison, not a perceptual test or
display comparison. The original and result remain distinct documents even
when canonical pixel identity is unchanged, as the existing return contract says.

Source/display extraction can gather the same bounded source-centre samples
from the immutable image reader. Only the separately labeled SDR PNG is reduced.
The result document and final export must consume full-resolution pixels.

## 4. Field streaming and paint locality

Depth interpolation must reproduce `_full_depth` at GLOBAL source centres:
((x+0.5)*depth_width/source_width - 0.5), and similarly for y, clamped only at
actual depth-raster edges. Preserve f64 interpolation followed by one f32 store.
Never rescale depth independently per tile. The small original depth raster,
its provenance and its source identity remain immutable.

For paint, build a bounded spatial index of complete stroke segments. Per
output field tile, visit only intersecting segment bounding boxes, but preserve:

- all original points and their ordering; no decimation;
- maximum capsule coverage once per stroke, stored as f32;
- stroke compositing order and f64 update from old f32/coverage f32;
- exact round caps, feather function, amount, flow and clear/blur sign;
- exact q=-1 plateaus, including after a preceding blur stroke.

Zero/coverage fills and compositing occur only in affected tile regions rather
than rescanning the full image once or twice per stroke. Count actual capsule
evaluations, touched-area zeroing/compositing and index work. Keep the existing
64M refinement ceiling for actual examined pixel work; replacing eliminated
full-grid scans is an algorithm change, not a cap increase. Adversarial long
overlapping polylines may still exceed it and must not lose points to fit.

To avoid recomputing painted fields for overlapping FFT halos and classification
passes, materialize validated f32 field tiles once to bounded temporary storage,
or cache a provably bounded set and account for recomputation. The first design
uses retained temporary field blobs and deletes them after candidate completion.
Do not allocate N histogram entries while claiming a small tile working set.

## 5. Concrete memory/space example

For a 512×512 FFT and a 254×254 output core, a complex f64 plane is 4,194,304
bytes. A conservative prototype reserves a 128MiB native scratch lease for
kernel/work/transpose planes, input halo, scalar fields, tile accumulators,
FFT plan/scratch and bounded indexes. Actual buffer ownership and allocator
overhead must be enumerated before integration. Display retains its separate
existing 96MiB reserve. One worker initially; reservations are not multiplied
silently by thread count.

At 24MP, full canonical RGBA is 384,000,000 bytes, output the same, and each
materialized f32 depth/refinement field is 96,000,000 bytes. Source + output +
two full fields is 960,000,000 disk bytes before original, ICC, manifests and
crash-safe publication overhead. Original encoded bytes can be up to the
existing 512,000,000-byte cap. A source/output pair with a 100MB original and
small ICC is approximately 868MB of distinct retained content before previews.
This can fit the existing 1GB retained-payload ceiling; a pair with a 512MB
original cannot. Do not silently redefine that ceiling as 'RAM only'.

Keep unchanged host work <=2,000,000,000 bytes, retained payload <=1,000,000,000
bytes, canonical asset/store limits, 120-second job deadline, and the actual
global available-memory check. Any separate temporary disk quota must be explicit
and bounded, not unlimited spill. Charge shared provenance only once if that
accounting change is implemented and verified; do not assume current accounting
already deduplicates separate source/candidate leases. A file-backed implementation
does not by itself make every allowed original-file size admissible at 24MP.

The target incremental resident footprint is bounded by configured buffers and
leases rather than 128N. This is not a measured RSS result, nor permission to
ignore existing decoded images, undo, model reserves, Python objects, page cache
or other tasks. Admission must enumerate overlap between pipeline phases.

## 6. Current shared integration blockers

Every path here needs an explicit owner. None is fixed by the new docs:

1. `creative_document_assets.py`: `validate_asset`, `make_asset`, `AssetStore`
   require immutable Python bytes. Add a separate reader-backed asset schema or
   backend with complete validation/identity/lease support. Do not pass a path
   into the old `content` field and weaken validation.
2. `creative_document_base.py`: `_pixels`, `export_source`, capture/import and
   `export_float` are whole-array consumers. The 96N edited/RAW capture admission
   blocks ordinary 24MP non-neutral photos before lens rendering. A region-capable
   edited-source renderer is a separate shared-pipeline milestone.
   `creative_document_import.import_bytes` and `_tiff` also preflight original
   JPEG/PNG/TIFF decoding at 96N + 2×original_bytes. Even a neutral ordinary file
   cannot bypass that import unless a canonical baseline already exists.
3. Decoder/geometry/effect chain: classify every active operation as bounded
   pointwise/local/global or nonlocal. Local operations compose their exact halo;
   crop/rotation/warps declare true source bounds, not a blanket radius. Global
   analysis may use a separate full-source streaming reduction only if numerically
   compatible. Unsupported active operations block capture; do not omit them.
   RAW demosaic and some codecs may still need full decode or codec-owned memory.
   Admit this honestly, or implement a verified streaming decoder. Merely adopting
   libvips does not make all existing Lumaretouch operations lazy/streamable.
4. `lens_aperture_native.py` and ABI 1: whole-array snapshots are intentional for
   immutability. Keep ABI 1; add a region-based API rather than removing snapshots
   from an interface still accepting caller-owned mutable arrays.
5. `lens_blur_stage.py`: CapturedSource/Candidate content fields and output asset
   property are bytes. New descriptors and leases must propagate through review,
   expiry, cancellation, display and no-change checks without `read()`/`tobytes()`
   of a full image at the final step.
6. `lens_blur_host.py` and `creative_document_host.py`: preserve one-shot return,
   unknown-outcome fencing and authoritative readback. `require_photo_return`,
   `host.assets.intern`, state snapshots and new-image publication all need the
   reader-backed asset contract before a streamed candidate is applicable.
7. Project package/history/export: persistence and reopen must own the canonical
   blobs, not a temporary lease that expires after 180 seconds. Final encoders
   must consume full-resolution rows or explicitly admit any whole-array bridge.

A limited transition may process an already-existing immutable canonical byte
asset through borrowed read-only regions, then produce a whole-byte result if
the exact peak and retained caps allow it. This is a useful bounded accelerator
for that input subset, but is NOT end-to-end streaming or the final design.

## 7. Proposed module ownership, no shared edits by this design lane

- Numerical owner: NEW `core/lens_cohort/{lib.rs,contract.rs,plan.rs,
  kernel.rs,fft.rs,cohorts.rs,residual.rs,gather.rs,validation.rs,tests.rs}`.
  Original GPL-3.0-or-later algorithms; optional audited FFT dependency isolated
  behind `fft.rs`. No file I/O, host lifecycle, model inference or document commits
  in aperture math.
- Storage owner: NEW `engine/src/lumaretouch_engine/creative_asset_regions.py`
  and an isolated native blob/region I/O module. Own immutable manifests,
  incremental identity, private writers, leases, quotas and collection. Shared
  asset/state/project modifications require their existing integration owner.
- Field owner: NEW `engine/src/lumaretouch_engine/lens_region_fields.py` plus
  native tile rasterization if needed. Own exact mapping, stroke bounds/index,
  hashes and field certificates, not UI provenance policy.
- Lens integration owner: NEW `lens_fullresolution_native.py` and
  `lens_fullresolution_stage.py`; controlled edits to existing host/mailbox/UI
  capability and version schemas. Own aggregate admission, cancellation and
  final review. Do not duplicate the common commit/history implementation.
- Edited-source owner: controlled extension of existing capture/export pipeline
  and decoder interfaces. Own whole current-edit fidelity and geometry. This is
  a prerequisite for claiming general 24MP photo support, not a lens-worker alias.
- Verification owner: fixtures and acceptance under this directory or a separately
  assigned test directory. Run only when execution is authorized; preserve UNRUN
  otherwise. Track per-kernel/full-resolution/source/paint/depth scope separately.
