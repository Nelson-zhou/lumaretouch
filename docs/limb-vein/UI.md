> Integration update: current-photo shared source wiring is now authored; see INTEGRATION.md. The isolated-slice description below records the component contract. All execution and acceptance remain UNRUN.

# Reference-assisted hand, forearm and foot vein softening UI

Status: **AUTHORED / UNRUN**. No build, type check, test, product execution or photo acceptance was run. Shared integration is not included in this isolated UI slice.

## Requirement and honest scope

The retained original `ui/src/spec/refine.json` identifies `control:PC-46608:2` for hand/arm veins and `control:PC-9XYcMCvHXW:1`, `:2` for foot vein correction/manual painting. The UI provides one explicitly selected visible hand, forearm or foot per current-photo recipe. It does not identify anatomy, diagnose vessels, reshape limbs, reconstruct hidden skin, or implement cross-photo/batch behavior.

Amount 0–0.5 is presented as color easing; amount above 0.5 adds bounded lighting softening. These are the local kernel's staged semantics, not an official vendor parameter scale or a guarantee of texture preservation. Both color and lighting quality require photographic validation.

## Shared ownership and integration

`LimbVeinPanel` accepts `{port, disabled}`. The controlled port offers `reference`, `preview`, `confirm`, `clear` and a canonical snapshot. The implementation adapts the project's original GPL current-photo fabric UI, retaining existing request/receipt ownership principles; it creates no image or history bank.

`useLimbVeinPort(context, refresh, transport)` is exported. Mount it once at App lifetime, not inside the conditional panel. Context has `{bindingKey, documentId, revision, enabled, blocked}`. `bindingKey` includes document, epoch and source/revision identity. Revision is a safe nonnegative decimal string. Transport is injected as `{request(request): Promise<unknown>, status(requestId): Promise<unknown>}`; no nonexistent shared native import is assumed.

Native integration supplies a standard command with `cmd: "limb_vein"`, `protocol: 1`, exact request ID, document ID, revision and short action `reference | preview | confirm | clear`. Results use `event: "limb_vein_result"` and exact `limb_vein_request` echo. A successful write requires canonical `doc_state.document_id` and `doc_state.limb_vein` containing protocol, safe revision, amount and recipe digest matching the reviewed candidate. Persisted state remains the existing document owner's `_limb_vein`, not this hook.

The hook sets pending before dispatch, sends once and queries only the original request ID after ambiguity. It validates outer binding and PNG byte identity before exposing read responses. Refresh never proves an unknown mutation succeeded. Retain global conflicting-edit/export guards while pending, uncertain or waiting for a confirmed state refresh. Missing native capability blocks nonzero preview; clear may remain available for an existing effect.

## Payload contract

- `reference {}` returns family `limb_vein`, opaque reference ID, source fence, full source metadata/image, current amount and capability.
- `preview {reference_id, amount, radius_px, review}`. `review` is exactly the four existing source-normalized local-mask brush stacks `limb`, `target`, `reference`, `protect`, plus `version: 1`, `domain: "source-normalized"`, `limb_kind: "hand" | "forearm" | "foot"`, `same_limb_confirmed: true`, `clean_reference_confirmed: true`.
- Preview returns full-composite `before`, `after`, source-domain `mask`, preview ID, source fence, facts and candidate digest.
- `confirm` binds that exact preview ID and all three image hashes plus candidate hash with `reviewed: true`.
- `clear {}` removes this current-photo effect through the canonical transaction owner.

Changing the selected limb kind revokes both reference-condition confirmations and invalidates prior preview acceptance. Any mask, amount or radius change invalidates confirmation. Automatic source recognition is not inferred from the user's checkboxes.

## Painting and review

Four independently composited roles cover visible same-limb skin, vein target, clean comparable skin, and hard protection. Add/subtract affects only its role; protection is hard add-only with undo/clear for correction. Protect nails, jewelry, tattoos, skin boundaries and non-target anatomy. Do not mix persons, separate limbs or incomparable lighting in the clean reference.

Brush vectors remain on the full unrotated source grid. The display canvas is not a numerical measurement source. The host rasterizes authoritative vectors, verifies same-source input, target/reference disjointness and available support. Subtract can restore painted target portions; an accepted prior recipe is not editable by the panel without a new source review. A whole-effect clear is provided.

The explicit update action produces complete-pipeline before/after images, not isolated numerical mockups. Before/after dimensions match each other; the mask retains full source aspect and is labelled unrotated/uncropped. Confirm requires all three images to load and an explicit user review assertion. Loaded images alone are not human inspection evidence.

Drafts are bounded to 64 strokes per role, 1024 points per stroke and 4096 aggregate points. Radius 2–128 canonical pixels is a local algorithm control, separate from brush size. No image upload, model download, install or runtime fallback is performed.

## Remaining validation

Type/build verification, stale and malformed receipts, navigation/pointer cancellation, original-request recovery, source-aspect mapping, clear with missing runtime, and actual color/detail/lighting quality and performance remain UNRUN. Shared router/render/history/export wiring is separately required before claiming this is a reachable feature.
