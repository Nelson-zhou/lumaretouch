# Local XMP parameter adaptation, source implementation v1

Baseline: ba04e314aff6d20cf2edba85d198a77ef03ae27f.
Status: SOURCE IMPLEMENTATION, NOT FUNCTIONAL ACCEPTANCE. Builds, tests, package behavior, real photograph
comparisons and functional acceptance are UNRUN.

Requirement: LNX-REF-WF-158978-398fbf9da9, handbook lines 227–233: local XMP
import alongside proprietary sharing codes. The handbook does not disclose an
XMP compatibility field list. This feature does not implement proprietary codes.

## Honest compatibility boundary

This is an explicit native-parameter adaptation, not Lightroom/Camera Raw process
emulation or an identical-rendering claim. Exact serialized ProcessVersion 11.0
is the only initially observed supported syntax, based on Adobe's own sample.
Camera Raw Version is reported separately. Missing, legacy, other and future
process values remain unsupported, never guessed from numeric ordering.

Selectable groups are Exposure2012 as native absolute EV (−5…5), and the complete
four ToneCurvePV2012 arrays as native master/red/green/blue curves. Every curve
requires 2–64 ordered integer coordinate pairs in 0…255 with explicit x endpoints
0 and 255. Values are normalized by 255, never sorted, clamped, deduplicated,
truncated or silently synthesized. All four arrays are mandatory. The entire
native curve module is replaced, including previous luminance/parametric curves;
this replacement must be disclosed. Native interpolation is the existing Rust
PCHIP compiler in sRGB-display space, not an Adobe spline or processing domain.

No white-balance, profile, look/LUT, calibration, HSL, local correction, mask,
crop, detail, grain, automatic exposure or parametric-curve interpretation is
claimed. Relative native Kelvin/tint is not Adobe absolute RAW white balance.
Unsupported properties remain visible in the compatibility report and preserved
in the exact original bytes. Acknowledgment cannot turn malformed or unsupported
values into compatible operators. Unsupported-only files produce a readable
report, not an empty fake preset.

## Source and lifecycle contract

Inspection is read-only. Import rereads the actual bounded local file and checks
both content and compatibility-report hashes against explicit selected-group
consent. The library stores original XML bytes losslessly with SHA-256, adaptation
version, selection and regenerated report. Ordinary preset atomic writes,
no-overwrite policy, classification and recoverable deletion remain authoritative.
Public catalog/receipt summaries omit raw XML/base64 bytes.

Import does not apply pixels. Applying the stored adaptation requires the actual
current target's before and candidate full-source renders, downsampled only for
review. Both PNGs must pass content/dimension checks before confirmation. Frozen
review binds the immutable original/derived source, document and revision, all
upstream candidate and people-context fingerprints, original XMP hash and report.
Apply uses the existing single preset history transaction and rollback. Source
and installed candidate are checked after rendering, not just before dispatch.
No old source analyses, proxy masks, apply-and-undo previews or silent HDR clipping.

## Integration map and residuals

- `xmp_document.py`: read-only file/namespace/XML/RDF boundary and exact bytes.
- `xmp_adaptation.py`, `preset_xmp_import.py`: report, explicit group consent,
  immutable portable original bytes and deterministic verified native modules.
- `scope.py`, `preset_controller.py`, `custom_lut_scope.py`: schema admission,
  existing atomic library writes/receipts, compact public summaries and a corrupt
  preset's per-file error without hiding the rest of the catalog.
- `xmp_target_review.py`, `full_candidate_render.py`: complete current-target
  before/after renders and compact immutable evidence. Existing fringe coverage
  decode proof is included rather than omitted from the full candidate chain.
- `local_grade_preset_review.py`, `workflow_ports.py`: dedicated XMP review port,
  one-use target token, actual post-replay installed-state check and rollback.
- `ui/src/xmpImport`, `ui/src/presets`, native `xmp_preset_protocol.rs`: bounded
  report and selected-group consent, PNG content/dimension checks, explicit user
  image acknowledgment, native command/receipt validation and same-request query.

Native portable JSON carrying XMP provenance also requires fresh compatibility
inspection before reimport. Raw `.xmp` and these portable packages use the dedicated
XMP entry; ordinary native JSON import keeps its previous behavior. Default
no-overwrite and explicit new-copy remain; no silent replacement of existing IDs.

Source checks establish wiring/identity contracts only, not measured equality
between preview and viewport or photographic equivalence. Candidate previews are
640-pixel display images of full-source renders, not candidate 100% inspection.
The saved result retains the existing original-size inspector and global undo.
Wider unsupported returned-source alpha/HDR remains explicitly fenced. Broader
process versions, profiles, WB and other Adobe controls are unfinished, not cut
from a claimed complete compatibility implementation. Original bytes/reports
retain the evidence needed for future versioned adapters.

## XML security and runtime prerequisite

The ingestion boundary uses Python's maintained namespace-aware Expat parser,
not a hand-written XML tokenizer. File size is capped at 1 MiB, depth at 32,
nodes at 4,096 and properties at 512. DTD/entity declarations, external entities,
resource resolution and arbitrary processing instructions reject. UTF-8/UTF-16
are explicit supported encodings. Duplicate semantic properties and conflicting
RDF subjects reject. Only direct top-level CRS properties can supply adaptations;
nested look/local-adjustment values remain structured unsupported evidence.

A security-patched linked Expat >=2.7.2 is required. Older packaged runtimes fail
closed with an explicit dependency error. This environment's runtime version and
package compatibility were NOT executed or verified. Python XML security source:
https://docs.python.org/3/library/xml.html#xml-security . Existing Rust curve
compilation/rendering remains authoritative; no substitute Python spline exists.

## Primary references and licensing

- Adobe XMP CRS namespace/schema: https://developer.adobe.com/xmp/docs/xmp-namespaces/crs/
- Adobe first-party PV11.0 sample: https://github.com/AdobeDocs/cis-photoshop-api-docs/blob/main/sample-code/lr-sample-app/crs.xml
- Adobe sample repository license (Apache-2.0): https://github.com/AdobeDocs/cis-photoshop-api-docs/blob/main/LICENSE
- Adobe tonal adjustment semantics: https://helpx.adobe.com/camera-raw/desktop/using/make-color-tonal-adjustments-camera.html
- Adobe process generations: https://helpx.adobe.com/camera-raw/desktop/get-started/overview-and-setup/process-versions.html
- Exiv2 observed-property registry (GPL-2.0-or-later): https://github.com/Exiv2/exiv2/blob/main/src/properties.cpp
- darktable importer (GPL-3.0-or-later): https://github.com/darktable-org/darktable/blob/master/src/develop/lightroom.c
- darktable interoperability caveat: https://docs.darktable.org/usermanual/development/en/overview/sidecar-files/sidecar-import/

Read 2026-10-23. No third-party source code or complete sample XML was copied.
Fixtures are original synthetic examples. Mature implementations informed limits
and interoperability analysis, not a borrowed renderer or quality certification.
