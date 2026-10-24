# Bilateral facial contour: source-only implementation, UNRUN

Baseline `ad1fc32c86a56700fe0ae7b7c011062059dbb84d`.

## Exact handbook scope and current primary evidence

- `LNX-REF-PC-32466-C-94bf91612d`: temple contour. Positive expands outward;
  negative contracts inward.
- `LNX-REF-PC-32466-C-d24d97d234`: cheekbone contour. Positive narrows inward;
  negative expands outward. This sign is deliberately different.
- `LNX-REF-PC-32466-C-3bc7e245b7`: jaw contour. Positive expands outward;
  negative contracts inward.

All three support linked or independent left/right adjustment. Left/right in this
implementation means the subject's sides, not the viewer's. The frozen mapping
has no dedicated acceptance cases for these rows, only related module case
PORTRAIT-007. That module association is not evidence of feature acceptance.

The frozen guide URL is `https://www.pixcakeai.com/guide/32466`; direct retrieval
was unavailable during this work. The current official desktop
[face reshaping guide](https://wiki.pixcakeai.com/guide/9405.html), read 2026-10-24,
explicitly confirms all three directions and independent-side unlock behavior.
The [official iPad guide](https://www.pixcakeai.com/guide/32509) corroborates the
same controls but is not silently substituted for the desktop requirement.
No range, radius, deformation coefficient or proprietary solver equivalence is
inferred from these descriptions.

## Material gap, not a renamed filter

Existing generic slim-face controls affect a different wider region; eyebrow,
nose, eye and mouth geometry each have their own separate consumers. None
constituted three independently linked bilateral contour controls. This new
`lnx.face_contour.v1` stores only versioned temple/cheekbone/jaw left/right values
and link flags. Each amount is in [-1,1], an original product range. Relinking
changes only the link flag; the next explicit linked edit sets both values in
one canonical transaction. It does not silently collapse unequal existing values.

Shared write targets with no explicit link choice must choose linked/unlinked
before changing numeric values, rather than borrowing one selected face's
inherited mode for other faces. Reset writes six neutral amounts atomically and
retains every link flag. Readback and target provenance are distinct.

## Geometry, method and licenses

The new operator uses the verified 36-node MediaPipe face oval from the
[official v1.1.1 topology](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py).
These are factual topology indices, not an upstream contour-editing algorithm.
They provide measured sample locations, not proof of hidden anatomy, real bone
position, complete occlusion or instance segmentation.

Original Rust generates bounded head-lateral forward control displacements.
The existing project-normalized thin-plate spline machinery then solves the
source pullback at displaced control points, with pinned identity features,
compact support, actual-control error checks and fold-risk refusal. The
[Bookstein primary TPS paper](https://user.engineering.uiowa.edu/~aip/papers/bookstein-89.pdf)
and [official SciPy RBF documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.RBFInterpolator.html)
provide mathematical context: thin-plate radial kernels require their affine
polynomial constraints and well-posed control geometry. No paper prose, SciPy
implementation, external solver, model or weights were copied. Project TPS reuse
and all new code remain GPL-3.0-or-later. The staged package includes core source,
header and project license; building was not performed.

The controls alter only existing two-dimensional image coordinates. They do not
reconstruct 3D bones, hidden skin or missing image content. Original and derived
sources use their authentic measured analysis, never a spoofed original digest.
Known-occluder and interior semantic/photometric checks remain conservative
heuristics. A contour change necessarily transports a small adjacent background
halo; this is not a segmented foreground-only composite or perfect background
preservation. Complete compact influence windows intersecting another retained
face box are refused, including disabled/manual/unresolved neighbors. Undetected
people or objects remain an explicit detection limitation.

## Single canonical owner and sampler

The four legacy `A.GEOMETRY` slots and their migration/mirror/export contracts
remain unchanged. A separate contour operation is registered and its active
pullback is appended after those fields. The existing `FaceGeometry.evaluate`
composes actual off-grid mappings and the existing final joint-map check refuses
fold risk before one RGB/mask sampler. A contour-specific wrapper additionally
checks every actually evaluated nonzero increment against retained foreign boxes
at output, pre-contour and final source-sampling coordinates, including bilinear
footprints. This catches prior geometry moving a query into the contour support;
unsafe compositions refuse rather than silently masking or attenuating intent.
Out-of-image contour samples also refuse. This does not certify unchanged legacy
prefix effects or prove unsampled continuous injectivity. Mouth teeth-cavity protection now explicitly
uses legacy slot 3, not the formerly last field. It cannot mistake contour for
mouth support. Contour facts have their own key, not a legacy field label.

Canonical people state, source bindings, receipts, undo/reopen, frozen export and
confirmed/explicit transfer remain the only owners. Scalar presets carry only
bilateral values and link intent. Every target rebuilds controls and evidence at
its actual source/render grid. No source landmarks, support mask, field or cached
pixels are transferable. Generic derived preset guards remain unchanged.

## Separate legacy audit finding, not silently repaired

The existing `ops/deform.py` slim-face `FACE_OVAL_LEFT/RIGHT` constants were not
reused. Its left chain runs upward despite its direction comment; its right
chain contains 314/405/308, which the official topology places on lips rather
than the oval. This is a pre-existing, separate slim-face audit issue. This slice
does not alter that legacy behavior, its prior fixtures or old acceptance claims.
It needs an independently scoped correction with genuine regression photographs.

## Acceptance and remaining limits

All numerical, native ABI, build, typecheck, UI, actual-source export, performance
and photographic acceptance remains UNRUN. Static source/AST/JSON/hash inspection
is not proof of execution. Later validation must measure forward directions,
linked/independent sides, landmarks after rendering, identity-feature stability,
neighbor/image-border protection, actual inverse-control error, fold behavior,
original/derived/PNG16 preview/export, undo/reopen and per-target transfer.

Frontal/mild-yaw measured visible contours only. Occluded, clipped, low-resolution,
degenerate or unsupported evidence refuses rather than approximating from a face
template. No whole facial-reshaping, AI face-smoothing, jaw lighting correction,
body-shape, HDR or alpha acceptance is implied. Numerical thresholds are original
conservative policies, not validated perceptual or anatomical truth.

## Source policy bounds and integration map

The new operator requires measured width at least 64 pixels, height at least 72,
iris span at least 24, both visible eye spans at least 10, and a conservative
bilateral eye-span ratio. Inner contour strips require named face-skin weight
at least .45, retained exclusion below .15, at least 88% supported samples, and
usable nonclipped RGB with nontrivial local variation. These rules can reject
smooth, low-contrast skin and are not validated visibility probabilities.
Protected boxes follow the durable 4096-face catalog bound. Unsupported frames/geometry refuse;
no template, proxy contour field, hidden-side reconstruction or radius fallback.

The Rust boundary accepts at most 256 controls with fixed 4 KiB transactional
scratch. Each regional peak uses an original .035 face-width amplitude and the
absolute contribution sum cannot exceed .08 width. The host's TPS is evaluated
in bounded bands; its probe and final pixel-grid Jacobian refusals are not a
proof of continuous invertibility between samples. Full-source memory, latency
and cancellation behavior remain unmeasured.

- `face_contour_state.py`, `face_contour_native.py`, `core/face_contour`: strict
  recipe, checked native displacement API, dedicated readiness and offline build.
- `face_contour_geometry.py`, `face_contour_field.py`, `face_contour_runtime.py`:
  verified oval, measured evidence, own identity protection and compact pullback.
- `face_contour_people.py`, `people_render_runtime.py`, `people_algorithms.py`,
  `people_geometry.py`: canonical registration, source/neighbor proof, composed
  coordinate protection, separate facts and unchanged one-sampler ownership.
- `creative_derived_effects.py`: exact new operation admission to the real derived
  source path, not reuse of original analysis or generic guard removal.
- `face_contour_scope.py`, `people_scope.py`, `scope.py`, `workflow_ports.py`:
  bilateral recipe-only preset replay and strict target rendering. Ephemeral
  owner metadata reuses the existing endpoint proof's document/epoch/scope/source
  identity; transaction revisions remain with the existing controller, avoiding
  a second history owner or broken monotonic rollback.
- `ui/src/faceContour`, the three RetouchPanel leaves and capability/labels:
  authoritative selected-face readback, explicit shared write mode and atomic
  existing-owner patches, including zero recovery.
- New authored native, geometry, integration, scope and UI fixtures are all
  UNRUN. Explicit doubles test transport and composition contracts, not native
  numerical behavior or genuine photograph quality.
