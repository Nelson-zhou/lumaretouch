# Saved-project ingestion and two independent workflow modules

Source baseline: 2712b5884a2c6754e4fcddc2673905552af0ee86.
This snapshot is source-connected and unexecuted, not functional acceptance.

## Real integration boundaries

- `core/tether_capture` supplies the versioned system-libgphoto2 adapter, without
  bundling or installing camera drivers. `ui/src-tauri/src/tether_host` owns its
  device thread, durable intents, events and completed private transfers.
- `core/local_workflow` supplies versioned graph validation and durable occurrence
  scheduling. `ui/src-tauri/src/local_workflow_host` owns definitions, polling,
  exact saved-project leases and original-request receipt reconciliation.
- `ui/src/tetherCapture` and `ui/src/localWorkflow` provide actual native-backed
  panels mounted in `ProjectWorkspace.tsx`, not mock host implementations.
- `ingest_session_api.rs` and `ingest_receipt_validation.rs` admit exact engine
  receipts. Owned dispatch checks the expected epoch under the final engine
  lock, so an old command cannot enter a replacement engine.
- Engine `ingest_session_host.py` delegates to the existing atomic managed import
  using internal source/precommit/root-descriptor hooks. The root pin is checked
  on the actual opened directory before writing and again before committing.
- Engine `workflow_owner_*` binds genuine fixed-profile export to the same lease,
  retains the original task identity and hashes the actual output for success.
  `owned_export_destination.py` carries trusted directory identities through the
  existing export runtime and atomic writer, not through user JSON fields.
- `command_registry.py` and `export_command_reply.py` are real extractions to
  retain server modularity and its line cap. Existing command order and generic
  exporter behavior are preserved when the optional internal hooks are absent.

Both modules retain their own state/resources and explicit unsupported-capability
responses. This is compile-time modularity, not a claim of hot plugin loading.
Shutdown stops producers before engine shutdown; requesting stop is neither
hard cancellation of a native camera call nor rollback of an admitted write.

## Acceptance and remaining scope

All builds, typechecks, tests, hardware interaction, filesystem behavior and
end-to-end acceptance are UNRUN. Static Python AST/JSON/TOML parsing, source
call-path review, hashes, whitespace and file caps are the evidence supplied.

An engine restart does not reconstruct a lost lease. An admitted export failure
without an affirmative never-committed receipt remains Unknown even if its
output is now absent. These unresolved outcomes cannot authorize blind retry,
automatic lease release or an assertion of successful cancellation.

Tether follow-latest, physical user-pattern destination filenames, automatic
reconnect and preset synchronization remain missing. Workflow preset execution,
ERP, AI culling, arbitrary profiles, branching/loops and full restart recovery
remain missing. Exact original requirement statuses and limitations are in the
two family REQUIREMENTS.md files; neither entire handbook workflow is accepted.
