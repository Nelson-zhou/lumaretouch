# Group delivery UI — authored scenarios, UNRUN

No build, typecheck, unit test, native runtime, inference, output-quality or performance check was executed.

- Complete group receipt carries exact token, batch id, workspace and every post-apply document revision. Only then hand off; an incomplete delivery receipt must not turn a successful apply into permission to apply again.
- Save button sends a separate explicit scoped save action. No save is triggered by apply, opening export settings, preview, or start. The message must not imply unrelated dirty edits were saved.
- Change filmstrip selection after opening group export: existing settings and destination planner remain visible, but exact successful group document IDs remain pinned.
- Change profile, format, watermark, layout, destination or current edit revision after preview: invalidate destination and require a new preview; no fallback to generic export.
- Confirm a skip/rename destination policy using existing UI. Collisions stay skipped/reported or uniquely named; there is no overwrite option.
- Double-click save or start: retain one request ID. Timeout/transport failure, remount and workspace navigation keep the original pending request; reconciliation only reads that request.
- Start returns unknown with an exact task ID: block a new start, but permit fresh reads of the same canonical task. Unknown without task ID keeps the original start request unresolved.
- Start returns requested/queued: never display output completion. Read only the returned exact task, never the newest/global task.
- Running task cancellation uses its exact task ID. Cancellation is a request, not immediate completion; preserve already succeeded and failed/skipped/pending items until canonical terminal status.
- Task succeeds partially, fails or is cancelled: show actual item states and paths; never convert skips into success and never auto-retry or delete earlier outputs.
- A completed or failed task cannot be re-exported through this handoff. Explicitly leave group mode for ordinary workflow; this does not erase task receipts.
- Engine restart or project change locks the retained handoff. Late old-session replies cannot attach to a newer engine/project or clear the original unresolved state.
- Navigate away and back while export runs: retained task and request identities survive. Existing queue view remains canonical; group panel does not claim independent file hash verification.
