# Measured same-photo reference proposal

Status: **AUTHORED / UNRUN**, 2026-10-25. This is an isolated source-only proposal
API plus unexecuted fixtures. The subsequent current-photo host/UI integration
is recorded in [CHOICE-INTEGRATION.md](CHOICE-INTEGRATION.md). No
product import, test collection/execution, build, typecheck, model inference,
installation, download, hardware probe or photographic acceptance ran here.

## Public requirement and non-equivalence

The preserved external control is `control:PC-32465:19`, **AI多人肤色统一**.
The [official skin guide](https://www.pixcakeai.com/guide/32465), updated
2026-05-26, and the [official wiki](https://wiki.pixcakeai.com/guide/9404.html),
dated 2026-05-18, both describe a same-photo brightest-face reference, adjustment
of other people's face/body tone **and brightness**, and exclusion of the
reference face itself. Both were read directly for this change. Neither page
specifies a luminance statistic, treatment of clipped highlights, uncertainty
rule or face-ranking implementation. No original hashed LNX mapping is guessed.

This independently authored module proposes the brightest **measurable enabled
retained face** under the declared statistic below. It never claims to have
found every face in the photograph, recovered intrinsic complexion, matched the
external product's metric, or implemented its complete face/body feature. The
existing correction family remains `lnx.skin_reference_match.v1`, and the
separate body-to-own-face chroma operation is unchanged.

## API and authority boundary

`engine/src/lumaretouch_engine/skin_reference_choice.py` exposes:

```python
propose(state, asset_sha256, full_source, analyses, *, byte_budget,
        manual_reference=None, cancelled=lambda: False) -> dict
```

- `full_source` must be the in-process result of
  `portrait_fit_source.capture/capture_original` for this exact original or
  canonical creative source, before repairs and portrait operations. Exact
  `FullSource` type, binding, precision, immutable bytes, pixel hash, float32 SDR
  validation and full dimensions are rechecked through the existing runtime.
  A caller constructing that dataclass is not an alternative authentication
  route. There is no caller RGB/score/"verified" boolean API or proxy RGB fit.
- The candidate set is derived from the complete current graph, not from the
  keys the caller happens to supply. All enabled retained same-source faces are
  candidates. Missing analysis remains visible and blocks automatic selection.
  Disabled retained faces are disclosed, not ranked, and remain protective
  vetoes. At most 64 retained same-source faces are admitted; no truncation.
- `analyses` must use exact current stable face-instance IDs, source, analysis
  revision, verified MediaPipe model evidence, the actual float32 478-point
  array and matching digest, named `face_skin` observation, and exact-grid known
  occluder field. Merged/body skin, fabricated rectangles, another face's
  geometry, unresolved evidence and caller scores are never replacements.
- A successful result is JSON metadata only. It includes each measurement or
  explicit unavailable/disabled status; source and support hashes; rank order;
  automatic blockers and near-ties; optional manual choice; mandatory review
  and reference-exclusion flags. It contains no RGB, masks, landmarks, reusable
  fit, effect record, consent token or scalar recipe. Its content hash detects
  metadata changes but is **not** authority to render or confirm anything.
- Source-proof fields are `source` (asset hash and original dimensions),
  `source_pixels_sha256`, `source_kind`, `source_bits`, `source_encoding`,
  `source_stage`, `state_revision`, and `association_revision`. Each measured
  row additionally carries its exact `face_ref`, full retained `evidence`,
  `landmark_digest`, `face_skin_observation`, `source_window` and
  `support_sha256`. A future host must additionally fence its document, repair
  and complete analysis snapshot; these scalar fields are not substitutes.
- The function has no support-bank or recipe-write API. It never calls native
  apply, support retain, host confirm or any UI command. Returning a face does
  not alter the photo, the graph, an existing selected reference or its review.

The host must capture/fence the source, graph, analysis generation, document and
repair revisions around a future call, discard stale results, and use a returned
face only to prefill the existing explicit selection. Users must still be able
to override it. The existing source-overlay, exact target ownership and complete
before/after review flow remains mandatory; the selected reference must still be
excluded from all target application. This module adds no body permission.

## Independent supports, same exclusions

For each candidate the module snapshots its own validated observations and
projects only `face_skin` and `excluded` semantic fields to the source grid using
the existing runtime helper. Original RGB is never resized, downsampled, tiled
for fitting, replaced with current edited pixels or paired to another face.
Producer dimensions remain unchanged in the returned observation: interpolation
does not claim fresh full-resolution inference.

It reuses the existing support helpers without changing them:

1. Intersect that candidate's actual face-skin weight with its independently
   measured face oval.
2. Exclude eyes, lips and brows using its own actual anatomy and pixel-footprint
   protection.
3. Veto known occluder weights greater than 0.1, exactly as reviewed support does.
4. Apply the same outer-oval inset and feathering.
5. Veto every other retained same-source face box, including disabled/unresolved
   faces. Every other independently validated actual oval is an additional
   veto, so narrow foreign boxes cannot override available measured anatomy.

Foreign masks are never used to fill another face's support. Foreign geometry
only subtracts permission; it never supplies ownership or a candidate's missing
anatomy. Unknown occlusion, detector omissions and semantic-model errors remain
visual-review limitations. Geometric support alone is not photometric evidence.

## Measured statistic, not confidence ranking

No new numerical solver or native ABI was introduced. Each candidate's complete
source support window is passed as **both** populations to the existing original
Rust fitter, with correction limits `(0, 0)`. The ABI explicitly permits
read-only input-input overlap and still requires real evidence with zero limits.
The Python bridge makes its existing independent snapshots. Self-fitting
duplicates statistical work but avoids a second approximate Python algorithm.

After the native result passes `MeasuredFit.checked`, the proposal requires equal
source/target shapes, counts, weights, effective counts, centres and MADs, exact
zero transform/raw shift/bound flags, and a centre inside the native reliable
luminance interval. Inconsistent results cannot become rankings. The fit itself
is discarded after scalar facts are extracted.

The rank score is diagnostic index 7: the final robust centre of **natural-log
linear-sRGB luminance**, descending. Its exponential is also reported as linear
luminance. The existing core decodes working-sRGB, uses Y coefficients
`[0.2126, 0.7152, 0.0722]`, suppresses unstable dark/near-clipped observations,
estimates streaming weighted medians and initial MADs, applies one bounded
bisquare reweight, and rechecks its evidence gates. See [NUMERICS](NUMERICS.md)
for the exact thresholds, 2048-bin/two-level approximation and limitations.

Counts, effective samples, retained weight and initial luminance MAD are
diagnostic facts only. They are not brightness scores, probabilities, confidence
intervals, beauty judgments or tie-breakers. No age, sex, ethnicity, identity,
demographic label or inferred complexion enters the measurement or ordering.
The result is observed source luminance under the existing lighting and colour
transform, not an illumination-invariant physical skin measurement.

## Refusal, ambiguity and manual override

Automatic selection requires at least two enabled retained faces, a reliable
measurement for **every** enabled candidate, no reported detector-limit hit, and
a separated top measurement. The graph does not assert a complete face census;
the returned `census_complete` is always false, even after a successful proposal.
An absent detection-run record cannot silently become a complete-census claim.

The local separation rule is a gap greater than `ln(1.02)` between the two top
log-luminance centres, equivalent to over 2% relative linear Y. A smaller/equal
gap exposes all candidates inside that top band and leaves automatic selection
empty. This is an explicit conservative engineering tie band requiring future
photo validation, **not** a perceptual JND, a statistical confidence bound, a
published calibration or the proprietary metric. Face IDs make the displayed
order deterministic but cannot break a selection tie.

No unreliable, clipped, missing or malformed face is silently removed to let a
remaining darker face win. Candidate-specific geometry/native evidence refusals
are listed and block automatic choice. Missing/incompatible native capability,
native resource failure and cancellation propagate without a partial proposal or
fallback solver. No source validation failure is reduced to candidate absence.

An explicit current `manual_reference` can select a successfully measured enabled
face even when automatic choice is blocked by a tie, another unavailable face or
the detector limit. Automatic findings remain visible and are not relabeled as
successful brightest selection. An unavailable, disabled, stale or foreign
manual face is rejected, never replaced. Manual selection also remains only a
proposal and grants no consent or application permission.

## Memory and validation boundaries

Admission includes full captured RGB, supplied ndarray backing storage (not just
small strided-view sizes), analysis snapshots, graph/metadata allowance, full-grid
projection/validation scratch, largest anatomical ROI work and native self-fit
snapshots. Faces are processed serially; no collection of raster supports or
native fits is returned. The caller subtracts unrelated render allocations first.
The existing live CPU-budget check remains fail-closed; estimates are not an OOM
guarantee or benchmark.

Native fit's combined 32-million-pixel ceiling counts a self-ROI twice, so an
unusually large single face ROI can refuse even within the full-source ceiling.
No reduced-resolution or tiled-fitting fallback hides that limitation. Native
statistical work is doubled per face; latency has not been measured.

`engine/tests/test_skin_reference_choice_unrun.py` authors source-binding,
same-exclusion comparison, independent-owner evidence, missing-candidate,
confidence-vs-brightness, exact/near-tie, manual-override, detector-cap, protected
disabled-face, semantic-projection, purity, memory, cancellation and native-failure
fixtures. Protocol doubles test routing only. Separate real-core fixtures cover
constant-source luminance, clipped/dark refusal and a small specular patch; all
remain unrun. No passing test, integrated product behavior or photographic
quality claim follows from source inspection or syntax parsing.

## Primary methods and licences

Reviewed 2026-10-25. These references informed the design only; no external source
code, package, asset, model, executable or example was incorporated.

- [Astropy's official biweight-location documentation](https://docs.astropy.org/en/stable/api/astropy.stats.biweight_location.html)
  describes the mature median/MAD-based bisquare robust-location family and
  cites Beers, Flynn and Gebhardt (1990) and NIST. Its
  [official licence](https://github.com/astropy/astropy/blob/main/LICENSE.rst)
  is BSD-3-Clause. This module does **not** call/copy Astropy or implement its
  biweight-location estimator. The existing core's weighted median after one
  bounded reweight is different; Astropy's formula/tuning constants are not
  presented as validating this implementation or its tie band.
- [darktable's official colour-mapping manual](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/color-mapping/)
  separates acquisition of source and target colour statistics. Its
  [official implementation and licence header](https://github.com/darktable-org/darktable/blob/master/src/iop/colormapping.c)
  identify GPL-3.0-or-later. It uses Lab colour clusters/histogram mapping, not
  this source-only brightest-face statistic. No code was copied and no
  algorithmic or performance equivalence is claimed.
- The reused original `core/skin_reference_match` and these new Python sources
  are GPL-3.0-or-later under the repository [LICENSE](../../LICENSE). Existing
  anatomy/support/runtime helpers are reused in place. No new native
  dependency, model, notice obligation from incorporated third-party code,
  numeric-core edit or shared ABI change is introduced.
