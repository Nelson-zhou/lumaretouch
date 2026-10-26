# Native-size AI restoration product path — source authored, UNRUN

The explicit `upscale_restore` command uses the existing complete-current-edit
capture (version 3), immutable canonical asset/source proof, source revision,
people graph, ordered repair proof and original-file fence. No camera preview,
RGB8 proxy, original-path substitution or thumbnail enters model inference.
The fixed first model is `Swin2SR-classical-sr-x2-64`, classical SR, not blind
restoration or face reconstruction. The first profile is restricted to opaque SDR, native width and height each 16–1024 pixels and
at most 1,048,576 pixels. The full source runs as exactly one model tile; larger
photographs are explicitly unavailable, never proxy/downsample/tile substitutes.
Swin finite attention-mask cyclic edge dependence makes an interior halo
insufficient to promise full-frame boundary equivalence. Multi-tile research is
not exposed as a supported product profile. Source capture, result retention and isolated model computation
have separate fail-closed budgets; these are NOT measured peak RAM guarantees.

The model-specific stage calls `upscale_v2.adapter.restore_native_candidate`,
checks model/source/output identities and the full float result, then creates
before/after display records and an immutable review candidate. Display PNGs
never become output. The first model uses a 2× internal network and returns to
original dimensions; the feature is not a promise of 2× export dimensions.
Actual checkpoint/runtime eligibility is separately reported by adapter/setup.

`upscale_restore_host.Service` reuses the existing reviewed-copy transaction
implementation in `light_glow_host.Service` through static stage/job/command
parameters. Numerical glow behavior is not reused. The complete source capture
is the existing `light_glow_source` owner, itself built on canonical capture and
lens source fencing. No parallel mutable photo/history/export owner was added.
Only an exact before/after-reviewed new-image write may reach
`CreativeHost.commit_return`. Original photo, source path and history stay intact.
An entered but unconfirmed write locks mutation and is reconciled by its original
request identity; a timeout/cancel does not assert rollback or trigger resubmit.

The resulting canonical photo uses the existing editor/project/save/export path.
There is no automatic disk save, export, overwrite, or export-backend substitution.
The legacy export Real-ESRGAN backend remains independently unavailable.

## Acceptance still UNRUN
- Receipt identity/replay/cancel/unknown-state fixtures: authored, not executed.
- Shared glow lifecycle regression after static parameterization: not executed.
- Genuine original and derived source capture incl ICC/RAW/high bit depth/repair
  replay, HDR/transparent rejection, source changes and memory rejection: UNRUN.
- Native transport, capability matching, hide/reopen, presentation hashing,
  before/after acknowledgment, cancellation and race cases: UNRUN.
- Model setup, checkpoint load, actual inference, seams, detail hallucinations,
  real portraits/wedding photographs, full-frame inference and exact global boundary behavior: UNRUN.
- Project reopen/new-image persistence and export color/precision: UNRUN.
- Build/typecheck/tests, hardware/resource/performance acceptance: UNRUN.

Source/AST review is not evidence that a model is installed, accepted or usable.
