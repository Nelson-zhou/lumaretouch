# Native expression acceptance checklist

All rows are AUTHORED / UNRUN, not passed. Source-only work did not run cargo, rustc, npm, Python, inference, a product process or any image import.

## Authored contracts

- Exact-byte command SHA accepts whitespace/key spelling differences only when parsed content matches; a changed raw digest is refused.
- Duplicate root/nested keys, NaN/Infinity/overflow numbers and trailing JSON are refused.
- Current digest uses the explicit sorted string-only envelope.
- Measured 478-point face/protection/eligibility fields and bounds are mandatory; same-original donors, out-of-crop strokes, unsupported colour adjustment and invented confirmation fields are refused.
- Donor path cannot appear on preview/apply or use a relative path/URL.
- Each before/after/fusion PNG must match its bytes, native dimensions, complete-source mapping and bound source.
- Apply consumes the exact retained preview proof; changed preview image hashes, original-document overwrite, wrong parent and wrong result source are refused.
- Apply cancellation is invalid.
- First terminal remains immutable across late receipt/EOF; malformed original can be resolved only by later valid original terminal; eviction preserves request identity and prevents replay.

## Integration and runtime work still required

1. Review main registration, actual capability advertisement, read-only routing, shared native enqueue, both mutation ingress fences, raw stdout observer placement, normalized recovery settlement and all engine lifecycle hooks.
2. Confirm the server strips only `_host_request_id`, measures actual images and emits the exact envelope shapes. Check current and preview-before byte identity.
3. Exercise OS dialog dismissal, cancellation while queued and while rendering/analysis, late selected paths, source navigation, out-of-order read results and engine replacement.
4. Exercise bounded storage, non-evictable unknown apply, explicit preview release and full process tombstone budget.
5. Inject duplicate-key/malformed/wrong-event/mismatched-binding receipts, a dropped acknowledgement, EOF followed by buffered original terminal, replayed IDs and late contradictory commit/reject results.
6. Demonstrate one actual new image, no original pixel overwrite, canonical shared history and no second undo owner. Verify save/export/undo cannot cross an unresolved apply.
7. Compile, run focused and aggregate tests, typecheck the real adapter, and execute controlled end-to-end UI/host proof only in a separately authorized runtime window.

Static source checks and authored fixtures cannot establish rendering quality, real cancellation timing, durable publication, runtime memory usage, successful compilation, or feature acceptance.
