# Colour scopes v1 — basic checks verified; product acceptance remains partial

Requirement: original manual professional-colour section “直方图/RGB-Lab”; trace
`PC-32455-C-50c884e953`. This slice implements explicitly refreshed, bounded proxy
histograms and aggregate colour readouts. It does NOT complete point/area eyedroppers,
full-source histograms, Lab histograms or live performance acceptance.

## Ownership

- Rust `scopes.rs`: 256-bin RGB and linear-Y accumulators, under/overflow counts,
  nonfinite accounting, encoded-sRGB mean and that mean's Lab-D65 conversion.
- Rust `wire.rs`/`main.rs`: versioned bounded binary input, bounded JSON output.
- Python `color_scopes_sampling`: producer-stage float sampling on the source device.
- Python `color_scopes_controller`: read-only request validation through four ports.
- Python `color_scopes_bridge`: transport only, no duplicate histogram algorithm.
- Native `color_scopes_host`: one latest request/ticket and accepted result;
  invalidation rejects already-running late replies, including repeated public IDs.
- Native `color_scopes_api`: read-only coalesced queue path, not the edit dispatcher.
- UI `HistogramPanel` and `colorScopesModel`: presentation and stale-result policy.

Engine/App remain wiring points, not statistical implementations. Native-main cap
2030→2040 is reviewed for module/state/event/command wiring, not permission to add
new business logic there.

## Domain and sampling

Opaque working-sRGB RGB samples are gathered before display quantization. Stages:
original working proxy (uncropped), exposure output / levels input, levels output /
curves input, and final geometry/background output. Same rendering chain, optional
stateless taps; no SHM screenshot guesses, HUD or overlays, or source-file rewriting.

Uniform grid-cell centres cover the entire stage domain, with at most 65,536 pixels.
Actual stage and grid dimensions, eligible/sample counts and proxy quality travel
with the result. Sampling is an estimate; bins are not scaled up to claim full-image
counts. Gather occurs on the source device before bounded CPU transfer. No full
image or view is retained by a tap.

RGB axes are display-encoded [0,1]. Y axis is linear relative luminance with precise
sRGB/D65 Y coefficients (the luminance-curve convention). Each histogram excludes
out-of-range samples from endpoint bins and reports them separately. A nonfinite
RGB triplet is excluded from every channel and counted once. A populated endpoint
bin is not by itself evidence of earlier clipping.

Mean RGB is the arithmetic mean of encoded values, not linear-light mean. Lab is
computed from that mean, not the mean of pixel Lab values. Lab uses the existing
quality-reference's rounded XYZ matrix and D65 whitepoint; it is not ICC Lab D50.
Extended signed sRGB transfer is used for diagnostic out-of-range values; nothing
is silently clamped to make the statistic appear in gamut.

## Request/lifecycle contract

LCS1 binary input: 4-byte magic, little-endian u32 sample count, count RGB f32 LE
triplets. Count 1–65,536; reject wrong exact length, truncation and oversize input.
No network or model dependencies. Packaged helper is built from the same checkout.

Native-generated monotonic tickets bind request/document/stage/revision. Old replies
cannot repopulate a slot after edit invalidation; accepted results require the
expected coherent host document revision. UI requires exact identities and hides
old statistics immediately on edit intent or document/revision change.

Analysis is explicit-refresh, not an automatic extra render on every status poll.
A request may run the full existing proxy pipeline before bounded gathering, so the
sample cap is NOT a bound on full renderer memory or latency. It never packs or
publishes a frame, changes recipe/history, or cancels inspection. Requests defer
while inspection preparation/snapshot/worker/result leases, export or benchmarks
own resources. Rust helper timeout is 5 seconds; pipeline execution is synchronous
and is not claimed to be preemptively cancellable. Live cached capture and full-source
analysis remain follow-up work, not silently removed requirements.

## Primary references

- [GIMP Levels](https://docs.gimp.org/3.0/en/gimp-tool-levels.html): histogram and
  channel/input/output interpretation; sampling and TRC are distinct controls.
- [GIMP Curves](https://docs.gimp.org/3.0/en/gimp-tool-curves.html): input histogram
  belongs to the selected module/channel, not an unlabeled final screenshot.
- [darktable scopes](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/scopes/):
  preview-derived scopes and channel/log-count-axis distinctions.
- [W3C conversion code](https://www.w3.org/TR/css-color-4/#color-conversion-code):
  signed sRGB transfer and explicit whitepoint/domain handling.

Tests cover count conservation, nonfinite values, binary limits, reference Lab,
spatial budgets, tap pixel/frame invariance, read-only inspection coexistence and
host/UI late-result rejection. Basic checks passed; see `docs/development/color-scopes-verification-2026-10-21.md`
for exact candidate, logs, reporting correction and remaining acceptance.
