# Portable project UI acceptance cases — UNRUN

No build, compiler, typecheck, application import, test or package creation was run during authoring.

1. With an open saved project, preview with both checkboxes off. Confirm embedded replay assets appear and external originals remain declared but excluded. Change either checkbox: old preview disappears.
2. Cancel each native file/folder/save dialog and confirmation: no write operation occurs. Existing archive target refuses overwrite. Restore parent produces an explicitly displayed unique child destination.
3. Create and restore: transport acknowledgement alone must not show completed. Status polls the original operation ID until terminal state and displays manifest SHA only from completion.
4. Break transport after creation request. UI retains original ID, blocks second submit, and provides query. Reload must query the same ID, not resend creation.
5. Reject or interrupt cancellation. UI marks outcome unknown and keeps the original operation query available. A cancellation acknowledgement must not fabricate a terminal cancellation.
6. Reload/unmount while running; reenter project workspace. Existing operation remains recoverable. Unknown engine epoch never shows stale transport receipt as completion.
7. Restore missing sources: dependency list remains visible; source repair uses existing full-hash SourceRelocationPanel, external sky references point to sky asset picker. Virtual-copy identities/history remain independent.
8. Explicitly open restored project with current dirty edits. No force open; engine rejection must preserve current edits. UI verifies actual engineStatus project path before treating open as confirmed.
9. Duplicate clicks while native picker open or while request pending must produce one write ID. Changing active project invalidates old UI preview; backend stale-preview admission must reject.
10. Malicious archive rejection (path traversal, links, compression bomb, duplicate/case names) surfaces the backend error, no restore-success state or execute action exists.
