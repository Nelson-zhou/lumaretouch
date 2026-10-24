# Corrected bilateral slim face, source-only / UNRUN

## Requirement and evidence

Exact frozen requirement **LNX-REF-PC-32466-C-da1d54e292** is
`PC-32466 / 脸型/瘦脸`; the frozen AI mapping and `ui/src/spec/refine.json`
require left/right unlock, but do not prescribe a numeric range. Related
PORTRAIT-007 requires side-face, occlusion, neighboring-face and straight-background
regression; it is not proof that those cases pass.

Primary official desktop semantics were read on 2026-10-24:
<https://wiki.pixcakeai.com/guide/9405.html>, section 瘦脸: inward narrowing below
the temples and independently adjustable sides. The original frozen guide
address is retained in the baseline mapping, not replaced by a claim of identical
commercial implementation. Negative expansion is an explicitly disclosed local
extension, not an official range assertion.

Verified factual oval and lip topology:
<https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py>.
Its Apache-2.0 file identifies 314/405 as lip points and 308 as an inner-lip endpoint,
not oval points. The old right chain also includes 399, which is not a face-oval
point. Point-number facts are used; no upstream implementation or weights copied.
The corrected chain comes from the existing `face_contour_geometry.CHAINS` and
`face_scope.FACE_OVAL`. New code is original GPL-3.0-or-later.

Existing original Rust contour controls and normalized TPS are reused, not a
second engine. Mature mathematical references remain
<https://user.engineering.uiowa.edu/~aip/papers/bookstein-89.pdf> and
<https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.RBFInterpolator.html>.
These substantiate TPS/affine-tail construction, not photographic quality or
commercial parity. No model download, native build or numerical execution occurred.

## Version and compatibility policy

New canonical operation **lnx.slim_face.v2** has recipe
`{version:2, linked:true, left:0, right:0}`. Values are finite signed [-1,1],
subject-relative, not viewer-relative. Relinking preserves unequal values; the
next linked adjustment explicitly writes both sides. Missing new intent resolves
to neutral, so opening an old document does not convert its appearance.

**lnx.deform.v1 is intentionally unchanged.** Its original point lists, numerical
strength, pixel convention, TPS, serialized `/slim_face`, exports and migration
archives remain the compatibility renderer. The known wrong topology is not
silently fixed inside that saved operation. Existing negative historic amounts
remain valid. Its source-file SHA-256 at the baseline is
`5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd`.
This is source preservation, not a claim that unrun renders are byte-identical.

The new profile is explicitly a compound of the verified contour regions:
for each side, temple = -amount, cheekbone = amount, jaw = -amount.
All three narrow for positive intent. The regional peaks are 0.035 measured
face width rather than the historical 0.11 sinusoidal profile. These numbers
are **not** appearance-equivalent or automatic migration coefficients.

The UI defaults new edits to v2, labels the legacy control and three old built-in
shape presets as historical behavior, and keeps those saved numerical definitions.
Unmanaged legacy documents retain their existing historical edit command instead
of pretending that the new source-owned operation is available without a people owner.
Replacement requires explicit user-chosen new values and one canonical patch
transaction that writes a legacy zero override plus the new values. It does not
unset inherited old values, copy an old strength, or mutate on entry. Undo belongs
to the existing people owner. Higher-priority conflicting scopes can still refuse;
the UI must not claim that a selected face's value represents all targeted people.
All seven official shape presets, their strength controls and proprietary preset
appearance remain outside this bug-fix scope.

## Geometry and source ownership

The operation is a new versioned user intent, not a changed legacy map. It reuses
the admitted contour field itself rather than sampling RGB twice. Active v2
refuses active legacy slim or any active standalone contour recipe. This bounded
coexistence rule avoids silently double-applying the same regions. Neutral v2
does not acquire analysis or a native core and does not change old contour behavior.
The plan ignores only the valid boolean v2 `/linked` leaf for anatomy demand,
so an unlinked zero-strength recipe remains visually neutral. Unknown or malformed
leaves, nonzero amounts, conflicting inheritance, other effects and retained local
assets keep their existing evidence requirements. No old-family link semantics change.

