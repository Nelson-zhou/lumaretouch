# Genuine preset catalogue prerequisite

Requirement: `workflow:8YEKwsjJg7`. This is a read-only prerequisite for selecting
an existing preset in a local-workflow definition, not an implementation of
automatic preset application or a new preset format.

## First-party product references

- PixCake's [automation guide](https://www.pixcakeai.com/guide/8YEKwsjJg7), inspected
  2026-10-25, describes selecting effects according to labels and checking a graph
  before starting it. Its broader ERP, classification and branching features are
  not supplied by this catalogue. A selected effect is not evidence that this
  engine has a compatible target-image execution port.
- darktable's [styles documentation](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/styles/),
  inspected 2026-10-25, separates the available named styles and their module
  settings from applying a style to selected images. The useful semantic
  reference is explicit selection of a real stored style, rather than a text
  field that claims to identify an effect. No third-party implementation,
  artwork, preset, parameter set or licence text was copied.

Existing project and dependency licences are unchanged. Builtins come only from
the project's existing `preset_store.builtin_docs()`; user content comes only
from its existing `preset_store.preset_dir()`.

## Public Python contract

Module: `lumaretouch_engine.workflow_preset_catalogue`.

- `list_catalogue()` returns `schema`, `presets`, `errors`, and `complete`.
  The schema is `lrt.workflow-preset-catalogue.v1`.
- Every preset row contains `id`, `name`, `kind`, `builtin`, `preset_sha256`,
  `module_ids`, `modules`, `workflow_supported`, and `support_reason`.
- `modules` contains only the matching existing `scope.describe()` metadata,
  not raw recipe values, embedded assets, thumbnails, image data or review
  acknowledgements. Registry transferability and single-face requirements are
  descriptive, not target applicability or permission to apply.
- Every row has `workflow_supported: false` and
  `support_reason: "preset_owner_not_bound"`. Presence in the list must not turn
  this value true. Only a separate genuine target-specific planner and review
  port could establish application support.
- `load(preset_id)` returns a detached copy of the current validated, visible
  document. It refuses an incomplete catalogue, ambiguous ID, missing preset or
  trashed preset.
- `fingerprint(preset_id)` reads that same live document and returns its SHA-256.
  It does not accept a caller-supplied recipe, path, hash or builtin claim.
- `resolve(preset_id, preset_sha256)` rereads the actual current catalogue and
  returns the document only if its exact canonical fingerprint still matches.
  It never replaces the requested hash with a newer one or selects by name.
- Failures raise `CatalogueError`, a `ScopeError` subclass with a stable `code`
  attribute and a human-readable message. Listing instead reports bounded
  `{code, file, message}` diagnostics and `complete: false`.

The parent owner can include the catalogue in its existing profile readback.
The picker must use an actual returned ID/hash pair and surface incomplete
catalogue diagnostics. It must not manufacture a hash, ask the user to paste
one, infer a match from a display name, or treat selection as an execution or
review receipt. Resolve again at graph preflight and immediately before any
future supported application; a row read earlier is not a durable lease.

## Canonical identity and existing behaviour

The canonical document is produced by the existing
`scope.validate_preset(..., builtin=...)`, then receives the same read-only
organisation overlay as the existing store: current display name, visibility
according to trash state, and saved ordering. The complete validated document
is hashed with `workflow_owner_protocol.digest`: UTF-8 JSON, sorted object keys,
compact separators, unescaped Unicode and no NaN/Infinity.

This retains all validated module parameters, embedded portable assets and
provenance, including retained XMP adaptation content where the existing schema
accepts it. `builtin` is derived from the genuine builtin source, never trusted
from a user file. Author, note, name, kind and builtin provenance participate in
the digest. A content edit or rename therefore invalidates a pin. Equivalent
JSON whitespace/key order does not; this is a canonical-content fingerprint,
not the raw file checksum. Trash or deletion makes the entry unavailable.

