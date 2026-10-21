# Full-source inspection Viewer integration

Status: candidate implementation, not product acceptance. Native host baseline
`b1b0380e6c935d51c077cf943dd70b0fe6374452` passed CI non-GPU checks, 54 local
backend cases and 32 native inspection cases. Those results do not validate this
new frontend or real RAW latency, image quality, Wayland, GPU or packaging.

## Contract

- Fit retains the existing proxy/GL presentation and acknowledgement loop.
- 100% requests an identity-bearing full-source ROI after 120 ms settling. The
  backing canvas contains only the requested pixels, never the whole source.
- Geometry uses current crop/rotation `out_full`, absolute device-pixel alignment
  and current DPR. Source geometry is not inferred from stretched proxy shape.
- Pending edits, viewport changes, document changes and comparison immediately
  hide the detail canvas. Comparison remains explicitly a proxy comparison.
- One controller serializes admission, polling, pull, pixel copy and release.
  No transferred buffer is kept in React state. Reveal follows release and a
  final epoch/generation/request check, not merely successful decoding.
- Uncertain pull/release responses retain exact cleanup ownership across mounts.
  Cleanup is retried only after status verifies that exact lease is still held.
- Re-clicking 100% changes a retry token. Returning to Fit or switching documents
  disables inspection. Viewports exceeding the 16 Mi-pixel patch budget are
  explicitly reported as proxy fallback, never silently downsampled.
- No new dependencies. TypeScript permits `.ts` import suffixes under existing
  `noEmit`, matching Node's strip-types unit-test runner.

## Required validation

CI: frontend typecheck/build and controller/geometry unit tests, plus existing
regressions. Qoder: actual native API pixel identity/release/cancel tests, then
real 100% display, pan (including zero/subpixel movement), edit invalidation,
retry, document switch, compare suspension/resume and monitor DPR changes.
Do not count synthetic API pixels as GUI/RAW/portrait quality acceptance.

## Known scope

The full-source worker currently renders the complete recipe before ROI output;
this is not tiled algorithm evaluation or a performance promise. Full-resolution
comparison, automatic inspection at arbitrary zoom, GPU worker acceptance,
large-source tiling and production resource policy remain separate work.
