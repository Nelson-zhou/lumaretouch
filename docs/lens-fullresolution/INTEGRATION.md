# Explicit v2 current-photo integration

Requirement: LNX-REF-WF-165438-165adae6a7. Status: source-connected manual
partial, all runtime/numerical/photographic acceptance UNRUN. This document
supersedes the earlier design-only status for the specific paths below, not
its broader open requirements. It does not alter earlier frozen manifests.

## Implemented source path

1. Dedicated lens wire3 negotiates actual packaged direct-v1/cohort-fft-v2
   renderers through capability2. UI selection and separate v2 math consent
   invalidate old review/ACK; unavailable versions never silently fall back.
2. New capture explicitly opts into bounded JPEG/PNG import only when the exact
   export snapshot is neutral. Existing canonical bases need no re-import.
   Non-neutral edits, TIFF and RAW keep their old complete-source path and
   original memory gates. Original file/provenance/history are unchanged.
3. The new importer retains integer decoder samples and does existing ICC and
   native transfer in bounded blocks directly into one private canonical sink.
   Genuine PNG16 low bits, orientation and alpha contracts remain represented.
   A final immutable bytes copy and named codec/ICC reserves are counted.
4. Recipe2 binds lnx.lens_blur.cohort.v2 and math identity
   cohort-fft-f64-v2-00020001. Recipe1 retains its old keys and original Rust
   renderer; no saved numerical intent is automatically reinterpreted.
5. Actual acknowledged constant u16 depth is checked, converted to its actual
   f32 value and supplied as a scalar. No full depth array is created. Stroke
   staging uses each stroke's real source rectangle, not full-plane coverage
   scans; capsule, feather and stroke-composition math is unchanged in intent.
6. Native create validates immutable source and plans all work. Ordered tiles
   write a private full-size sink, finish must succeed, then the job/tile release
   precedes the counted immutable copy. The full candidate is canonical float
   data; PNG display sampling never becomes final output.
7. The existing exact before/after/source/output ACK, distinct new-image return,
   history, cancellation and query-only uncertain-write ownership stay in use.
   Retained leases deduplicate only the same physical immutable bytes object,
   not merely equal hashes/content. Original/ICC bytes therefore need not be
   charged twice when source and candidate actually share that object.

## What this does and does not establish

This removes the previous mandatory96N import and128N staging paths for the
explicit supported neutral JPEG/PNG/current-canonical route. It supplies a real
asymptotically different aperture renderer, not a raised cap, Gaussian alias,
quantized radius, thinned brush or downsampled final image. Ordinary24MP source
planning is now arithmetically possible for supported content and sufficient
available memory, but is NOT executed24MP performance/quality acceptance.

Working memory stays capped at2GB and session retention at1GB; actual available
memory can lower admission. Encoded source size, ICC, display/receipt leases,
FFT work, sparse residuals, direct numerical repair, stroke scans and deadline
remain independent bounds. Named native codec/ICC reserves are conservative
application planning, not an enforceable process-RSS limit. Cancellation remains
cooperative; bulk decoder/ICC work has no immediate-stop promise.

Dense feather residuals may still be refused, especially at large apertures.
For radius128 the250M direct-pair ceiling is restrictive; no residual pixels are
omitted to obtain success. Numerical roundoff policy is separately versioned,
not a certified error bound. Full protection and neutral paths retain explicit
byte-preservation checks; real tests remain authored UNRUN.

Still incomplete: arbitrary mixed-edit24MP capture, RAW/TIFF optimized import,
variable/AI depth and automatic subject focus, transparent/HDR v2 return,
end-to-end runtime/numerical/RSS/quality/export/reopen acceptance, batch/presets,
and reopened editable lens recipes. Existing conservative autosave taint after
unknown-write reconciliation is not reset by this slice.

Small-source compatibility is retained: source acquisition admits when at least
one actually advertised renderer fits. A v2 reservation does not disable a
feasible direct-v1 path. The new importer may use the original full importer
only after a typed final-plan budget refusal following valid metadata, only
when direct-v1 is advertised, and after releasing the refused snapshot's
exception frames. Invalid metadata/ICC/precision never triggers this retry.
Selected renderers remain checked at native preview admission; no renderer
fallback occurs. Whole-session Cancel now uses the exact session/owner and a
null optional candidate token, so an expired image lease cannot block cancelling
the still-live session. Uncertain Apply remains query-only, never cancellable.
