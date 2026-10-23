# PC-32475 background-colour spill removal: source implementation, not acceptance

Baseline: `c72de4fbb2a5cadb5bd41c936b596d37555c76a8`.

## Exact requirement and non-equivalence

- `LNX-REF-PC-32475-C-e999ab085a`: 祛背景色反光.
- `LNX-REF-PC-32475-C-4bc238dfa1`: 祛背景色反光/手动涂抹画笔.

The supplied manual lines 575–579 and mapping entries at lines 5685–5708,
checked against the [official guide](https://www.pixcakeai.com/guide/32475) on
2026-10-23, concern reflected background colour on faces, clothing, limbs and
hair in solid-background photographs. The guide also describes manual
erase/restore coverage. It does not disclose the algorithm or numerical defaults.
The local 0–100 scale and default 50 are implementation choices, not official
values. Source wiring must not be counted as photographic acceptance.

This is not the background opacity slider, matte erosion, a recovery brush,
global desaturation or lens chromatic-aberration correction. The original
subject alpha is unchanged. Separate source-owned manual coverage restricts a
colour correction and never becomes evidence that a pixel is contaminated.

## Technique and attribution

The mathematical reference is Germer et al.,
[Fast Multi-Level Foreground Estimation](https://arxiv.org/abs/2006.14970):
fixed-alpha foreground/background colour estimation with spatial regularization.
The compositing equation is `I = alpha F + (1-alpha) B`. Both colours need
independent spatial evidence; alpha alone is insufficient. At alpha=1 this
equation gives F=I and says nothing about reflected illumination. Accordingly,
the opaque near-boundary branch is separately identified as an original,
conservative chromatic-excess heuristic, not a conclusion of the matting solver.

Mature implementation references, read only:

- [PyMatting foreground API](https://pymatting.github.io/foreground.html) and
  [MIT license](https://github.com/pymatting/pymatting/blob/master/LICENSE.md),
  copyright 2020 PyMatting. This establishes a real colour-estimation technique,
  not compatibility with its numerical output.
- [Natron Despill documentation](https://natron.readthedocs.io/en/rb-2.5/plugins/net.sf.openfx.Despill.html)
  and [exact source header](https://github.com/NatronGitHub/openfx-misc/blob/master/Despill/Despill.cpp),
  GPL-2.0-or-later. Its green/blue excess suppression is distinct from alpha
  generation and is not a substitute for general foreground estimation.

No paper code, PyMatting code, Natron code, model, weight or image asset was
downloaded or copied. The Rust implementation is original project code under
the repository GPL-3.0-or-later license. No third-party model compatibility is
claimed. Detailed numerical contracts belong in the kernel documentation.

## Ownership and workflow

The existing ID-background pipeline remains the single compositor and history
owner. Legacy ID recipe v1 is preserved exactly, including its existing hash in
derived-source evidence. A spill edit explicitly creates ID recipe v2 with a
versioned nested `spill` recipe. Old projects do not suddenly gain an active
effect, and old dormant hashes are not rewritten just to introduce a default.

The immutable effective source supplies foreground/background estimates. A
returned creative composite supplies its own canonical RGB, not the physical
original file under a new identity. Original file bytes remain provenance.
Current edited RGB receives the estimated correction before the ID composite;
earlier edits are not replaced with cached original pixels. The existing ID
recovery target wraps this complete stage, so it also attenuates spill correction
without adding a second history or recovery owner.

Manual coverage snapshots only actual geometric source-mask objects (brush,
linear, radial), including their retained composition order. It rejects semantic,
prompted, full-image and foreign-source objects. Full export replays these vectors
at the exact source dimensions. The existing coverage raster is quantized to
8-bit coverage; this is not a claim of learned or physical hair alpha.
The user can retain the current snapshot, explicitly choose automatic coverage,
or review a new selection. Manual coverage gates automatic confidence, so an
erase is an exclusion and a restore cannot force uncertain pixels to change.
The panel can retain snapshots created in the existing source-mask editor.
A subsequent [direct source-owned erase/restore slice](PAINT-README.md) adds its
own raw-source canvas and reviewed brush drafts. Its interaction and all
photographic acceptance remain UNRUN; this is not full feature acceptance.

Preview is not a hidden live apply/undo: it renders complete before and candidate
states independently through the real full-source exporter. Only after rendering
are float results converted into bounded display PNGs. The review binds both
source identities, complete recipe fingerprints, people ownership, document and
revision. Native and UI check the exact loaded PNG identities; explicit visual
confirmation authorizes one token, consumed before mutation. A newer document,
source, recipe or review invalidates that token. Display images and numerical
fields never enter history/project snapshots.

Apply uses one document fence, one retained receipt and one history transaction.
The installed complete state is checked against the reviewed candidate, with only
the transaction's intentional revision advance allowed. Rollback restores both
recipe and history ledger. Single receipts are admitted against the native 4 MiB
cap before mutation, with a final exact-size check before releasing rollback.
Only the newest preview PNG pair is retained; a 16 MiB receipt budget preserves
mutation receipts and rejects new work rather than evicting uncertain operations.
Uncertain outcomes query the original receipt rather
than automatically resending an edit. Failed rollback remains explicitly blocked.

## Presets, batch and persistence

Existing ID scope transfers only enabled/strength spill parameters. Neither
estimated pixels, source alpha nor manual coverage is copied to another image.
The target retains its own reviewed foreground support and its own manual spill
coverage, and estimates its own colour fields during rendering. A v1 preset
disables the new effect while preserving the target's dormant coverage, so old
presets do not unexpectedly acquire spill correction. Target ownership is checked
even for dormant intent. Existing project/package/history asset handling retains
vector recipes and original encoded assets, not full RGBA fields per undo step.

The additional narrow `lnx.spill_removal.v1` scope transfers only those two
scalars into an already-active, independently reviewed ID target. This allows
original and opaque-SDR returned targets without admitting the still-fenced
whole-ID-background derived transfer. A single transfer cannot contain both
whole-ID and spill-only scopes because both would own these scalars. Scope undo
freezes all ID dependencies but restores only the target's spill subrecipe/schema.
Preset apply requires its frozen preflight, and batch requires per-target frozen
preflight and source proofs. These transfer reviews concern parameters and
ownership, not rendered spill previews for every target. Parked target numerical
fields are recalculated from their own source and matte when activated/exported;
no claim is made that preflight rendered or visually approved every parked photo.

## Explicit limitations and UNRUN acceptance

- This is a bounded partial implementation, not proof of the complete official
  reflected-spill behavior. Deep opaque contamination, contaminated interior
  samples, tiny structures without independent colour support and real foreground
  colours matching the backdrop remain ambiguous. Such cases must not be silently
  represented as successful recovery.
- A manually feathered selection is not necessarily the physical mixing alpha.
  Low reconstruction residual alone does not prove correct recovered colours.
- Strong nonlinear upstream recolouring may make a source-estimated direction
  inappropriate even when applying an additive correction preserves the edit
  stack structurally. Actual before/after review is mandatory for direct edits.
- Original/derived source alpha/HDR admission stays explicit. No hidden flattening,
  clipping or proxy-mask promotion is introduced. Current out-of-SDR edited pixels
  are left unchanged by spill correction rather than clipped into its domain.
- Full-source computation and tile consumption are distinct from display PNG
  reduction. Memory/cancellation refusal must remain visible, not silently reduce
  source quality. Numerical budgets are not measured performance guarantees.
- Joint F/B guidance is limited to a longest side of 1024 and at most 1,048,576
  pixels. Full-source per-pixel refinement and confidence use actual source RGB
  and alpha. This is coarse-guided colour estimation, not native-full-resolution
  F/B recovery. Standalone kernel admission is `64*N + 64 MiB`, at most 2 GiB
  and 32MP, with other pipeline allocations admitted separately. A 24MP kernel
  estimate is 1,603,108,864 bytes, not a measured total-process working set.
- Fixtures are authored but **UNRUN**. No product imports, numerical execution,
  inference, build, compiler/typecheck, tests or photographic evaluation ran in
  this source-only slice. Neutrality, colour accuracy, edge/hair preservation,
  RGB16 precision, preview/export/tile parity, history/reopen, native UI review,
  memory and performance all still require local QA.

## Integration map

- `spill_removal_state.py`, `spill_removal_coverage.py`, `id_background_state.py`:
  exact durable recipes, legacy preservation, source-owned manual vectors.
- `core/spill_removal`, `spill_removal_native.py`: original numerical kernel and
  explicit dependency/encoding contract, no runtime build or substitute backend.
- `spill_removal_render.py`, `id_background_runtime.py`, `id_background_stage.py`,
  `id_background_export.py`: full-source fields, aligned current-RGB consumer,
  source proof, budgets and full export/tile lifecycle.
- `reference_color_provenance.py`: corrected foreground is not misreported as
  untouched original-colour support.
- `spill_removal_paint_source.py`, `spill_removal_paint_vectors.py`,
  `full_source_working.py`: direct source-normalized brush drafts, genuine-source
  locator and shared RGB16 ICC/alpha/bit-depth boundary.
- `spill_removal_review.py`, `spill_removal_controller.py`, existing ID dispatcher
  and derived host: actual before/after review, one-use commit and unified history.
- `ui/src/spillRemoval`, `ui/src/idBackground`, native ID request/receipt module:
  separate spill draft, coverage selection, reviewed PNGs and no blind retry.
- Existing `id_background_scope.py` and recursive project validator: parameter-only
  per-target inheritance and strict dormant/history persistence.
- `spill_removal_scope.py`, scope registry, frozen preset/batch planners and
  group history: narrow original/derived scalar transport with target-owned
  colour recomputation. The broader ID transfer guard remains intact.

Consult `FREEZE.json` for the initial payload and `PAINT-FREEZE.json` for the
direct-painting follow-on. They are source manifests, not functional-acceptance
certificates.
