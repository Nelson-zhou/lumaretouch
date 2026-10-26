# Retained history step navigation — source-only

Status: **AUTHORED / UNRUN**. This is not product acceptance. No test, build,
typecheck, product import, inference, network request, installation or download
was run. Qoder owns subsequent local validation. Existing undo/redo and project
history persistence remain the canonical owners.

## Preserved requirement and bounded surface

- `ui/src/spec/workflows.json`, ID `47209`: 历史点击某一步恢复.
- `ui/src/spec/refine.json`, ID `PC-47209`: 历史可回到某一步.
- The existing history panel now reads the actual retained undo/current/redo
  segment and offers a button for every retained position. Numbering is relative
  to that **exact current retained segment**. The oldest position is “保留起点”,
  never “原图”, and no action names are inferred from current recipes.
- Current owner: `HistoryController`, `Engine.HISTORY_MAX = 64`, gesture window
  700 ms. The normal combined chain has at most 64 transitions. The existing
  saved format independently bounds each stack at 64; an unusual combined chain
  over the owner limit is still listed but navigation is refused before writing,
  because canonical replay would otherwise evict an endpoint. No folding,
  migration, new history ledger, history labels, snapshot library or export UI.
- This feature navigates retained state only. It does not change which history
  survives saving/reopening, invent unavailable old steps or implement the
  reference product's restart-folding behavior.

## Source route and ownership

1. `App.tsx` mounts `useHistoryNavigation` for its lifetime. `RetouchPanel`'s
   existing `PC-47209` block contains `HistoryPanel`. An unresolved request and
   its query/reopen/explicit-abandon controls survive panel closure at App level.
   Completed mutation messages also remain until explicitly dismissed.
2. `native.ts` exposes separate request/status/abandon calls. Navigation settles
   the existing curve edit barrier and announces inspection edit intent. Read
   requests do not invalidate captures. A pending request is saved before send;
   one request is admitted at a time; repeat clicks cannot submit another jump.
3. `history_navigation_protocol.rs` validates exact request shape, metadata
   budgets, u64 revision budget, target domain and computes the bounded adjacent
   undo/redo plan. `history_navigation_api.rs` retains only original requests and
   exact native-validated receipts, never image snapshots. Dispatch is bound to
   the observed engine epoch. Queue `{requested:true}` is never success.
4. `server.py` registers `history_navigation`. `state` reads current metadata
   without edit/capture invalidation. `history_navigation.py` binds stable runtime
   document ID, workspace, load ID, revision, exact digest and cursor. The digest
   uses the existing streaming candidate fingerprint with opt-in exact keys;
   default fingerprint callers are unchanged. It includes the current recipe,
   ordered undo/redo snapshots and sparse transition metadata, coalescing state,
   complete current people graph and its monotonic ownership fences.
5. The engine independently checks the native plan's inputs against a fresh exact
   checkpoint. It executes **only adjacent** `HistoryController.handle_command`
   undo/redo calls. The existing body and people sparse patch implementations,
   source-switch/proxy checks, shared/batch refusal, renderer, remember-current,
   reverse patch decoration, `history_state` and frame output remain in that
   canonical path. No arbitrary target snapshot is passed to `_history_apply`.
6. Each successful edge proves exact resulting ordered stacks against the
   canonical `body_pose_history_chain.decorate(before, actual_after)` reverse
   transition, unchanged owner/session identity and expected actual cursor.
   Each proved successful edge marks the existing project dirty (including a
   known partial after a prior save); no-op/refusal does not invent an edit.
   Intermediate checkpoints never replace an additional history store.

## Truthful terminal semantics

| Phase | Meaning | Selection/retry behavior |
|---|---|---|
| `state` | Actual current retained metadata, no mutation | Valid only for that context/digest |
| `applied` | All requested canonical edges completed and exact reached-chain proof exists | Refresh current engine state; reread timeline |
| `no_change` | Target already equals current cursor | No fictitious operation recorded |
| `rejected` | Prewrite refusal; optional exact unchanged checkpoint after attempt fence | No automatic retry; stale selection invalidated |
| `partial` | Earlier edges completed; next edge refused **before restore**, with exact current checkpoint | Actual reached cursor shown; target explicitly not reached; never auto-continue |
| `unknown` | Any restore-entered failure, unproved rollback, stack/publication error or ownership drift | `reached: null`; last-confirmed checkpoint is explicitly NOT current state; query-only |
| `not_sent` | Native synchronous pre-enqueue refusal for this exact request | Exact native-admission authority only |

