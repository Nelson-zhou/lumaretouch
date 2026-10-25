# Reviewed workflow preset handoff

Baseline: c04fa7c028f9d3325ed72d8796e4ff384d5cc432.
Requirement: workflow:8YEKwsjJg7, extending the existing local directory workflow.
Status: partial source-connected; runtime, filesystem crash, UI and device
acceptance remain UNRUN. This is not a second new workflow algorithm.

The actual stored preset catalogue supplies names, IDs and exact content hashes.
Only complete exposure/white-balance recipes enter this first connected route.
Any other selected module, XMP-specific review or unsupported retained portrait
review rejects the entire preset, never silently dropping those effects.

The original ingestion lease stays owned while discovery pauses. Each imported
photo is explicitly opened, fully rendered before/after, paged with immutable
image hashes, actually displayed and separately approved. The native workflow
core journals ApplyPreset before the ordinary preset dispatcher mutates state;
normal history capture/record/finish stays authoritative. Approval alone is not
an apply receipt. User save and verified return to the prior editor document are
separate actions before PresetApplied can permit the export phases to continue.

Stable document IDs and transient load IDs remain distinct. Actual managed-file
SHA/size/stat must match the durable import receipt. Source, complete candidate,
people and repair proofs are checked again through apply and explicit save.
The scoped save preserves other documents, inactive versions, source registrations
and unrelated project fields, then uses the existing codec and pinned-directory
content CAS. Hydrated live state comes from the exact stamped saved body.
See PRESET-SAVE.md for cooperative-lock/path-based immutable-sidecar assumptions;
this is not a hostile-writer transaction proof.

Per-operation handoff snapshots and retained original-step receipts remain
queryable without rerunning writes. Possible save/apply outcomes stay unknown;
engine replacement does not fabricate restored approval or automatically replay
work. No original project overwrite rollback is attempted. Restart reconciliation,
broader mixed portrait preset owners, initially empty editor selection and
unattended auto-approval are not implemented by this slice. Tether hardware remains
unverified and unchanged. No tests, builds, typechecks, product imports, hardware
interaction, inference, installation or downloads were performed.