No cached document is authoritative. Returned dictionaries are detached copies;
editing one does not edit the store. No import, save, rename, delete, apply,
review acknowledgement, export, project operation or image inference exists in
this module. Existing public store and organisation operations are not changed.

## Zero-write locking and safety boundary

The store's existing `catalogue_lock()` creates a directory and lock file even
for a read. This module deliberately does not invoke that initializer. It uses
the same `preset_organisation_store.LOCK`/`LOCAL` ownership and, when not nested
inside the same owner's lock, opens the exact existing `.organisation.lock`
with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK` and takes `LOCK_SH | LOCK_NB`.
Competing writers receive no implicit wait or retry: a busy lock produces an
explicit incomplete result. A caller already owning the same store lock can
nest this read; cross-directory nesting is refused.

- A nonexistent preset directory yields a genuine builtin-only snapshot without
  making a directory, metadata file or lock. The directory is checked again at
  the end; appearance during the read invalidates the snapshot.
- An existing directory without its established lock produces
  `catalogue_lock_missing` and `complete: false`. It is not silently initialized
  by profile reading. Existing preset-manager/store initialization remains the
  owner of that side effect. The user can return to that existing manager before
  refreshing; this module does not attempt to repair the store.
- The root directory, preset files, metadata and lock are descriptor-checked.
  Direct symlinks and nonregular preset/metadata entries are refused rather than
  followed. File identity/size/mtime/ctime are checked during and at the end of
  a snapshot; directory and lock identity are checked before returning.
- Existing organisation validation/reconciliation is used in memory only.
  A malformed sidecar is reported, never discarded, reset or written back.
- Duplicate JSON keys, nonfinite JSON, invalid UTF-8, executable-looking content,
  unknown modules, invalid schema and failed existing parameter/asset validation
  produce explicit diagnostics. Repeated user IDs are removed as ambiguous;
  user collisions cannot replace genuine builtins. Any such diagnostic prevents
  `load` and `resolve`, including for otherwise healthy visible rows.

The lock coordinates cooperative existing store writers. The result does not
hold a filesystem lease after return, cannot stop unrelated external programs
from changing files later, and must not be described as such. A future apply
owner must consume the resolved frozen content within its own target/review
contract rather than look up an unpinned ID again.

## Bounds

- At most 256 presets including builtins and all candidate user JSON entries.
- At most 4,096 directory entries examined, including unrelated entries.
- Each preset is bounded by the existing 48 MiB `PRESET_MAX_BYTES`.
- The existing 4 MiB organisation-state limit is preserved.
- Aggregate file reads are limited to 64 MiB, including malformed reads; one
  extra byte may be read to detect a growing entry. No pagination silently
  promises a complete result beyond these bounds.
- Retained canonical validated documents have a separate 64 MiB aggregate
  budget, including builtin content and any values filled by schema validation.
- Parsed JSON is limited to depth 48 and 200,000 nodes.
- Encoded catalogue metadata is limited to 512 KiB. Overflow returns an explicit
  incomplete diagnostic with no rows, not a silently truncated success.
- Diagnostics contain at most 512 characters per filename/message; invalid
  filesystem-name Unicode is escaped so it cannot corrupt the transport.

These are readback/work budgets, not a change to the existing preset store's
capacity. A store exceeding them needs a separately designed bounded catalogue
protocol before this workflow picker can promise completeness.

## Verification status

`engine/tests/test_workflow_preset_catalogue_unrun.py` specifies genuine builtin
and user resolution, canonical hashes, rename/trash overlays, exact-pin
invalidation, zero-write reads, malformed/ambiguous entries, symlink/nonregular
rejection, lock absence/contention/nesting, replacement races, byte/count/tree
bounds, response limits and transport-safe diagnostics.

The fixtures are authored but UNRUN. Product imports, runtime tests, builds,
typechecks, pixel/inference checks and end-to-end acceptance have not been
performed in this source-only pass. Static source/AST/hash inspection cannot
establish runtime correctness or target-image compatibility.
