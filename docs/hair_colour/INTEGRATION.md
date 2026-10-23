# Shared integration: source wired, runtime unrun

The hooks below are now present on the authorized shared turn after shoulder
base `c56f78a78485487385d0ac0dfba5041b9879c7c8`. They describe source contracts,
not executed acceptance. No product import, test, build, compiler/typecheck,
inference, installation or download was performed. The root owns commit/push.
Project v14 retains all v1–v13 migration boundaries, including the independent
v13 body bank. It rejects hair data disguised under older schema versions.

## Canonical people registration and render

1. `people_algorithms.specifications()`: add
   `hair_colour_state.OPERATION: (neutral(), check)`; no legacy global recipe.
   The existing defaults/leaves/resolver, scopes and confirmed transfer use it.
2. `people_effects.STAGES`: add `hair_colour`; do not call hair preparation from
   the per-face facial ROI/landmark routines. Hair can extend far beyond faces.
3. `people_render_runtime.prepare(...)`: accept optional `hair_assets`,
   `hair_evidence`, `hair_source_path`, `force_hair_prompted=False`.
   Skip `local_assets['hair_colour']` in the legacy FACE recovery asset loop;
   it is explicitly consumed by the hair bank, NOT silently ignored.
   After all ordinary face preparation succeeds, call
   `hair_colour_runtime.prepare_bank(state, asset_sha256, effect_source, plan,
    evidence=hair_evidence, assets=hair_assets, byte_budget=byte_budget,
    source_path=hair_source_path, force_prompted=force_hair_prompted)`.
   Extend effects, merge each fact under `facts[face_id]['hair_colour']`.
   Do not publish a partial result on any hair refusal. Include resident bytes. Supply only the remaining memory budget after other prepared effects/maps; hair admission must not independently spend the whole engine budget twice.
4. `people_support_assets.raster`: iterate only supported facial recovery kinds,
   explicitly leave `hair_colour` to its own checked consumer. Reject other
   unknown kinds. Do not pass hair assets through facial wrinkle recovery schema.
5. `people_engine_runtime.prepare_preview/synchronize`: pass hair kwargs.
   Every host caller (sync, candidate preparation, body edit, recovery re-render)
   supplies `people_owned_inputs.preview(engine, candidate, ...)`, which forwards
   hair evidence/assets plus independently retained body inputs together.
6. Existing RGB pipeline: before the ONE people warp, add
   `people_pipeline.source_effect(pipe,pixels,'hair_colour')` alongside facial/lip source
   stages. Preview, full float export and RGB8/16 tile paths must share it.
   Do NOT put it after the rendered-canvas semantic-colour stage.
   `aligned_fields` uses the same people map for any diagnostic mask view.

## Snapshot / project / history

7. `PeopleHostMixin._people_save`: `hair_colour_project.save(self,project)`.
   Project admission must run `hair_colour_project.validate(project)` before
   mutation; `_people_load` calls `hair_colour_project.load`. Existing graph
   history already saves the face's local asset reference; append-only store
   must remain at project/session level and not be overwritten by photo switching.
8. `_people_export_snapshot`: after `people_snapshot.capture` append with
   `hair_colour_project.capture(self,snapshot,pc,binding,source_path=source_path)`.
   Obtain exact original source binding from the retained graph evidence, not
   the currently open photo when exporting a parked target.
   Own helper `kwargs(snapshot)` supplies hair assets/evidence/path downstream.
9. `people_engine_runtime.prepare_export`: call same prepare with those kwargs
   and `force_hair_prompted=True`. Re-raster vectors at full source dimensions.
   `people_snapshot` should freeze/retain extra hair fields, not reinterpret them
   as face_skin or a late rendered-canvas class. ExportSpec already carries
   people snapshot; do not add a second hair export engine.
10. Ordinary commands record `hair_colour` only for action in MUTATIONS;
    context/preview must not create history entries, dirty documents or advance
    versions. Gesture group includes target face and request ID so two reviewed
    strokes do not coalesce accidentally. Retained append-only vectors permit
    source-specific undo and redo without copying assets between photographs.
11. Validate `hair_colour_assets` alongside people graph on project load and any
    newly admitted project sidecars. Never clear the append-only store on neutral
    defaults, face selection, another document or a failed preview.

## Host / Tauri / UI

12. Add `HairColourHostMixin` or forwarding methods to the Engine; capabilities
    `hair_colour_protocol:1`; dispatch completion calls `finish_hair_colour`.
    Do not catch refusal and convert to success. Exact context includes canonical
    document/epoch/revision, graph/association fences and selected face.
13. Register `hair_colour_api` new Rust module and Tauri command. engine event
    receiver routes `hair_colour_result` to receive; lifecycle invokes ended;
    send_to_engine routes `hair_colour` through its epoch checked enqueue.
    Reuse existing ReceiptHost; no duplicate acknowledgment or resend.
