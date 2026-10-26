# Ordinary export task controls — bounded L1 slice

Status: source-only implementation. Runtime, UI, race, export quality, and performance acceptance **UNRUN**. No tests/build/typecheck/product import/inference/install/download performed.

## Reachability and identity

`App` already mounts `ExportQueuePanel`; that panel now mounts `ExportTaskControls`. No App integration change is needed. The UI consumes engine-authored allowed actions, states, counters and blocked reasons, not selection or the legacy StudioPanel.

The existing `runTask(action, taskString)` and native task command carry a qualified reference containing exact task ID, a fresh session-local per-task token, immutable project/workspace/session identity, string revision and request ID. Engine validates the reference under a task RLock before any mutation. Task ownership is frozen only at creation/restore using DocumentVersions.owner/workspace; listing after project_create cannot adopt retained tasks into the new project. Session tokens/ownership/results are excluded from task persistence and discarded on restore. All public mutations reject raw IDs/default/all. The sole internal group-cancel owner hands over the exact retained task object to a non-command helper, which checks immutable ownership and constructs a qualified reference; no JSON bypass flag exists. UI mutation pending state survives panel remounts. Dispatch acknowledgement does not unlock it: only a matching task-token/request/action result does. Invalid/stale identity stays unknown and locked; read-only refresh never resends. Stale revision rejection is correlated and can be safely retried only after an explicit new click on refreshed state. Delete removes the row and publishes an exact task/token/project/workspace/session/request/action receipt. The native host retains a bounded receipt list so deletion can be reconciled after the row disappears; only exact matching receipts settle the pending deletion.

## Boundaries

* Queued/retrying pause requests are legal and survive worker startup; cancel likewise survives startup.
* Boundary waits release the RLock. Request/transition/result events are serialized against start, boundary, item receipts and finish.
* Pause during the final atomic commit permits successful terminal accounting after committed output, rather than an illegal transition from pause_requested.
* Target preflight uses an independent task copy before mutation. Public bulk mutations are refused rather than allowing unbound all/default selectors. The helper also rejects multi-task retry before any start. Delete is allowed only for terminal records with no live worker; only ledger and in-memory task-argument entries are removed, never files.
* Retry uses retained same-session snapshots and the same task ID. Per-item rendering owns its input snapshot in all formats so analysis enrichment cannot mutate retained retry inputs. Reopened project records remain explicitly non-resumable/non-retryable without persistent recipes. Cancel/delete remain available as appropriate.
* Controls may need a read-only refresh after worker exit: the final event is emitted before `Thread.is_alive()` becomes false. This is conservative, not an implicit retry.

## Separate small S1 field

The single `image_ready` constructor also reports `device_fallback`: the current image pipeline's actual nonempty string `pipe.fallback`, otherwise null, next to existing `load_id` and `device`. No CPU=>fallback inference and no log scraping. Added at parent request for the parallel status UI owner.

## Not closed

This does not close all of L1: general long-model task checkpoints and broader task-kind semantics remain. L2 persistent frozen recipes, dependency reconstruction and crash reconciliation remain. Source inspection and AST parsing are not behavioral evidence. The companion JSON enumerates unrun acceptance scenarios.
