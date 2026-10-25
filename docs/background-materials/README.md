# Local background-material catalogue

Status: source authored, statically reviewed, all runtime/visual/image/packaging
acceptance **UNRUN**. No tests, compiler, typecheck, build, product import or
execution, model download, inference, hardware access or Git write was performed
for this slice. Source presence is not a release-quality or whole-feature claim.

## Exact requirement and genuinely new workflow

Baseline inspected: `d5f81acb7e686ed99f8012fcac1b3c638527018e`.

The preserved requirement is `creative:165433`,
`ui/src/spec/creative.json:259–265` and
`docs/development/handbook-traceability.json:1187–1196`. The original expanded
mapping is not available in this workspace, so no missing hashed requirement ID
has been invented. Actual first consumer is existing ID-background control
`LNX-REF-PC-32475-C-7f1d9dd04c` (the user's background materials).

The new capability is a durable, reusable library of user-owned background files:
import files/folders, search, categorize, reorder, rename, multiselect move,
recoverably remove/restore, then choose a real material in the ID-background
editor. It is not a renamed file picker or another colour-sample catalogue.

Baseline source evidence:

- `IdBackgroundPanel.tsx:26,42` provided only a one-file picker.
- `id_background_controller.py:52–54` already decoded that file and packed it into
  the image recipe, but had no catalogue browse/search/organization operation.
- `SkyReplacementPanel.tsx:16–21,52–55` also used an individual-file picker.
- `creative_document_assets.py:94+` held private content-addressed rendering
  assets, not a persistent user-facing material catalogue.
- `sample_library_state.py:89–122` is explicitly a colour-reference schema. It
  remains separate and unmodified. No sample records or user directories migrate.

Existing layout/printing, export destinations, target-size delivery, project
packages/recovery and sample-photo management were inspected and were **not**
counted as missing merely because runtime acceptance remained outstanding.

## Primary sources and licences

Read on 2026-10-25:

1. [PixCake's official 165433 guide](https://www.pixcakeai.com/guide/165433),
   particularly its material-management section, describes own-background import
   from files/folders/drag and drop, search, categories, ordering, multiselect
   moves, rename, deletion and refresh. Official-pack downloading and AI scene
   generation are separate behaviors, not supplied by this local catalogue.
2. [Official ID-background guide](https://www.pixcakeai.com/guide/32475) specifies
   own JPG/PNG/TIF/BMP material up to 10 MB. The first consumer therefore retains
   its exact 10,000,000-byte admission, not the sky module's separate 64-MiB limit.
3. [Krita resource management](https://docs.krita.org/en/reference_manual/resource_management.html)
   documents resource libraries, lazy loading, naming/tagging/filtering and
   reversible deactivation. These are mature architectural/UX precedents, not
   copied implementation or artwork. [Krita's application licence](https://krita.org/en/about/license/)
   is GPLv3; it does not grant rights to somebody else's resource images.
4. [digiKam's albums documentation](https://docs.digikam.org/en/left_sidebar/albums_view.html)
   documents folder imports, organization and recoverable trash. This catalogue
   uses logical groups rather than moving the user's original folders. No digiKam
   source, logo, screenshot or sample photograph is included.
5. Existing codecs remain existing dependencies: [Pillow MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE),
   [imagecodecs BSD-3-Clause](https://github.com/cgohlke/imagecodecs/blob/master/LICENSE)
   and [LittleCMS MIT](https://github.com/mm2/Little-CMS/blob/master/LICENSE).
   Their existing dependency and binary-codec notices still apply. No new decoder,
   model, resource pack or vendored upstream code is introduced.

The catalogue begins empty. Import accepts only local material the user is
entitled to use. Code/codec licences never imply rights to commercial background
packs. No upload, network lookup, proprietary download or scraping path exists.

## Modules and integration seam

See [the exact v1 contract](CONTRACT.md) for transport fields and result schemas.

- `background_material_state.py`: strict versioned identities, validation and
  application-policy bounds.
- `background_material_store.py`: independent location, flock, CAS, immutable
  file validation, atomic catalogue publication and previous-catalogue copy.
- `background_material_images.py`: bounded explicit folder walk, no-follow
  descriptor copy, exact original-byte hashing, existing ID decoder and separate
  display-only thumbnails.
- `background_material_query.py`: small revision-pinned pages and receipts.
- `background_material_controller.py`: organization/import/trash/select workflows.
- `background_material_command.py`: strict transport-neutral dispatcher.
- `background_material_selection.py`: full-resolution, current-library selection
  resolver returning the existing immutable `IDBackgroundAsset`.
- `background_material_host.py`: serialized commands, bounded terminal receipts,
  cancellation-only reader ingress with pre-admission cancellation retention,
  and a shared outer-guard rejection hook that preserves exact cached terminals.

Shared integration is deliberately outside these modules. The existing ID owner
must add `id_import_material` with the strict `selection` object, resolve the asset
after its existing document/revision checks, pack via existing
`id_background_assets.pack`, then retain its current single edit/history/project/
export owner. The library itself never changes image parameters, mask support or
rendered pixels. The UI must fence its caller's photo/revision before choosing.

The first real consumer retains existing original/returned-source ownership,
support review and mutual-exclusion rules. No library operation invents a mask,
implies that a displayed thumbnail is an image preview, or bypasses the ID owner's
original-shadow reviewed-edit guard.

## Preservation and failure semantics

The immutable objects are byte-for-byte copies of selected originals, named by
SHA-256 and detected format. Original paths are only read through regular-file,
no-follow descriptors and checked for changes. Complete original compressed bytes
are retained; float32 images are temporary existing decoder outputs, not stored
library masters. Real PNG16/TIFF16, embedded ICC, orientation and alpha use the
existing ID asset implementation. Thumbnails are separate, at most 256 pixels on
their longest side; their 8-bit display does not set source or export precision.

Names/categories/order/trash are metadata. Trash does not delete immutable objects;
no purge or garbage collector is provided. Existing saved image/project bundles
own their bytes independently. Removing a catalogue row blocks a pending selection
but cannot delete an already-packed background. Duplicate imports report the
existing active/trash row rather than manufacturing another original.

Every mutation compares the catalogue revision. The catalogue also has a stable
library UUID, so a selection from a different root cannot accidentally match the
same numeric revision. Selection resolution checks row, SHA, decoded pixel/ICC/
alpha identity, and catalogue revision again after decode. Unknown file changes,
unsupported codecs, memory limits, corrupt schema, missing indices and unsafe
managed paths fail visibly. No reset, guessed colour profile, bit-depth reduction
or preview substitution is used as recovery.

Import cancellation preserves and reports preceding successful files. Other
mutations cancel before atomic publication. Cancellation after confirmed durable
publication does not change success into cancellation. If rename occurred but
directory fsync failed, the outcome is explicitly uncertain/committed and must
be reconciled rather than resubmitted. Native/engine restarts do not imply a
durable cross-engine operation receipt. The previous catalogue is retained but
never silently restored over a damaged current catalogue.

Interrupted/failed imports may leave unindexed immutable objects. Storage
accounting includes them; they are not silently discarded or reused with changed
content. Linux flock is intentional. Current bounds are not unlimited catalogue
scale, hard native decoder cancellation or universal process-memory guarantees.

## Not claimed

- No AI staging, automatic light blending, 4K/6K generative output, random batch
  background matching, official stock pack or whole `creative:165433` completion.
- No sky consumer in this slice. Its opaque-only and different byte-budget rules
  need a separate explicit adapter, not a relabelled ID selection.
- No claim that the existing ID algorithm, PNG16/ICC pipeline, Tauri transport,
  photo quality or cross-machine packaging has passed new runtime acceptance.
- No drag-and-drop UI claim follows merely from the backend accepting explicit
  paths; UI behavior must be judged from the actual connected implementation.

Dedicated authored but unexecuted fixtures:
`engine/tests/test_background_materials_unrun.py` and
`engine/tests/test_background_material_host_unrun.py`.
They cover exact bytes, actual decoder/alpha/PNG16 ICC paths, CAS/search/groups,
trash and project bundles, malformed catalogues, unsafe paths, changed objects,
mid-decode revision changes, cancellation/partial imports, uncertain durability,
cancel-before-admission, terminal replay and post-commit cancellation.
The dedicated host fixtures also cover outer-guard rejection without dispatch,
event retirement, unknown after-entry interruption, preservation of an existing
authoritative result, conflicting IDs and bounded rejection retention.
