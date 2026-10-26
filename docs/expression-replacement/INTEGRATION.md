# Current-photo manual expression replacement integration

Requirement: **LNX-REF-PC-32468-C-0e5f836ef1**. Status: source connected,
manual-assisted partial coverage; automatic mode and photographic acceptance are
NOT complete. All product execution, builds, typechecks, tests and inference are
UNRUN. The earlier isolated-core notes describe that earlier boundary, not the
current integration status.

## Actual path

- PC-32468 opens an App-lifetime controller and a dedicated review workspace.
  Hiding the workspace does not discard a pending save. Explicit source capture
  renders all current edits, crop and repair, then independently analyzes those
  captured pixels with the existing installed MediaPipe backend.
- The native file picker supplies another real local photograph. Both canonical
  assets retain original-file provenance. Identical original files are refused;
  the user explicitly confirms person identity, session, visibility and pose.
  No original-image analysis is relabelled as edited-source analysis.
- Actual native-resolution face crops use source pixel centres. Eight stable
  measured contour/nose anchors align donor pixels without deforming the donor
  eye/mouth expression back to the old expression. The Rust multiband result is
  already fused once; its diagnostic fusion mask is not applied again.
- Users paint add/erase fusion coverage in source coordinates, inspect actual
  complete before/after/fusion PNG projections, and acknowledge their exact hashes.
  PNGs are RGB8 presentation only. Numerical source, crop and output stay linear
  float32; no proxy is promoted as a full-resolution result.
- Apply consumes the exact candidate once through the existing canonical
  CreativeHost new-image transaction. A new document/recipe, private empty people
  context and independent derived base are created. The original physical-file
  family remains linked for relocation/package validation, using a distinct
  positive copy number; original file bytes and the original recipe are unchanged.
- The new document stores actual base and result-patch layers through existing
  immutable asset persistence. Existing derived-source analysis/export/history
  paths apply to that returned base. No donor geometry or masks are copied to
  another person's editable portrait graph.

## Modules and ownership

`expression_replacement_source.py` captures immutable edited pixels and fresh
analysis. `geometry.py` validates measured crops/support; `native.py` binds the
versioned Rust ABI; `stage.py` owns isolated full-image candidates. `jobs.py` owns
read cancellation ingress; `host.py` owns retained leases and the exact one-copy
transaction. The native protocol/mailbox validates original UTF-8 packet hashes,
full PNG byte hashes, engine epoch and candidate receipts. App only supplies the
actual row/load identity and its separate UI invalidation counter. UI doc_rev is
NOT treated as the engine's canonical document revision.

Capability requires the matching protocol, operation ID and installed Rust ABI.
The build/staging scripts are authored but not run. Missing code/models reject
rather than substitute a filter or fabricated candidate. This is a statically
registered replaceable module, not arbitrary hot-loadable plugins.

## Cancellation, receipts and resource bounds

Reader-thread cancellation sets only the matching read's event. Actual cancelled
receipts wait for the original operation to unwind. An inference call may finish
before observing cancellation. Already-completed reads arriving after cancellation
are discarded, not called force-cancelled. Native epoch changes retire only
read-only leases; unknown apply requests remain fenced and never retransmitted.
Outer-dispatch rejection emits the exact request-specific no-write receipt only
when no mutation began. Apply is never cancelable. Native process loss cannot be
resolved as successful cancellation or safe retry; inspect/reopen a known saved
project rather than repeat an uncertain copy.

Capture stores are job-local. The host retains only current target, donor and one
candidate; immutable candidate assets enter the existing transaction only at
apply. Existing explicit working budgets, crop limit 1024, transport limits and
native reservations may refuse large images. These are admission estimates, not
measured process peak-memory or speed claims. No 24MP/all-resolution claim.

## Remaining original requirement and usability gaps

- Automatic bad-expression detection, best-expression ranking, same-person recognition,
  default automatic replacement and full group automation are absent. Bounded
  original-eye-aperture ordering within existing user-confirmed associations is
  now authored; see `DONOR-HINTS-V1.md`. It is not automatic donor selection.
- Native crop sides above 1024, transparency and HDR are refused, not resized,
  flattened or clipped. No invented 3D pose or semantic occlusion measurement.
- Full source numerics are retained, but review is a bounded full-frame projection,
  not native-resolution visual inspection of every output pixel.
- Fusion is editable before apply. Saved layers support ordinary layer edits;
  reopening does not reconstruct the donor acquisition or parametrically regenerate
  its fusion. The donor and effective fusion asset are not claimed as a reopened
  editable expression session.
- Only explicit new-image return is connected. Update-original, preset/batch,
  automatic variants and optional alias variants are not claimed.
- Core unchanged-outside-fusion contracts do not establish byte-for-byte equality
  of a full composited image (e.g. signed zero normalization). No photographic
  quality, identity preservation, numerical performance or runtime acceptance.
