# Automatic export profiles — source-only slice

Status: implemented source; authored fixtures UNRUN. No tests, build, typecheck,
engine/model execution or photographic validation performed. Qoder owns final local tests.

## Exact scope

Automatic finite directory jobs can select five immutable engine-returned profiles:
legacy JPEG95 RGB8; JPEG80 RGB8; JPEG100 RGB8; PNG RGB8; TIFF RGB16 uncompressed.
All retain sRGB, scale=1 (no resize), Lanczos3, sharpening=0, GPS=false,
no watermark/layout, chosen existing output root, flat original stem and canonical
extension (.jpg/.png/.tif), conflict=ask. PNG/TIFF use the existing command's
quality=95 placeholder; this is not a lossy quality setting. No arbitrary quality,
ICC paths, resize, PNG16, WebP or compression configuration is exposed here.
Reviewed workflows keep the exact legacy profile and digest.

The engine catalogue is metadata, NOT assurance that a given source/recipe can
export. TIFF16 still goes through existing cmd_export, full source/native16 decode,
floating edit and RGB16 write/readback checks. RGB8 or embedded-preview sources
cannot be promoted to fake native16. Unsupported source/effect/codec reports a
failure; it never silently changes to JPEG. Uncompressed TIFF uses the existing
writer and does not add a dependency. Existing RGB8 PNG encoder is reused.

## Authority and output safety

Each complete profile has its own recipe_sha256; existing graph persistence/hash,
Start consent and immutable freeze_export command already bind that digest.
No core schema change or settings database is needed. Preflight resolves the
exact digest for the graph's mode; dispatch compares with the exact preflight
graph; canonical destination plan hashes contain actual format/settings.
The renderer gets the selected profile, not a separately guessed extension.
The UI discloses the selected complete profile and refuses consent when absent;
changing the profile edits the graph and invalidates prior preflight/consent.

Destination collisions, same-stem collisions across inputs, originals protection,
pinned directories, full-source rendering and atomic no-clobber publication stay
under existing planner/export owners. No hidden rename, missing-directory create,
overwrite, custom encoder or retry mechanism was added. A terminal original task
plus exact output hash/size is still required for exported; saved or task-started
is not exported. Unknown outcomes remain query-only.

## Source review / local test handoff

Authored Python fixtures cover exact catalogue, legacy identity, mode rejection,
unsupported settings, command/frozen hash propagation, PNG/TIFF extension and
collision rejection. TypeScript fixtures cover exact profile validation, duplicate
hash rejection, profile disclosure and consent invalidation. Existing owner
unknown-outcome/receipt/native precision fixtures remain relevant and UNRUN here.
Qoder should additionally exercise true native16 TIFF, RGB8 refusal, unsupported
16-bit effect refusal, existing and same-stem output collisions, cancelled worker,
restart/unknown receipt and changing profile after preflight on the actual app.

## Official references consulted before implementation

- Adobe Lightroom Classic export workflow: https://helpx.adobe.com/lightroom-classic/help/exporting-photos-basic-workflow.html
- Adobe export file settings/destination/naming: https://helpx.adobe.com/lightroom-classic/desktop/export-photos/export-files-disk-or-cd.html
- Pillow codec/format documentation: https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html

These guide explicit settings and destination UX, not a claim of matching Adobe
features or that Pillow alone provides true RGB16. Actual capability came from
server.py cmd_export, export_destination_runtime.py, export.py native RGB16
writer/renderer and their existing guards.

## Owned-file manifest

- engine/src/lumaretouch_engine/workflow_owner_protocol.py
- engine/src/lumaretouch_engine/workflow_owner_export.py
- engine/src/lumaretouch_engine/workflow_owner_host.py
- engine/tests/test_workflow_export_profiles_unrun.py (new)
- ui/src-tauri/src/local_workflow_host/view.rs
- ui/src/localWorkflow/contracts.ts
- ui/src/localWorkflow/controller.ts
- ui/src/localWorkflow/LocalWorkflowPanel.tsx
- ui/src/localWorkflow/automaticBatch.unrun.test.ts
- docs/development/AUTOMATIC-EXPORT-PROFILES-SOURCE.md (new)

Validation performed: Python AST parse of the three modified engine modules and
new fixture; scoped whitespace diff check. TypeScript parser is not installed in
the checkout; no installation or typecheck attempted. Changes remain uncommitted.
