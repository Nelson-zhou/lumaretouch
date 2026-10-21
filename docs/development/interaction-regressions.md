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
