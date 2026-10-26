# Hand tone UI / protocol — AUTHORED, UNRUN

This is a source integration, not a successful build or real-photo acceptance.
PC-46608:1 is routed independently from vein correction and hand shaping.
The `reference` command captures the current photograph; it is **not** a donor
reference mask. The only mask roles are `limb`, `target`, `protect`, with
`limb_kind: 'hand'` and explicit same-visible-hand confirmation.

External acceptance still needed:
- Capture current source, paint hand/target/protect, preview, inspect before/after
  and source-grid eligibility mask, confirm, undo/redo, save/reopen and export.
- Nails/jewelry/edges remain protected. This requires manual marking, not detection.
- Change any stroke, strength, radius or source after preview: confirmation must
  become unavailable until a newly matching preview is fully loaded and reviewed.
- Mismatched PNG digest/dimensions or candidate/source/revision identities refuse.
- A timed-out publication queries the original request only; no duplicate write.
- Restarting the engine fences old receipts; unknown mutations keep recovery guard.
- Missing native capability disables positive preview, without substituted filter;
  clear remains an explicit canonical edit when an existing correction is present.
- Pending hand tone disables the sibling vein/fabric panels and global edit gate;
  pending siblings prevent hand tone submission.

Numerical quality, texture preservation and performance are not established by
these UI checks. Tauri fixtures in hand_tone_api.rs are also authored / UNRUN.

## Source-grid ROI admission (UNRUN)
- On ordinary unrepaired 24 MP source, bounded hand target plus full radius halo
  should be admitted when actual decode/mask/ROI memory budgets permit; not an
  established performance or supported-device claim.
- Compare full-context source and exact halo crop within numerical tolerance,
  then verify full-grid field scatter/export origins and protection neighbors.
- Original-image edges must remain rejected; never pad/reflection-fill a halo.
- Very large/disjoint targets must refuse on the real ROI reservation.
- Existing repair operations on 24 MP still exceed the canonical repair-capture
  budget; report this restriction, do not switch to a proxy or drop repairs.