14. App creates one long-lived `useHairColourPort` / `createHairColourPort` owner.
    RetouchPanel mounts `HairColourPanel` with people view, existing people
    workflow patch callback, busy state and refresh. Do not remount the port on
    panel closure: an unknown write must remain locked until its original receipt.
    Add own tool navigation entry, explicit control IDs and UI type/capability.
    Scalar patch fields belong to people scope; asset review requires exact-face
    scope. Existing panel supplies concrete source brush and checked commit flow.
15. Package `packaging/build-hair-colour.sh` into stage-engine, producing
    `engine/src/lumaretouch_engine/bin/liblrt_hair_colour.so`. No runtime build.

## Receipts / provenance / edge cases

- An accepted native enqueue is not result completion. Original request status
  is queried; unknown outcomes stay locked and are never auto-retried.
- A current receipt refresh failure does not resend a committed edit.
- Source/face/version change invalidates UI and backend review; closing preview
  cancels only its unsubmitted draft, never claims a dispatched commit rolled back.
- `clear_support` while colour/gloss active must be refused or preceded by an
  explicit recipe reset; the UI requires the latter. Clearing recovery retains
  support. Neither clears unrelated people overrides or other operator history.
- All enabled retained supports participate in overlap refusal, even if one
  person's recipe is neutral; face detection count is never a support shortcut.
- RGB gamut clamping after additive stage composition may alter strict native
  luminance properties when other operators already changed the same pixel.
  Shared-stage photographic validation is still necessary; no pixel-perfect claim.

Amended replay requirement: project.save/load/validate must include both
`hair_colour_assets` and `hair_colour_evidence`. The latter is already bounded
JSON-safe lossless encoding; do not send it through a lossy/unknown-array-drop
path. `hair_colour_project` hooks own this codec. Every asset pins its evidence
ID. Preview/export first use the retained field; no fresh model availability is
needed merely to replay it. Project v14 and explicit old-schema rejection prevent old readers from silently
ignoring new active data.
Preserve earlier schema versions and all existing sky/semantic migrations.

Strict hair-only no-model replay hook: `hair_colour_replay.restore_open(engine,
decoded)` must be checked in `people_open.prepare` before it constructs a new
producer. This returns true only when all requested non-hair FACE ops are neutral,
no other local asset family needs missing semantics, real measured landmarks
and hair evidence are retained with exact hashes/source. It never invents skin,
exclusion, landmarks, faces, or a precompute producer receipt. For a parked export
whose PC is None, call `hair_colour_replay.analyses(engine,state,binding)` before
requiring a new producer; use the returned actual rows in the ordinary snapshot.
Keep the old explicit failure path if it returns None. Other nonneutral effects
still require their own missing actual inputs. Prompted-mask recipes separately
require their actual prompted producer inputs; manual brush/radial support is
weight-independent on replay.


## Bounded static call-site scan, 2026-10-23

- `people_host._people_sync` -> `synchronize` and `_people_prepare_graph` ->
  `prepare_preview`: shared owned-input helper includes exact current source,
  candidate graph, reviewed hair vectors, retained hair field and body bank.
- `body_pose_host._body_prepare` forwards the CANDIDATE body bank plus unchanged
  hair inputs; `people_recovery.prepare` forwards the candidate face graph with
  both independent inputs. The previous optional-kwargs omission cannot silently
  remove a body map. Hair graph assets are validated even on neutral preparation.
- `people_engine_runtime.prepare_preview/prepare_export`: face/hair preparation
  first, then body composition preserves `face_fields`, `body_fields`, and
  `body_operation_order`. Body budget reserves retained colour/recovery buffers;
  hair budget reserves prior fields/maps/source buffers. No second deformation.
- `people_host._people_export_snapshot` captures exact target source path and
  retained fields, not live-photo fallbacks. `people_export.prepare` reaches the
  same full-resolution bank through `prepare_export`. `hair_colour_project`
  stamps/hash-checks the source at capture; full export verifies the stamp before
  preparation and after late colour, rejecting changed files.
- `reference_color_engine.render` already captures the exact source snapshot,
  verifies decode/stamps and calls common `export_float`; it therefore retains
  body/hair preparation and its own reference/late semantic stages. No separate
  rendered-canvas hair-mask conversion was introduced.
- `master16_policy._master16_snapshot_blockers` now consults
  `people_export.fastpath_blocker`: nonneutral per-face/inherited intent, local
  assets, conflicts/unknown operations and unresolved legacy intent cannot be
  lost after `isolated_snapshot` neutralizes legacy mirrors. Neutral detections
  alone remain eligible for passthrough.
- `hair_colour_replay` restricts only unsupported face consumers. Independently
  retained body geometry and late reference/semantic-colour effects remain in
  their own checked paths; no fake precompute, skin/exclusion, pose or census.
- Root's generic people post-publication uncertainty fix remains unchanged.
  Hair's own receipt retains before-fence and mutation state across result
  publication; later emit/report/history failure is unknown, not false refusal.

Static parsing/hashes are recorded in `manifest.json`. Runtime behaviour,
photographic quality, mixed-effect replay, memory peaks and full8/16 exports
remain AUTHORED_UNRUN Qoder cases, not inferred passes.