`HistoryController` gained only an optional private trace dictionary recording
entry into the existing restore port. Legacy callers, return values, rollback,
stack persistence and frame publication remain unchanged. In particular, a
legacy rollback returning normally is **not** treated as exact rollback proof:
people/body ownership counters may have advanced, and output restoration may
have failed. The new route is conservative and keeps that result unknown.

Known partial is not all-or-nothing: committed earlier edges are retained. The
existing project recovery boundary consumes an internal navigation phase; known
partial increments its mutation revision without falsely tainting it as unknown.
An unresolved navigation blocks edits/history/save/export and project creation.
The current reached claim is cleared and the private phase becomes unknown
BEFORE each identity/checkpoint/revision-fence attempt. A failed post-fence
source/people checkpoint retains only a historical last-confirmed value, never
an old digest/revision mislabeled as current. Zero-step no-change also requires
exact equality to the original complete retained view in native and UI readers.

## Receipt and recovery fences

- Raw terminal JSON must be bounded, duplicate-key-free, exact original-request
  matched, current owner/epoch matched, and structurally truthful. A renamed or
  malformed owned result cannot enter generic recovery or App event handling.
  Both command→event and event→command family checks protect ID collisions.
  Navigation requires the reserved `history-nav-v1:` request-ID namespace (UI
  suffixes it with a fresh UUID). Every other family is refused before sending
  if an ID field, including nested target/capture/operation aliases, borrows it.
  Both `EngineHandle::send`/`send_interactive` entry points and all seven direct
  control writers enforce the same predicate before any queue/write. The engine
  reader skips all read/cancel controllers for a borrowed namespace; the executor
  rejects before handler selection, still issuing its normal command-done ACK.
  Thus earlier/later genuine legacy read terminals cannot collide with admitted
  navigation IDs. No read receiver is bypassed or altered, no broad generic-state
  fallback exists, and no global ID registry or second ledger was added. The
  feature is unpublished/unrun: no deployed unprefixed navigation format is
  migrated, resolved as success or resubmitted.
- Namespace-exclusive, epoch-matching mailbox identities remain raw-event guards
  after mutation settlement and read-only completion, so late duplicate/renamed
  terminals cannot refresh a canvas or manufacture project-open state. An explicit
  injected foreign pending fence still wins over a retained row (defense in depth;
  public admission cannot create that collision). Independently, the exact event,
  `original_request.cmd`, or navigation-exclusive top-level completed/reached/
  last-confirmed markers identify stripped-ID renamed packets at BOTH generic
  recovery and App dispatch boundaries. Generic protocol/phase fields alone do
  not classify unrelated packets. Native `not_sent` cannot settle another owner.
- Status only reads the mailbox. A lost mailbox reserves the exact identity as
  observation-only; a later invocation cannot resubmit it. Timeouts, changed
  photos, panel closure and project creation never unlock a mutation.
- Same-epoch abandonment requires an explicit unresolved+idle baseline followed
  by a **later** strict unique-JSON `project_opened` event with verified opened
  project fields, then another idle observation. Prior queued opens cannot
  qualify. Only a new engine epoch or this later actual state-replacing open
  permits explicit abandonment. Canonical `project_opened` is unkeyed; a renamed
  keyed receipt cannot manufacture reset evidence. Its envelope permits only
  canonical project-open fields; stripping request_id from a renamed receipt
  while retaining original_request/protocol/action/view/reached is also rejected. The native navigation fence
  is not removed by generic project events; the proved abandon removes only its
  exact original fence, without claiming the unknown operation succeeded.
- Engine-side unresolved state is cleared only after the real project-open
  replacement path publishes `project_opened`, not by a bare workspace-token
  change, project creation, document selection or timeout.
- Canonical intermediate `history_state` and frame events update the existing
  canvas/status route. An original receipt never injects its old document state
  into a replacement canvas. Any published context/revision change invalidates
  the timeline; rereading it is explicit.

## Validation boundary

Executed: Python `ast.parse` of the changed Python sources/fixture; JSON decoding
of the source manifest and matrix; SHA-256 hashing; `git diff --check`.
**UNRUN:** Python fixtures, Rust fixtures, TS fixtures, Rust/TS syntax parsing
(parsers unavailable; no installation), typecheck, build, renderer/output, UI,
saving/reopening and all inference. Source parsing is not an implementation test.

`unrun-matrix.json` gives the local validation obligations, including real sparse
body/people/shared histories, frame publication failures, output/save roundtrips,
rapid clicks, panel closure and causal recovery. `source-manifest.json` pins every
owned source/doc/fixture byte (except the manifest itself) and the read-only
canonical dependencies used in review. Root reviews and publishes; this source
owner does not commit or push.
