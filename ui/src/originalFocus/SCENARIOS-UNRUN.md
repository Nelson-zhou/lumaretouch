# Original focus review — source-authored scenarios, NOT RUN

No build, typecheck, test, application startup or inference was performed for this change.

- Open the existing Library or Retouch filmstrip: the shared query controls expose original focus review. A plain open does not implicitly select a row. Zero, nine, hidden or unresolved selected rows disable start. Explicit 1–8 rows enable it.
- Set X/Y to blank, nonfinite, negative or >1: no request. Valid edge points remain valid, including zero; center defaults to 0.5,0.5.
- Inspect the request: `focus`, exact ordered indices + document IDs, focusX/Y/ Documents via Tauri, snake_case to engine. Reorder/remove rows before engine receipt: reject instead of reviewing another photo.
- Double click start: one local lock. Acknowledgement alone is not completion. Engine events drive running, stop and terminal errors. Repeat identical rejection: host_sequence distinguishes the new event. Query state resolves an unknown request without starting another worker.
- Stop mid-run; show only canonical completed rows after terminal status. Per-row failures show their own errors. Starting again removes old run results via canonical session data.
- Select another row, change filter/session/source or remove a selected row: no detached cached result shown. Source change hides old result with engine error; refresh/review required.
- Compare original and edited virtual copy: source crop is identical at same point; edit preview, camera preview, ratings, flags and recipes remain untouched.
- Show each <=256x256 image at literal intrinsic CSS dimensions, with scroll overflow rather than fit scaling. Confirm source extent, bit depth, point, rectangle, SHA and notes. Display clarifies CSS pixels versus physical screen pixels.
- Low contrast: no normalized detail conclusion; show warning/null. No best/rank/reject suggestions or automatic rating/flag changes.
- RAW before canonical open, >32MP source or insufficient memory: clear failure, no preview fallback.
