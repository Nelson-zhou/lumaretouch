# Creative selection editor: source implementation, acceptance UNRUN

## Exact scope and evidence

This isolated editor implements the retained interaction requirements `ui:18` (规则选区) and `ui:19` (自由选区), linked to `workflow:127932` for the existing creative document and unified history. The preserved references are [selection and interface guide](https://www.pixcakeai.com/guide/158252) and [creative workflow](https://www.pixcakeai.com/guide/127932). Their identifiers and original requirement text are not renamed or marked accepted by this module.

This is original manual geometric selection code, not imported-mask UI relabeled as selection, not AI segmentation, and not a proprietary algorithm compatibility claim. It creates a real source-local numeric layer mask only through the host's immutable-asset publication path. It does not replace or approximate the existing numeric creative compositor.

The bounded target is the current source's explicitly selected, unlocked image leaf. Groups, inherited locks, stale source/revision/transform/mask proofs and unsupported host capabilities must be refused by the host. UI availability also follows the current authoritative binding; no synthetic layer or placeholder mask is manufactured.

## Replaceable modules and integration

- `model.ts`: versioned vector, proof, review and transport contracts; runtime validation. The protocol marker is `lnx.creative-selection.v1`.
- `geometry.ts`: pure client-to-canvas edge mapping and free/fixed-ratio/fixed-size shape geometry.
- `imagery.ts`: canonical Base64, bounded nonanimated PNG structure/chunk CRC and SHA-256 verification of actual encoded bytes.
- `controller.ts`: App-lifetime owner of local drafts, read/preview/apply/cancel request identity and review gating. It never owns canonical pixel assets or a second document history stack.
- `useCreativeSelection.ts`: stable owner and query-only observation across transient panel unmounts.
- `CreativeSelectionEditor.tsx` / `creativeSelection.css`: scoped interactions and actual image presentation.
- `nativePort.ts`: parent-owned built-in adapter, not owned by the isolated editor implementation. An alternative implementation can replace the same explicit port contract; missing methods remain unavailable.

Mount `useCreativeSelection(context, stablePort, onApplied)` once above the conditional creative view. Pass the resulting controller to `CreativeSelectionEditor`. Do not instantiate the port each render. Do not include the selection owner's own `busy` flag in its input `context.busy`; that input is only the external owner fence. The parent retains the shared `App`, creative workspace and native registry integration.

The context consists of:

1. `scope`: genuine engine key + source load epoch; not a filename.
2. `binding`: exact `document_id`, `source_uid`, `ownership_token`, `expected_revision`, `layer_id` from the current creative authority, or null when no eligible image leaf is selected.
3. Current `active`, `available` and external `busy` state.

Acquisition is explicit. Opening the panel does not silently freeze a new source or start a render. The parent `onApplied` callback must genuinely read/publish the host's resulting creative state and refresh the main workspace. Refresh failure retains a confirmed applied outcome and exposes only a refresh retry, never a duplicate apply.

## Vector recipe and units

The exact recipe is:

```
{
  version: 1,
  coordinate_space: "canvas-pixel-edge-v1",
  canvas: { width, height },
  feather_radius: integer 0..256,
  operations: [...]
}
```

All geometry uses full frozen creative-canvas pixel edges, x right and y down. Pointer coordinates are measured against the actual displayed stage DOM bounding rectangle, then mapped to the authoritative canvas dimensions. Display PNG dimensions and device pixel ratio are not written into the recipe. The source image layer's own dimensions remain separately bound by the proof for host projection.

- Rectangle / ellipse: `{kind, combine, x0, y0, x1, y1}` with positive ordered bounds. Reverse drags normalize the bounds.
- Lasso: `{kind:'lasso', combine, points:[[x,y],...]}`. At least three sampled locations, closed implicitly from last to first only after pointerup. The original raster core uses even-odd fill, including self-crossing paths.
- Brush: `{kind:'brush', combine:'add'|'subtract', points, diameter, hardness, opacity}`. A single-location dab is valid. Diameter is full canvas pixels; hardness and opacity are [0,1].
- Invert: exactly `{kind:'invert'}`.
- Deselect: empties the local operation list, undoable locally. The UI and host do not preview/apply this empty draft as an accidental all-transparent replacement mask.

`new` replaces draft coverage, `add` is max(A,B), `subtract` is max(A-B,0), and `intersect` is min(A,B). Invert is 1-A. Feather applies after the ordered combination, not independently to each outline. These are original explicitly declared semantics, not a claim that a commercial editor uses the same numerical implementation.

Fixed-ratio shapes preserve the ratio at canvas boundaries. Fixed-size shapes preserve the requested canvas-pixel width and height and translate the whole shape back inside the canvas at an edge; oversized shapes are refused, never silently reduced. UI text calls out that these source-canvas units are not display pixels. Native projection of the resulting coverage into a transformed image leaf is a separate host operation.

The interactive limits are 256 operations, 4,096 points per gesture, 32,768 total points, a 2 MiB vector request, and 64 local undo snapshots. The host/native may additionally refuse work by resource cost; UI limits do not imply performance acceptance. A refused gesture is not silently truncated or downsampled into a different path.

## Gestures and accessibility

Pointer capture is scoped to the displayed stage. The in-progress gesture remains only in a ref/temporary outline; canonical vector history changes exactly once on valid pointerup. Pointercancel, lost pointer capture, source/tool/recipe changes, stage position/size changes, leaving the canvas, window blur, document hiding or Escape abandon the entire unfinished gesture. A brush preview is explicitly a gesture guide, not claimed as final raster coverage.

M selects rectangle and L selects lasso only while focus is inside this editor. There is no global document keyboard listener. Input, textarea, select, button, editable descendants, textboxes, modifier shortcuts and IME composition are ignored. Controls have labels; the stage is keyboard-focusable, and status/error changes have live announcements.

Completed vector paths are dashed guides. Their union/difference and feathered coverage are not approximated by SVG. The real four-image review is required for the result.

## Proof, review and publication

`context` sends an original request ID plus the full current binding. The host returns `proof`, `canvas_image` and optional `existing_mask_image`. Proof additionally freezes source asset ID/SHA-256, canonical document SHA-256, transform SHA-256, existing mask ID/SHA-256, canvas dimensions and layer-source dimensions.

`preview` sends that exact proof, recipe and explicit mask policy. The returned review echoes proof and recipe, contains recipe/output-mask hashes and immutable output mask ID, and supplies all of:

1. `before_composite`: real full creative composite before the proposed layer mask.
2. `after_composite`: real full composite rendered with the proposed immutable numeric mask through the original compositor.
3. `before_mask`: actual source-grid mask coverage (white implicit coverage when no mask existed).
4. `after_mask`: actual proposed source-grid numeric mask coverage.

Each display descriptor is `{mime:'image/png',width,height,sha256,base64}`. SHA-256 binds the encoded bytes. The UI verifies all four, verifies whole-frame aspect/dimensions against proof, then checks the actual decoded image natural dimensions and nonzero visible DOM size. Source/preview display images may be sampled; they are honestly labeled, never promoted into source assets and never described as 100% full-resolution inspection. Hiding/unmounting/replacing images revokes presentation and user acknowledgment.

An existing mask has no default destructive policy. The user must explicitly select `replace`, `union` (max), `subtract` (max(old-new,0)) or `intersect` (min). With no mask, only `create` is admitted. This policy is separate from the ordered draft operations and changing it invalidates review.

Only after all images are verified and actually presented can the user tick the explicit review checkbox. `apply` then sends exact original proof, immutable preview token, opaque host-generated ACK and `reviewed:true`. It does not send a fabricated file or synthetic mask ID. The host recomputes/binds the ACK and publishes its real immutable mask through the existing creative controller/history owner. The UI checks the exact returned proof/token/mask ID/hash and a valid revision before calling `onApplied`.

## Races, cancellation and recovery

- A source/load/engine/selection/revision change invalidates old source imagery and review. A fresh acquisition starts with an empty draft; old geometry is never copied to the new source.
- Pending requests survive panel hiding. Unknown outcomes preserve their exact original request ID and cannot be automatically re-sent. Query-only receipt observation continues in the App owner.
- Cancellation has its own request ID and names `target_request_id`; it is not an undo operation. Pending cancellation remains pending until the host reports actual original-job unwind. An accepted/unknown apply is never called cancelled merely because the user closed a panel or clicked Cancel.
- Old held preview candidates are cancelled explicitly before a replacement preview/acquisition, retaining draft geometry during this cleanup. Native preview metadata stays retained until candidate cancellation or verified apply.
- Optional native `release(request)` only releases terminal metadata after the result is retained. Pending/unknown original writes are not released as if complete.
- An authoritative explicit project reopen may yield a matching native `workspace_reopened:true` / `status:'unknown'` marker. Only then is the explicit “已核对重开工程，关闭旧会话待核对状态” action enabled. It closes the old operation lock, retains the old request/UNKNOWN receipt in `retired_*`, requires a fresh context, and never labels the old outcome applied, rejected, cancelled or replayable.

## Verification status and required local acceptance

Everything in this editor slice is **AUTHORED / UNRUN**. Only source inspection and edits were performed. No product imports/execution, tests, TypeScript compiler/typecheck, UI build, native build, inference, package installation, download or Git write was performed for this slice. No fixture result is a pass claim.

Authored files `model.unrun.test.ts` and `controller.unrun.test.ts` cover coordinate mapping, shape constraints, version/parameter validation, vector undo separation, explicit existing-mask choice, real fixture-PNG review gates, exact request cancellation and an apply surviving source change. The synthetic fixture PNG generator runs only when a verifier deliberately executes those tests. The tests are not silently added to the existing aggregate package scripts.

Before acceptance, locally run the repository-supported Node strip-types tests for both authored files, then the actual TypeScript/build and integrated host/native checks. Required real UI checks include:

- Rectangle and ellipse in free, ratio and fixed-size modes, reverse drags, source boundaries, high DPI and non-square display scaling.
- New/add/subtract/intersect/invert/deselect; feather after combined paths; brush dabs and strokes with hardness/opacity extremes; lasso auto-close and self-crossings.
- Pointer cancellation, lost capture, pointerup outside, resize/scroll during drag, window blur, tab hiding, tool change and source switch produce no phantom stroke.
- M/L inside stage, input typing, buttons, contenteditable, IME and modified shortcuts; no interference elsewhere in the application.
- Real full composite before/after and source-mask before/after, bad PNG bytes/hash/CRC/dimensions, hidden/zero-size DOM, delayed loads, and revoked acknowledgment.
- Existing masks never replaced without explicit choice; create on masked targets refused; inherited locks and groups refused; transformed target projection verified numerically and visually.
- Duplicate apply, source/engine switch during read/preview/apply, cancel races, pending-cancel promotion, original receipt reconciliation, explicit project-reopen dismissal, failed refresh and late responses.
- Exactly one canonical history entry per actual mask publication; unified undo/redo restores old mask/source and immutable assets; draft undo does not call canonical undo.

Real application startup, screenshots, UI/host/native execution, numerical correctness, performance/memory and end-to-end acceptance remain unverified until those checks are executed in the authorized local environment.
