# Reviewed body-skin extension: implementation contract, UNRUN

Baseline: `b57d69455af3eec7b39bf8bae8e104a71f424480`.

## Requirement boundaries

This extends the existing `LNX-REF-PC-32465-C-f0ba809461` (肤色色温) and
`LNX-REF-PC-32465-C-0146f740bd` (肤色色调), not a new feature count. The
[official guide](https://www.pixcakeai.com/guide/32465) establishes their signed
cool/warm and green/magenta semantics. Both remain partial until runtime and
photographic acceptance. Whole-body whitening, rosy skin, skin palettes,
translucence, skin unification and blemish removal are separate unfinished
requirements. Manual-assisted coverage is not automatic full-body ownership.

## Primary model and method evidence

Checked 2026-10-24:

- [Google Image Segmenter documentation](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter)
  describes category/confidence masks. The existing six-class portrait producer's
  body-skin plane describes a semantic class across the photograph, not the
  identity of a particular person.
- [Google Pose Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)
  describes 33 body landmarks and optional pose segmentation. Our existing
  acquired pose evidence does not supply body-skin instance segmentation, and
  this extension must not invent it from landmarks or a face box.
- The original Rust colour solver and its Lab/gamut research remain unchanged;
  see [the existing implementation contract](IMPLEMENTATION.md). This extension
  combines measured semantic evidence and explicitly reviewed vector coverage,
  not a new neural skin model or a substitute blur/heal algorithm.

No model/code weights were downloaded, installed, executed or relicensed.
Existing producer code/model hashes and licence gates remain authoritative.
New code is original GPL-3.0-or-later; no external implementation was copied.

## Ownership design

The sole portable colour recipe remains `lnx.skin_colour.v1` with temperature
and tint. A separately stored, nonportable `skin_colour_body_visibility`
descriptor opts an exact FaceRef into reviewed body coverage. Absence preserves
old face-only behaviour. It is not a body-deformation operation or a second
colour/history owner.

The immutable support record pins the actual BodyRef and pose point digest,
source dimensions/orientation/digest, confirmed anonymous person/face/body
association, semantic observation/model evidence and manual normalized brush
vectors. The source observation includes the face-analysis detector hash as
transport provenance, not a claim that it detects body ownership. A stale
attached active review must refuse, never silently revert to face-only.

Positive body coverage requires the real body-skin class intersected with the
user-reviewed visible region. Face evidence is only a protective exclusion for
this body attachment, not extrapolated positive body skin. Competing retained
owners cannot be resolved by arbitrary face ordering. Unknown or unreviewed
people/occluders remain a manual-review limitation. A user can make a mistaken
ownership selection; neither an explicit checkbox nor model confidence proves
that a pixel belongs to that person.

## Rendering, persistence and review requirements

Source-normalized brush geometry must be rasterized at the requested source
dimensions, using edge-normalized pixel centres, not stretched preview masks.
Actual face/body colour coverage combines once before the shared native solve,
then uses the existing single joint body/face geometric warp. Preview and full
export use the actual effective original or immutable returned source and its
own evidence. Producer observations survive resampling without claiming newly
inferred full-resolution edge precision.

Reference, candidate preview and confirmation are distinct. Before/after
images must come from real canonical rendering with private staged support,
not a live state swap or tinted UI overlay. Confirmation pins document, source,
people/body graphs, analysis, scalar recipe and vector content. Only confirmed
support enters the existing graph transaction and append-only asset bank.
Detachment removes the current reference, not immutable bytes needed for undo.
Historical assets must remain structurally valid without binding them to a
different present-day person's body.
Candidate review requires a nonzero current temperature or tint so it can show
an actual requested colour effect. A stale active attachment can first be
detached, then reviewed again; it is not silently suppressed just to manufacture
a before image. Remaining active effects still have to prepare successfully.

Presets and cross-image transfer carry scalars only. Every target retains or
recalculates its own coverage from its own evidence and reviewed attachment.
Face-only and face-plus-reviewed-body outcomes must be disclosed separately.
No source BodyRef, brush vectors, face landmarks or semantic arrays transfer.
The new frozen extent disclosure covers `confirmed_person_only` and
`explicit_face_map` transfers. The separate persistent cross-owner association
review DTO is not extended here: its association revision changes invalidate
active attached body reviews and preparation refuses rather than silently
rebinding them. Its complete reviewed-body inheritance UX remains unfinished.
Single-image scalar preset capture exposes local coverage facts, but its generic
preset UI has not gained the new cross-image extent review. Existing derived
generic preset refusals remain; supported explicit face transfer uses the actual
target-specific renderer and new disclosure.

## Source integration map

- `body_skin_semantics.py`: optional real body-skin plane and JSON observation;
  binding, retained-analysis restore and snapshot resampling preserve source and
  producer identity. Legacy absence remains absence, not fabricated zero support.
- `skin_colour_body_support.py`: immutable record validation, exact current
  ownership resolution, manual/semantic coverage intersection, face-box vetoes,
  competing-review overlap refusal and scope-aware historical asset validation.
- `people_support_assets.py` / `people_project.py`: existing append-only storage,
  content digests and active/dormant/private/history persistence. Nested private
  document banks are resolved in their own scope rather than the project root.
- `skin_colour_body_host.py` / `skin_colour_body_actions.py`: reference,
  private candidate, confirmation and detach; existing people receipts/history
  remain authoritative. Review JSON is limited to 192 KiB without raising the
  native 256 KiB envelope limit or silently dropping geometry points.
- `full_candidate_render.py`: optional private staged people/support context,
  append-only asset checks and original-context identity. Unrelated ownership
  stores cannot be replaced, and the default render identity schema is unchanged.
- `people_owned_inputs.py`, `people_engine_runtime.py`,
  `people_render_runtime.py`, `skin_colour_people.py`: actual target banks and
  source-domain coverage union before one native colour solve/common warp.
- `creative_derived_effects.py` / `creative_derived_makeup.py`: exact support and
  action registration; actual active support ownership is still checked by its
  dedicated consumer, not accepted merely because its name is on an allowlist.
- `skin_colour_transfer_review.py`, scalar capture and existing people batch
  preflight: per-target face-only/reviewed-body/neutral disclosure after real
  candidate preparation. The immutable target support digest is disclosure,
  not a portable mask or permission to bypass target preparation.
- `ui/src/skinColour`: whole-source manual brush canvas, explicit ownership
  confirmations, actual before/after plus coverage overlay, stale-review and
  detach controls. Existing people workflow retains only correlated review
  replies; no second command queue, graph or undo stack is introduced.

Scalar/body-recipe revisions do not themselves invalidate a review. Actual
association changes, source changes and conservative legacy/full history restore
fences can require renewed review. These are explicit refusals rather than silent
rebinding of a historical support to another person. Source overlay PNGs and
comparison PNGs are display-only, not retouch buffers or persisted source assets.

## Acceptance status and explicit limitations

All fixtures are AUTHORED / UNRUN. Static parsing and source checks do not prove
runtime behaviour, performance, numerical accuracy or photographic quality.
No project imports, test runs, compiler/typechecker/build, inference or model
downloads are permitted during this source-development slice.

Existing opaque SDR retouch requirements remain. PNG16 source precision is not
HDR/alpha support. No clipping, implicit RGB8 conversion, guessed segmentation,
synthetic anatomy, or proxy promotion is allowed to claim unsupported coverage.
Manual ownership ambiguity, semantic boundary errors, small/occluded skin,
pose failures and undiscovered people remain real limitations. Full automatic
multi-person skin ownership and whole-family handbook acceptance remain open.
