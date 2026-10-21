# Interactive editing regression pass — 2026-10-21

## Reported acceptance targets (not completed by this document)

1. RAW first display, editable readiness, repeat navigation and cache performance.
2. Neutral import must not silently apply portrait softening; distinguish camera JPEG rendering, our RAW rendering and display resampling.
3. Single / side-by-side / wipe comparisons must be usable without repeated original-fetch flashing.
4. Exposure, curves and HSL must have discoverable, working controls. Curves are still unwired; navigation changes are not implementation of curves.
5. Nearly all sliders feel slow: measure queueing, processing and upload separately. Latest-value coalescing must preserve the final value and edit/history/document boundaries.
6. Tool navigation should follow the reference's category hierarchy, not one enormous list. Do not remove features to simplify the menu.

The reported desktop entry is the existing installed package, not the independent bb963 test candidate. Both label themselves 1.12.1, so version text alone is insufficient provenance. New changes must be tested on their own exact commit before installation or completion claims.

## Changes in this candidate

- Compare effect depends on primitive document/load identity rather than the new image object returned by every status poll.
- Original snapshots require matching request ID, document, original-view receipt, exact frame sequence and complete nonempty RGBA data. Old receipts, edited frames, partial buffers and cancelled requests are rejected. A deadline reports failure instead of waiting forever.
- The engine echoes correlation metadata; Rust retains the comparison receipt. No image processing was moved to JavaScript.
- Viewer keeps a verified original separately. Side-by-side renders both complete images; wipe position and mode changes repaint without requiring a new engine frame. Display-only changes redraw the retained GPU texture instead of assuming the WebGL drawing buffer persists; they do not add a second full-image copy to every slider frame. Unchanged displays do not continually redraw.
- Right-side category rail selects one family panel. All specification families retain a category; global search can reveal matches across categories. Default panel is color, with basic color family open. Portrait subject selection belongs to the portrait panel.

Official reference reviewed: https://www.pixcakeai.com/guide/47246 and https://www.pixcakeai.com/guide/32455 . The hierarchy is adapted; no proprietary assets or branding were copied. Full reference parity, customizable toolbars and search-result navigation/highlighting are not claimed.

## Verification so far

- Frontend typecheck: passed.
- Frontend unit tests: 41 passed (including 9 capture identity/cancellation/data tests and 2 category coverage tests).
- Vite production build: passed, with existing >500 kB chunk warning.
- Python source compile check: passed.
- Native compilation, correlated engine protocol test, actual GTK/WebKit window interaction: pending for this candidate.
- These checks do not certify RAW latency, neutral full-resolution quality, slider latency, curves or visual usability.

## Architecture direction

Prefer Rust for new core orchestration, caching, IPC and suitable processing components. Preserve mature model interoperability where Python remains necessary. Keep the Tauri/React frontend for now; moving languages must preserve output correctness and demonstrate measured benefit, not merely be labelled a performance improvement.

## Rust dispatch follow-up (not yet performance-accepted)

A paired host/engine transport now acknowledges completion after command handling,
including validation failure and history recording. Rust keeps one command in flight.
Only explicitly interactive skin/exposure/HSL submissions opt into adjacent latest-value
coalescing. Different controls/targets and all ordinary commands (including document,
history, export and reset operations) retain ordering barriers. Ordinary protocol clients
without a host request ID retain their existing event stream. Unknown old engines fail
compatibility checking rather than leaving a queue waiting forever.

The bounded queue reserves a final shutdown barrier; it never silently discards ordinary
commands. No retry is performed after an uncertain write. Queue counters expose pending,
in-flight and coalesced work for subsequent measurement. This is not a claim that all tools
or all sources are now responsive: deform/other operations, frame transport, high-resolution
preview policy, and actual GUI latency still need testing.

Baseline measured by Qoder on bb963, synthetic 4096×3072 source, actual AMD CUDA/ROCm and
enforced engine offline policy (not RAW or GUI performance):
- 1,034,880 preview pixels: single strength median 2.2 ms; 20-value burst tail 39.7 ms.
- 8,260,160 preview pixels: single strength median 14.6 ms; 20-value burst tail 298.4 ms.
Both processed all 20 intermediate values. The initial 8,388,608 budget was invalid;
the corrected 8,294,400 budget was measured without changing production limits.

Local verification for the dispatch change: two transport tests and a real enforced-process
hello/error/shutdown receipt smoke test passed; frontend 41 tests, typecheck and production
build passed. Rust queue tests and native compilation are CI gates; hardware/GUI dispatch
comparison remains pending. Host and engine must be deployed together.

## Comparison layout and navigation follow-up

Side-by-side now has a true two-frame-wide display surface, preserving image aspect ratio
and per-image 1:1 scaling; original/edited labels match the pixels. Wipe stays single-frame
wide. Brush and person-box editing require single view until their comparison coordinate
mapping is implemented, with an explicit hint rather than misdirected strokes. Category
scroll positions and both expanded/collapsed states are retained. These are UI code changes,
not a claim of a completed native visual review. Frontend suite now includes 42 tests.

## Main-panel skin scope correction

The main RetouchPanel (not just the legacy App handler) now explicitly uses the semantic
skin channel. It requires an available, nonempty skin mask; absent analysis is not permission
to blur the whole photograph. Single-person skin editing remains unwired and is explicitly
blocked rather than applying an all-person mask under a single-person label.

Each slider submits only its changed field. Rust set_strength accepts an omitted strength
so a radius/detail edit does not write a stale strength or overwrite unrelated bands. The
engine already preserves omitted values; a focused contract test pins that behavior. The
frontend suite has 43 tests after adding main-panel scope/patch/availability coverage.
Full-mask-outside pixel verification and actual GUI behavior remain separate pending tests.

A further failure-path guard preserves the requested skin channel when derived masks cannot
be restored (import/history/device/session replay). Rendering temporarily uses zero skin
strength without erasing the saved recipe, rather than clearing the channel and broadening
the same strength into a whole-image blur. Explicit unmasked protocol edits remain supported.
Three focused patch/suspension contracts pass locally; real masked replay is still subject
to the engine/model regression suite. This is a concrete fallback defect, not proof that it
was the sole cause of the user's old installed package's neutral-import appearance.

## 2026-10-21 — Coalesced panel status refresh

The Rust dispatcher remains the authority for command ordering and latest-value coalescing. The React panel now coalesces redundant status reads into an 80 ms timer, allows one pump read in flight, and continues reading while the host reports pending/in-flight edits. A trailing read is retained when an edit arrives during a read. The existing one-second health poll remains; this change does not throttle frame delivery or claim a measured GUI latency.

The pump is created inside an effect, with a fresh instance on every setup (including StrictMode replay); cleanup disposes only that instance. Switching between split and wipe reuses the same verified original snapshot rather than recapturing it. New image identity, engine restart, leaving comparison, and workspace changes still invalidate it.

Validation: frontend typecheck, 47 Node tests, and production build passed locally. Four pump tests cover burst coalescing, busy queue draining, trailing reads, and disposal. Native desktop control/visual acceptance remains pending. This is not RAW import, curves, or whole-product completion.

Read-only installed-package inspection found `/usr/lib/LumaRetouch/engine/src/lumaretouch_engine/server.py` uses `DEFAULT_STRENGTH = 0.5` and initially unrestricted channel, unlike the candidate's zero default. This explains a plausible direct path to unsolicited smoothing in the old desktop package; it is code evidence, not a reproduction using the user's photograph. The installed package was not modified.