Canonical runtime validates coexistence before legacy geometry construction,
appends one source-owned corrected field to the unchanged four geometry slots,
and leaves mouth protection at slot 3. The ordinary contour append is neutral
when corrected slim is active. Existing combined geometry owns the only final
RGB/mask/recovery sampler. Source, FaceRef, landmark digest, actual face-skin
observation and known-occluder exclusion must match the immutable effective image.
All retained same-source neighboring face boxes remain protected, including
disabled/manual/unresolved faces. Complete source influence windows and actual
composed output/prior/final sample footprints use existing refusal checks.

The Rust kernel, ABI and packaging are unchanged. Native readiness is the existing
`face_contour_available` capability, not a new claimed model. Source checks remain
frontal/mild-yaw, sufficient measured resolution, nondegenerate oval and identity
features, actual interior skin/RGB evidence, complete image support and foreign-face
separation. The inverse field uses destination controls and source pullbacks,
protected identity features, exact control admission and sampled fold checks.

## Persistence, source return and target transfer

The canonical people graph stores only link/amount leaves. Project save, dormant
documents, virtual copies, immutable derived-source binding, undo/redo, frozen
receipts and export snapshots retain their existing owners. No new bitmap cache,
geometry asset, mask copy, source replacement or repair history is introduced.
Actual original RGB16 and compatible opaque bounded derived float sources pass
through the existing shared source and export contracts. A nonneutral v2 blocks
the original-image passthrough path. Legacy source archives are not rewritten.
Full-source export reconstructs pixel geometry at the actual source extent;
retained semantic observations may be resampled with their producer metadata.
That is not fresh full-resolution semantic inference or extra boundary precision.

Dedicated preset capture/replay stores only the v2 recipe, with ephemeral exact
owner/source/FaceRef evidence and target-local admission. Confirmed person mapping
recalculates every target's field using its own analysis. It never transfers
landmarks, masks or geometry. The generic derived preset route remains fenced;
explicit confirmed mapping is the supported path. Applying a preset never clears
conflicting historical intent implicitly. Neutral reset still needs the correct
owner but not working anatomy/native readiness.

## Remaining limits and acceptance

This repairs new-operation topology and keeps historical semantics explicit; it
does not make the old topology correct. No photo, runtime, native numerical,
preview/export, UI, history, batch or performance acceptance was executed.
Fixtures are authored **UNRUN**, including synthetic doubles, not photo evidence.
The whole requirement remains pending independent verification.

Interior skin heuristics cannot establish perfect silhouette or occlusion
segmentation. Smooth skin can be conservatively refused; hidden contours are not
invented. Moving a visible boundary also transports a bounded adjacent-background
halo. Numerical fold probes do not prove injectivity between samples. Other
legacy prefix fields retain their pre-existing limitations. Full HDR/alpha,
strong yaw, 3D/AI reconstruction, complete face reshaping and official preset
parity remain unsupported or incomplete; nothing clips or fabricates them here.

## Integration map

- `slim_face_state.py`: strict portable v2, side/link handling, explicit coexistence.
- `slim_face_people.py`: compound intent delegates to the existing guarded contour field.
- `people_algorithms.py` / `people_render_runtime.py`: canonical defaults, actual
  source preparation, separate facts, common preview/export geometry; old slots retained.
- `people_render_plan.py`: narrow nonvisual-v2-link handling, without bypassing
  validation or other effect/asset evidence requirements.
- `creative_derived_effects.py`: exact operation admission only; no broader source guard removal.
- `slim_face_scope.py` / `people_scope.py` / `scope.py` / `workflow_ports.py`:
  target-owned preset capture, complete-candidate conflict checks and existing replay owner.
- `ui/src/slimFace/` / `components/RetouchPanel.tsx`: authoritative bilateral
  readback, explicit replacement, historical control and preset labels; no new edit owner.
- `ui/src/people/model.ts` / `ui/src/presets/presetModel.ts`: operation naming.
- Registry extension and route inventory describe wiring, not completed acceptance.
- `core/face_contour/tests.rs` adds two UNRUN compound-policy fixtures without
  changing the kernel/ABI. New Python/UI fixtures include source-preservation and
  synthetic routing assertions, never model or photographic evidence.
