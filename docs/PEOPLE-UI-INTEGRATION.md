# People editor host integration (source implementation, runtime not accepted)

This change connects the existing people data contract to the retouch workspace.
It is not a claim that photographic quality, runtime editing, save/reopen, undo,
export or cross-photo transfer has passed acceptance. Qoder owns local runtime
verification. No application imports, tests, builds, typecheck, compiler, model
installation or model execution were run during this source-only implementation.

## Authoritative boundary

- `doc_state.people` supplies the project graph view, selected cursor, editing
  target, exact binding, selected-face effective values and target-only overrides.
  React keeps only input drafts and a pending receipt, never another people graph.
- Every people command carries document ID/epoch/revision, graph/association
  revision and an explicit target. A face target includes its asset digest,
  stable instance ID and analysis revision. All-people names the current asset.
- The Rust boundary keeps a bounded receipt mailbox. It never treats enqueue
  acceptance as completion. Status queries do not invalidate captures. Unknown
  results retain the original request and offer read-only reconciliation, not replay.
- Product deform/enhancement/wrinkle/lip sliders submit sparse numeric leaves
  through one in-flight people receipt, retaining only the latest unsent value per
  leaf. A fresh authoritative revision is required before sending the next intent.
- Legacy brow/nose/eye/mouth, lip, deform and enhancement transports carry the
  captured `people_context` when available. Geometry latest-intent ownership also
  includes the editing target and document epoch; an intent cannot follow a newly
  selected scope. Its next send waits for a newer authoritative graph revision.
- `deform` and `enhance` native wrappers are extracted to `portrait_api.rs` rather
  than compressing main.rs. Existing portrait controls and thumbnail avatars remain.

## Visible behavior

The former local all/single-person lock is replaced by engine-confirmed scopes.
Selected-face chips remain selectable when analysis is unresolved or the face is
disabled, so users can correct a refusal. A chip selects the cursor and face target
atomically, not via two stale-revision commands. The engine, not selection, owns
the set of enabled faces rendered.

The panel supports current-photo defaults, explicit groups/priority/membership,
anonymous confirmed links, user labels, recoverable disabling, manual regions,
analysis requests, exact per-key inheritance removal and source/conflict display.
Ambiguous legacy records have explicit apply-to-selected-face/current-photo or
retain-inactive choices; retained archives and history are not deleted. Viewport
manual addition captures current-asset fences when armed and still uses real
region analysis, with an unconfirmed message on timeout rather than false success.
Other-photo group members are preserved using the current authoritative group,
not a stale copy hidden in the form. Candidates never claim confirmed identity.

When editing a broader scope, existing sliders are explicitly labeled as the
selected face's effective preview values, not the shared default values. Exact
current-scope overrides appear separately. Skin smoothing is truthfully described
as the photo's skin-mask operation, not per-person or group scope.

## Primary practice and licensing reviewed

- React's official [state guidance](https://react.dev/learn/managing-state) and
  [effect guidance](https://react.dev/learn/you-might-not-need-an-effect) support
  deriving displayed facts from one authoritative state rather than synchronizing
  a duplicate graph. This implementation uses those architectural principles;
  no upstream example code was copied.
- Tauri's official [invoke API](https://v2.tauri.app/reference/javascript/api/namespacecore/)
  and [Rust command documentation](https://v2.tauri.app/zh-cn/develop/calling-rust/)
  define the existing JSON command/Result bridge. Acceptance remains separate
  from the application-specific correlated completion receipt.
- The community-maintained [Tauri source repository](https://github.com/tauri-apps/tauri)
  publishes the [API MIT license](https://github.com/tauri-apps/tauri/blob/dev/packages/api/LICENSE-MIT)
  and [Apache-2.0 license](https://github.com/tauri-apps/tauri/blob/dev/LICENSE-APACHE-2.0).
  No new dependency, copied implementation, image or model was introduced.
  New project source files retain GPL-3.0-or-later notices, matching the repository.

## Source inspection and later local acceptance

Allowed inspection is source review, TS/TSX parse-only AST inspection with the
already-installed Babel parser, and whitespace/diff checks. These are not tests
or a typecheck and do not establish runtime correctness.

Qoder should exercise A/B edits and revisits; all enabled faces in the preview;
save/reopen and undo/redo; exact scope/source displays; one-key unset; equal-group
conflicts; confirmed versus candidate links; disabled/manual regions; original
RGB8/16 export; rapid target/photo changes with an outstanding portrait gesture;
engine exit/restart with a pending receipt; panel collapse/reopen; and original
viewport manual-region correction. A failed or uncertain action must not show
success, silently replay or mutate the new photo/scope.
