# S1 / S2 current-image notices — source-only review

## Implemented boundary

- App's **existing accepted** `engineStatus` response feeds a read-only projection after `statusFence.accept`; no listener, command, log parser, alternate polling, or task owner is added.
- `CoreStatusNotices` is mounted directly in the actual production `<main className="stage">`, outside development-only controls and across workspaces.
- The displayed device is the `image_ready.device` fact for the image load. Explicit CPU alone is **not** called a fallback. An optional `device_fallback` string is shown only from the same scoped image receipt. Missing field is explicitly unreported, not “no fallback”.
- Decode notes are copied from that receipt, with input assumptions prioritized. This includes ordinary missing ICC and PNG16's missing ICC/other declaration statement. Missing notes never infer ICC absence. No decoder/error path is modified; damaged ICC rejection remains backend-owned.
- Reported resource fields show exact nonnegative safe-integer byte counts in an expandable **load-time snapshot**, not live totals, free RAM, memory admission, or a performance promise. Omitted/invalid values are not zero-filled. Byte categories are not summed.
- Notices require engine_alive=true and equality of image load_id, image doc_state.document_id, latest doc_report document_id and session doc_state.document_id; session current path/index must also agree. The same session receipt's explicit project identity must match the separate project status. No historical load blacklist or user-intent reset exists, and no decoded assumption is cached across images.
- The existing atomic `session_state` event carries both document state and project state. This proves successful create can retain the same image load under a new project, while a stale session/new project pair hides notices only until the confirming session arrives. Rejected create/open preserving old state retains old facts correctly. Torn rejected snapshots cannot poison future complete snapshots.
- Unmanaged import requires session.project to explicitly contain open=false, project_id=null and path=null. Only in this explicitly proven case may the native project slot be null (before any project event). Missing/malformed session ownership never implies unmanaged; managed ownership requires nonempty project ID/path and exact agreement.
- Text is bounded (8 unique notes, 240 characters each, device 64), scrollable to 180px, plain React text (not HTML). No source path is rendered by the component itself.

## Source evidence / cross-owner contract

- `engine/src/lumaretouch_engine/server.py`: `_make_pipe` emits unscoped `engine_warn` from `pipe.fallback`; `image_ready` emits actual device, load_id, doc_state and resource fields. Those old logs cannot establish a current-image reason.
- Coordinated backend owner change observed in current source: `image_ready` includes the actual `pipe.fallback` string or explicit null alongside load_id and device. Native `on_image_ready` retains the raw JSON; no alternate event cache is needed. The UI defensively consumes this optional field locally without changing shared `native.ts`.
- This covers actual pipeline fallback only. Automatic device resolution warnings emitted separately (e.g. torch unavailable) do not become attributed reasons unless the backend supplies a similarly scoped fact.
- `decode.py` explicitly appends missing-ICC assumptions and rejects invalid ICC conversion. This change does not synthesize metadata or change color processing.
- `ui/src-tauri/src/main.rs` reads status slots under separate locks. The projection rejects identity disagreement rather than trusting a torn snapshot. `server.py:emit_session_state` and `project_package_project_commands.py` supply the project/load bridge; successful create emits an updated session without requiring image_ready. The regression fixtures include this retained-load boundary, late project metadata, torn report/load, failed operations, and standalone import.

## Acceptance still UNRUN

No application execution, test, build, typecheck, project import, inference, install, or download was performed. Regression fixtures are authored only, and are not added to shared package scripts. Source inspection is not runtime or quality acceptance.

When authorized, run the module fixture and UI typecheck, then verify: CPU selected versus actual CUDA fallback; explicit null versus absent fallback field; CPU-only full workflow quality/performance separately; ordinary and PNG16 missing ICC versus tagged ICC; damaged ICC rejection; same-path different-load navigation, successful create retaining image, failed create/open, project replacement/reopen, standalone import, shutdown/restart, delayed status and thumbnail continuations; long notes/small viewport; device changes and edits do not mislabel load-time resources as live.

S1 is a display-wiring improvement, not full CPU compatibility/resource-admission acceptance. S2 is a source-wired notice, not color accuracy acceptance.
