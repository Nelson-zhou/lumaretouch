# Independent inspection backend (work in progress)

This internal protocol is not a completed 100% Viewer. The Rust host must still
own request generations and validate/consume LRIF before a future UI may display it.
No new display controls or release/installation claim accompanies this backend.

`inspection_snapshot start` without `render` retains the preparation-only contract.
An explicit `render` admission adds an engine-owned private job directory, bounded
array/manifest spool, independent CPU process, private LRIF result, and release.
Inputs come from the active document's captured recipe, not client-provided assets.
The worker uses the shared full-source export recipe and pixel pipeline, rejects
missing active layers, and never substitutes proxy pixels or resizes silently.

## Limits and ownership

- Snapshot arrays: explicit budget up to 512 MiB; known records, numeric dtypes only.
- JSON manifest: up to 2 MiB, 10,000 tree nodes, depth 128, 1 MiB UTF-8 text.
  The encoder temporarily builds JSON text; this is not a 2 MiB metadata RSS cap.
- Array and manifest disk writes are ticked. Bytes per tick do not bound disk latency.
- Independent Linux worker applies address-space, file-size and CPU limits before
  NumPy/Torch imports. Address-space limits are not RSS or total-machine RAM limits.
- RAW output pixel size is verified after decode; decoder allocation is constrained
  by worker address space, not a proven pre-decode pixel-memory estimate.
- Wall-clock timeout is checked by the command loop when it services the job. It is
  best-effort, not a hard deadline while a handler or continuous queue delays ticks.
  CPU-time limits remain independently enforced by the worker OS resource limit.
- One worker/result lease. Export/task resume/retry/benchmark cannot begin while a
  cancelled worker is still exiting. Normal edits cancel first and use independent
  arrays. Shutdown kills and waits for its own worker before deleting the job.
- Fixed filenames in a private temporary directory; no pickle or arbitrary imports.
  File readers reject nonregular files and final-component symlinks without FIFO
  open blocking. The directory is trusted only because the Engine created/owns it.
- Source dev/inode/size/mtime/ctime are compared before/after decode and render.
  This detects ordinary external changes; it is NOT an immutable content snapshot
  or a complete TOCTOU defense. Strong source-version ownership remains unfinished.

## State and result contract

The command returns its usual ACK before rendering finishes. States are copying,
spooling, rendering, ready, cancelling, cancelled, released, or failed. A ready
render event has `preparation_only=false` and a private `result_path`. That path is
not a user export or a public download; release/next edit/engine exit removes it.
The host must never treat `command_done` as a pixel result or copy LRIF into the
existing proxy frame layout. Full ticket/epoch matching and final stale-result
checks remain mandatory at the host integration boundary.

Tests are separate evidence: bundle structure/corruption, command lifetime,
independent worker execution, and full active-layer quality coverage must not be
collapsed into a claim that the full product or UI is finished.

The worker sets Linux PR_SET_PDEATHSIG to SIGKILL and checks the expected parent
PID after binding, so parent death before binding is not silently missed. This
controls the worker process, not an arbitrary descendant process tree; abrupt
parent death may still leave its private temporary files for host recovery.
References checked during implementation:
- https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html
- https://docs.python.org/3/library/resource.html

## Runtime-mapping diagnostic

The first actual ROCm-venv run at a 4 GiB address-space admission failed before
rendering: `ImportError: libmagma.so: failed to map segment from shared object`.
That failure is preserved, not counted as a passing pixel test. The next test
separates a deliberately insufficient 512 MiB admission (explicit failure, Engine
still responsive) from the existing maximum 8 GiB admission (must produce exact
pixels and release its file). No production cap is increased or disabled. An
8 GiB virtual-address allowance is not an 8 GiB physical-memory allocation or a
performance result. Dedicated CPU runtime packaging and host admission policy
remain separate work; the higher-budget attempt is not yet a verified remedy.
