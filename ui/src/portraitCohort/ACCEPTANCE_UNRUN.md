# Persistent named face-style cohort: implementation evidence, not acceptance

Source authored only. No tests, TypeScript typecheck, build, product import, inference,
model download, UI launch, rendered-photo inspection, or packaging validation was run.
Synthetic DTOs and one-pixel PNGs in the authored tests are not photographic acceptance.

Implemented source contracts:
- Named create/patch uses explicit v1 recipe plus exact 30 leaves and sorted ten-operation scope.
  The engine supplies values; no source-face parameter donor or style badge is persisted.
- Unlink has empty selection and no recipe. Generic later patches/unlink with all 30 managed
  intent keys still require every member's real images, including the source. Coefficients
  need not match a named recipe; the UI does not infer one.
- Python's cohort digest is opaque. Every member must use the same frozen digest and its own
  document, revision and source proof. Paged image reads verify coordinates, compact metadata,
  PNG bytes/digest, decode dimensions, both loads and a separate explicit checkbox.
- Commit carries exact frozen scope and ordered source-first ACK. Missing/changed scope, cohort,
  image pairs, members, source outcome, revisions or terminal state cannot release an uncertain write.
  Persistent canonical no-op remains an explicit preflight no-write rejection, not a null batch.
- Existing human face overrides stay higher priority than shared person intent. Whole-image
  unchanged candidates are disclosed and still reviewed. Collarbone coverage and whole-member
  image approval remain independently mandatory when both cohort gates apply.
- Ordinary one-shot named face-style transport/recipe digest and legacy scalar behavior are retained.

Still unverified: actual browser display/accessibility, image lifecycle under real navigation,
backend/native/UI integration, undo/redo against real files, all platform builds, and real portrait
quality across every named style, amount (including zero), explicit-override and unlink scenario.
