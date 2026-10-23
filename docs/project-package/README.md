# Portable project package and dependency recovery

Status: source-connected implementation; every runtime acceptance case remains **UNRUN**. No package was created by the implementation agent. No application import, build, compiler, typecheck, model invocation or test execution was performed.

## Exact scope

Handbook line 1047 / core audit M07 is a portable archive workflow, not merely single-file project save. Related original mapped rows are LNX-P0-PROJECT (`lnx.project.v1:create/open/save`), LNX-CORE-004 (original read-only), LNX-REF-WF-121298-2ca1392931 (backup/cross-device entry) and LNX-REF-WF-192117-f01ea02b58 (project loss troubleshooting). These are overlapping related requirements, not new independent completed controls. The new route does not claim cloud synchronization, automatic backup scheduling, universal troubleshooting or whole-family acceptance.

## End-to-end route

ProjectWorkspace → ProjectPackagePanel/useProjectPackage → native.ts → registered project_package_api.rs → engine receipt receiver → server `project_package` → project_package_host → bounded archive/dependency modules. Existing create/open/save remains the actual normal handler, extracted unchanged into project_package_project_commands.py; opening restored projects retains dirty-state guards and normal v23 project loading.

1. Save the current project, then explicitly choose whether to copy original photographs and external reference originals. Neither checkbox is selected by default.
2. Preview shows source/reference identity, inclusion state, licence/provenance, retained embedded assets and model dependency policy. A native picker and confirmation display the exact new destination.
3. One cancellable worker copies bounded chunks, computes full SHA-256, builds a content-addressed ZIP and verifies all bytes before exclusive publication. Existing files/directories are never overwritten. Sources are never modified or removed.
4. Restore first validates archive inventory and full SHA hashes, previews dependencies, then publishes to a new unique directory. Opening is a separate explicit action. Excluded/missing sources are rebound to nonexistent missing paths, never silently reused from old absolute paths.
5. UI retains the original operation ID and destination across reload. Status and cancellation are read back; cancellation acknowledgement is not completion. Unknown publication uses verification of the existing destination, never automatic resubmission. A retained restore receipt is checked against the immutable original project/manifest and reconstructed relocated project.

## Dependency and identity contract

- Stable document/source/root-copy IDs, copy numbers, recipe IDs, versions, undo/redo, people/support/body metadata and source provenance remain intact. Equal content may share a blob but independent logical sources restore to different paths.
- Project `assets`, reference-color frozen bundles, custom LUT bytes, masks, people/support/landmark records and ID-background replay bytes are mandatory parts of the project. They cannot be dropped by the external-reference checkbox. External sky reference paths are inventoried across inactive versions and history as well as active recipes.
- Missing originals use the existing source-relocation UI. Missing sky references are explicitly listed and repaired through the sky asset picker; they are not automatically substituted or discarded. Immutable historical recipe provenance is retained.
- Embedded assets and all project metadata are covered by the full project SHA in the immutable manifest. Included external files have full SHA and byte counts. Excluded files retain known hashes without pretending a head-only legacy fingerprint is a new full-file measurement.
- Model identity evidence and writer environment are declared separately. No model path is followed, no weight is included, no download occurs, and no model licence is inferred. User-provided content has an explicit rights-not-inferred label.
- Package v1 requires a validated v23 project. Existing older project migration remains through normal open/save; unsupported package schemas fail closed rather than inventing a migration.

## Safety limits and limitations

20,000 ZIP members maximum; 8 GiB per external file; 32 GiB aggregate; 256,000,000-byte project; 16,000,000-byte manifest; 64× maximum expansion ratio. ZIP entries are constrained to manifest/project JSON and content-addressed blobs; absolute/traversal, backslash, duplicate/case/Unicode collisions, links/devices, encrypted entries and unlisted content are rejected. ZIP directory preflight bounds entry count before allocation. No extractall or archive-provided code execution exists. Chunk boundaries honor cancellation. Private temporary files may remain after hard process termination, but are never promoted over an existing destination.

Directory publication requires Linux renameat2(RENAME_NOREPLACE); unsupported systems fail without an overwrite fallback. Integrity hashes are not signatures or proof of publisher trust. Normal project decoding/rendering still needs its own established validation. Cross-device rendering equivalence, desktop dialog behavior and native transport require local runtime acceptance.

## Primary references checked 2026-10-23

- Python ZIP documentation: https://docs.python.org/3/library/zipfile.html . Supports exclusive creation and ZIP64, documents duplicate names and extraction pitfalls including decompression resource exhaustion. This implementation adds strict whitelisting and budgets rather than relying on general extract helpers.
- Kdenlive official archive workflow: https://docs.kdenlive.org/en/project_and_asset_management/file_management/archiving.html . Separates archiving a project together with required assets from merely saving its project file. LumaRetouch uses the same user-visible distinction without copying implementation or claiming feature parity.

Authored executable archive cases: engine/tests/test_project_package_archive.py. UI/native/reload cases: ui/src/projects/projectPackage.unrun.md. All remain UNRUN.

Recovery receipts bind the original operation ID, not just a user-provided destination name. A valid archive/directory belonging to another operation is not reported as the awaited success. Restore preflight is asynchronous too; cancellation and reload during preflight are separate from write outcomes.
