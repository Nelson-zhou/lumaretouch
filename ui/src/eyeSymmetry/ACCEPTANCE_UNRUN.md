# Eye symmetry UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. Source reading and source editing only. No project imports, execution, tests, builds, type checks, application runs, inference, downloads, Git writes or real-photo acceptance were performed. The fixtures are authored assertions, not evidence that an assertion passed.

## Exact identity and semantics

The source contract is PC-32470, https://www.pixcakeai.com/guide/32470. It specifies independent horizontal and size symmetry, with the larger eye as automatic size reference and a manual side choice. It does not calibrate this implementation's numeric range, measurement policy, displacement bounds, support, falloff or quality.

| Exact path | Control ID | Route |
| --- | --- | --- |
| 眼睛对称 | LNX-REF-PC-32470-C-2745ac86f5 | eye_symmetry.family |
| 眼睛对称/水平对称 | LNX-REF-PC-32470-C-a86e5c0175 | eye_symmetry.horizontal |
| 眼睛对称/大小对称 | LNX-REF-PC-32470-C-4601eb7797 | eye_symmetry.size |
| 眼睛对称/参考眼选择 | LNX-REF-PC-32470-C-118aa67e04 | eye_symmetry.reference |

The family renders one actual section with two scalar controls and a string reference-eye control. The child routes are covered inside that section, not duplicated as disconnected controls. Unmanaged documents explicitly report unavailable; there is no fallback to eye shape, eye-ball adjustments, legacy big-eye deformation or pixel mirroring.

Operation `lnx.eye_symmetry.v1` accepts precisely `{version: 1, horizontal, size, reference}`. Both strengths must be finite numbers in `[0,1]`; reference is the closed string union `auto | left | right`. Unknown whole-recipe keys, missing fields, booleans, numeric strings, nonfinite strengths and arbitrary reference values are rejected. Defaults are `0 / 0 / auto`. Both strengths being zero is a geometric identity even if the saved reference is left or right. UI 0–100 is a product-local strength scale, not an anatomical ratio or official calibration.

## Source-owned geometry and limitations

- Horizontal symmetry levels the two source eye centers toward their shared midpoint height in independently measured head coordinates. The reference selection does not fix one eye for this operation. The head axis must not be inferred from the eye-center line being leveled. Tilt can change screen-horizontal positions even when the adjustment is head-relative vertical motion.
- Size symmetry uses measured eye-aperture area and local isotropic scaling, not a width-only proxy. Auto chooses the larger-area eye independently for each target. Left and right mean the person's anatomical left and right, consistent with existing landmark ownership, not screen sides. Manual reference changes only size symmetry.
- The source is each target's current effective image, whether original or already returned composite. Geometry, eye visibility, support and combined-operation validity remain runtime-owned. The UI does not fabricate eye areas, source centers, head axes, acceptance ratios or preview outcome facts.
- Both eyes need real source evidence. Closed, occluded, clipped, excessively turned or tilted eyes and insufficient local support are conservatively refused rather than reconstructed. No eye pixels are copied or mirrored; no closed-eye-to-open-eye generation or missing anatomy synthesis is claimed.
- Genuine already-symmetric geometry may validly make no change even with nonzero requested strength. There is no artificial minimum displacement to make a slider appear effective.
- Local falloff may move adjacent eye-area pixels. Earlier geometry and source/composition compatibility are still checked by the engine. No general promise is made that every neighboring pixel remains fixed after composition, every frontal image is supported, or preview/export is already verified.

## Ownership and deliberate editing

`PeopleOwner.patch` is the only mutation path. The existing owner retains source binding, queue, request receipt, history, undo and replay for both original and derived images. No second people workflow, native command or UI-owned people graph is introduced.

For each scalar and reference leaf, selected-face effective value and provenance are shown separately from the editing target's explicit value. Face edits can start from the exact selected face's effective value when target and face reference match. All-people, group and person edits start from that target's own valid explicit value or a deliberately blank choice, never the selected face's inherited number or side. Missing and malformed readings stay unknown, not fabricated zero or auto. Reference drafts do not write on selection, mount or blur; the user applies the choice explicitly.

A deliberate new size/reference choice uses two patches in one owner transaction. Editing an already available scalar slider changes only that scalar and preserves each target's own reference. A standalone reference edit writes only the reference string and leaves horizontal strength untouched. It is a normal geometry-affecting edit, including changing to auto when size is nonzero, and therefore does not bypass capability or source gates.

Bindings include source/document/epoch/revisions, selected face and exact analysis revision, all current faces, target, groups/persons/links, resolved values/provenance/conflicts, explicit intent, refusals and patch/check owner identity. Changes remount drafts and stale captured callbacks refuse to dispatch. A submitted guard prevents repeated writes before a confirmed owner snapshot; an uncertain outcome offers original-receipt lookup rather than resend. A separate query guard prevents repeated concurrent receipt checks. Engine refusals are displayed without rewriting their reason.

## Neutral recovery

The complete reset sends exactly one atomic owner transaction with `/horizontal = 0`, `/size = 0`, `/reference = auto`. Individual scalar zero buttons affect only their own leaf. Reset writes an explicit neutral override, not inheritance removal. It does not clear other targets, groups or operations, migrate historical values or silently upgrade eye shape.

Reset does not require available native eye-symmetry code, valid effective readings, enabled face analysis or real eye evidence. It still requires the current document/source/target, enabled canonical owner, no pending or uncertain request, and no competing edit. Other surviving effects or target overrides may still be refused by the engine; the UI must never silently clear them to force a reset through.

## Authored fixtures, all UNRUN

`model.unrun.test.ts` specifies exact identifiers, recipe whole-key validation and bounds, string enum and anatomical labels, neutral strengths with manual references, per-leaf effective/provenance versus explicit target intent, shared blank scalar/reference choices, malformed/conflicted/missing authority, current original/derived bindings, target identity, dedicated capability, neutral recovery without anatomy or native code, atomic reset and size/reference patches, pending/uncertain/external-editor fences, source/membership/provenance/refusal draft invalidation, deliberate raw text and no neighboring-state mutation.

`wiring.unrun.test.ts` specifies the four exact routes and one real family section, scalar/reference widgets, preserved eye/portrait neighbors, unmanaged refusal without fallback, the strict native reference DTO and existing generic preset compatibility, canonical owner reuse, editor fencing, no borrowed or fabricated shared baseline, source/owner-keyed drafts and stale/repeated callback guards, original receipt lookup, unaltered refusal text, atomic neutral-only recovery and source/no-op/refusal disclosures.

Unverified: every fixture assertion, TypeScript compatibility, compilation, mounted React behavior, bridge capability delivery, reference select/apply and scalar interactions, rapid owner/face/source/scope changes, repeated clicks, batched pending-to-failure transitions, original receipt recovery, all-target atomicity, malformed-state recovery, actual eye-aperture area and independent head-axis evidence, anatomical side selection, no-op detection, closed/occluded/tilted/clipped-eye refusals, local support and falloff, original/returned-composite parity, full-resolution photographs, history/undo/redo/replay, preset/batch integration, preview/export parity, packaging, complete handbook and development-pack acceptance. The eye-enhancement feature family is not fully accepted by these authored files.
