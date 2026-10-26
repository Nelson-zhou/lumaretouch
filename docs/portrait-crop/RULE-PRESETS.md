# Portrait crop rule presets v1 — source-connected, all execution UNRUN

## Requirement and bounded scope

This source-only follow-on addresses `control:PC-32478:18` (保存裁剪预设), whose
handbook evidence is preserved in `ui/src/spec/refine.json` and the existing
portrait-crop research. It replaces the UI's explicit unfinished-presets notice.
It does **not** turn the manual-assisted crop workflow into automatic landmark
or hair-crown detection, and does not claim feature/runtime acceptance.

The ordinary `lnx.crop.v1` persisted rectangle/rotation is deliberately separate.
There is no import, migration, alias, export or conversion between ordinary crop
presets and this catalogue. No project, photograph, history or undo owner changes.
Batch/cohort transfer, flips, arbitrary-rotation composition and model work remain
outside this delivery. Existing rotation/source/review limits still apply.

## Source path and ownership

- `core/portrait_crop_rules`: independent pure schema/range validation and CAS
  transitions; included as a native source module with existing serde crates.
- Native `portrait_crop_rules_api/store`: one dedicated local Tauri command,
  no engine dispatch; bounded Linux private storage in
  `app_local_data_dir()/portrait-crop-rule-catalogue/catalogue.json`.
- UI `portraitCrop/rulePresets`: independent catalogue model, transport,
  app-lifetime state owner, accessible panel and authored UNRUN fixtures.
- Minimal existing portrait panel/workspace/controller integration loads only
  draft rule strings and invalidates old candidate/review/anchor confirmations.
  Selecting a catalogue entry alone does not load it.

There are no new package dependencies, runtime plugins, network calls, downloads,
models, image/anchor inference or Python/product imports. Existing photographic
planner, native/Python host, crop sampler, rendering, apply and history remain the
final authority and are not modified by this slice.

## Exact persistent schema

`schema = "lrt.portrait-crop-rule-catalogue.v1"`, `catalogue_id` is 32 lowercase
hex characters generated locally, `revision` is a nonnegative safe integer
(`<= 9007199254740991`), `entries` is a maximum 256-item array. Each entry has
exactly `id` (`rule-<creation revision>`), `name`, and `rules`. No entry ID is
reused after deletion. Total canonical file size is bounded to 256 KiB.

The only rule fields are:

| Field | Local convention and accepted range |
| --- | --- |
| `aspect_ratio` | Frame width / height; finite 0.001–1000 |
| `headroom_fraction` | True crown-to-top spacing / frame height; finite 0–1 |
| `head_fraction` | True crown-to-chin height / frame height; finite >0 through 1 |
| `horizontal_position` | Face center horizontal position / frame width; finite 0–1 |

Headroom plus head fraction must not exceed 1. These are the existing local
conventions, not newly asserted vendor defaults or ranges. Vertical position
remains implied. The catalogue cannot validate a rule against a new photo;
existing actual-photo planning rejects infeasible geometry without clamping.

Names are case-sensitive, 1–64 Unicode scalar values and <=192 UTF-8 bytes.
Leading/trailing whitespace, controls, non-space whitespace and designated
zero-width/bidi formatting are refused. Names are not trimmed, normalized,
converted into paths or silently overwritten. Invalid/empty rule draft fields
are refused; there are no starter/default presets.

Every persistent struct and mutation schema rejects unknown fields. Prohibited
payload includes image paths/bytes and source/document/person/face identities,
crown/chin/center coordinates, rectangles, rotation, candidate tokens and any
confirmation/review state. Version and generated catalogue/entry IDs are protocol
metadata, not source identities.

## Actions and explicit UI intent

`list` reads a catalogue; `create`, `rename`, `update`, `delete` require the exact
`catalogue_id` and `expected_revision` from the displayed catalogue. Requests are
bounded to 8 KiB. Native performs CAS while holding an OS exclusive lock. Stale
mutation requests are refused without a catalogue edit and never rebased/retried.

- Create saves the current **four rule draft values** under a new name. Exact
  duplicate names are rejected, not interpreted as permission to update.
- Rename changes only the selected entry's name.
- Update is a separate explicit action with a confirmation showing the selected
  name and replacement four draft values. Equal-value update is a confirmed no-op.
- Delete opens an inline confirmation naming the exact selected entry. Cancel
  has no effect. Delete never changes a photograph or undoes a crop.
- Load is an explicit “载入为草稿，不应用” action. It changes four draft fields,
  clears any old candidate, decoded-preview readiness, review confirmation and
  anchor confirmations. It neither captures nor previews nor applies an image.
  Existing same-photo measured points may remain visible but must be re-confirmed;
  photo/context changes already discard all measured points and face selection.

Catalogue selection, refresh, create, rename, update and delete do not dispatch
photo commands. Per-photo real anchors and a newly generated/reviewed full
before/after candidate remain mandatory for any actual crop application.

## Atomicity, recovery and no-change statements

The stable unversioned directory name prevents a later schema from being silently
bypassed as an empty v1 catalogue. Directory traversal and creation are
no-follow and descriptor-anchored: every ancestor is opened/validated before
mkdirat/openat of its child, never path-based create_dir_all. Ancestors must be
owned by root/current user and not group/world-writable, except root-owned sticky
ancestors whose protected children cannot be renamed by another user. The app
storage parent must be current-user owned and not group/world-writable. Private
catalogue directory/file ownership, 0700/0600 modes, regular-file type, single
links and byte limits are checked. All file operations are descriptor-relative. A persistent `flock` file serializes cooperating windows
and processes for the entire read/CAS/write. Busy lock is a no-change rejection,
not a repeated write. Only the app-owned directory is created.

A successful mutation writes one exclusive `catalogue.partial`, fsyncs the file,
atomically renames it over the same-directory canonical target, then fsyncs the
directory and rechecks directory identity. No partial content is published.
Errors before successful rename report `rejected` with `no_change: true` for the
requested catalogue mutation. Errors after rename report `uncertain`; they never
claim no-change or deletion failure. Missing/invalid IPC receipts also remain
unknown in the UI. No photo-write claim is involved in either case.

On reopen/read, only a fully validated canonical target is accepted. An orphan
partial is discarded **after** validation and is never replayed/promoted. The
directory is synced before returning the snapshot. Thus an interrupted ordinary
save retains a complete old or new catalogue rather than merging partial data.
Unknown schema, malformed JSON, insecure file, symlink, size overflow, or an
existing directory missing its canonical target is refused without empty-default
replacement. There is no automatic backup restore that could roll revision back.
First empty initialization uses exclusive canonical O_CREAT|O_EXCL, not the
normal replacement-save path. A successful mkdir alone is never treated as proof
that the opened directory is still new: even a substituted existing catalogue
cannot be overwritten, truncated or deleted by initialization. The exclusive lock
covers first write/fsync; post-create errors are uncertain, not no-change. A crash
during very first empty-catalogue initialization can leave a deliberately blocked
missing/incomplete target requiring manual backup/inspection; it is not silently
reset. Only subsequent mutations use the atomic replacement-save path.

Closing the panel retains the app-lifetime catalogue operation owner and cannot
cancel or retry a write. Native I/O runs off the UI thread. The transport does
not impose a synthetic timeout that could falsely declare a still-running write
failed; a pending call stays pending. If IPC rejects or native reports uncertainty,
only read refresh is allowed. An unchanged revision cannot prove no-write and
keeps mutation controls fenced. A newer revision or different catalogue identity
makes the old CAS unusable and unlocks new explicit user decisions, while keeping
the original historical outcome unclaimed. A genuinely stuck I/O or an unchanged
unknown outcome requires external diagnosis/restart; no automatic repeat is made.
Restart reads persisted data; it is not evidence that the old operation failed.

Storage adapter v1 is Linux-only, matching existing app-local storage conventions;
other platforms return explicit unavailable/no-change. Filesystems must support
Linux advisory locking, atomic same-directory rename and fsync semantics. Runtime
crash/disk/permission behaviour is **not accepted by source inspection**.

## Verification status and Qoder handoff

**Performed:** source inspection, direct static review, JSON parse of the freeze
manifest, scoped whitespace/EOF checks. No Python product files changed, so Python
AST validation is not applicable. No Rust/TypeScript parser was available or run.

**Not run:** tests, compiler, typecheck, build, inference, app/browser, storage
fault injection, photographic review, numerical/pixel parity, performance or
real local persistence acceptance. Fixtures are authored **UNRUN**, not evidence
of passing tests. No installation/download or new Codex task was performed.

Qoder's later authorized local validation should cover:

1. Native compile and UI typecheck/build; both Rust UNRUN fixture modules and
   two UI UNRUN fixture files. No default test-script expansion is claimed.
2. Fresh list; empty draft rejection; create; exact same-name conflict; rename;
   explicit update/no-op; delete confirm/cancel; limit and Unicode boundaries.
3. Two windows/processes using stale catalogue revisions; double-click; save while
   closing/reopening; invalid/late/lost receipts; unchanged and advanced refresh.
4. Restart persistence and kill-before/after-fsync/rename; partial scratch;
   full disk, permission failure, wrong schema, truncated file, symlink/hard-link,
   missing canonical target and first-initialization interruption, a replaced
   newly created directory, and symlink/shared ancestors. Verify existing target
   bytes survive stale initialization and no child is created through an unsafe
   ancestor. Post-create/post-rename failures must never say no-change. Do not touch real user catalogues.
5. Current-photo rules load invalidates a reviewed preview and anchor confirmations;
   photo switch requires its own face/real crown/chin/center; load makes no engine
   call; new infeasible rules are refused by the actual planner; ordinary crop,
   history/undo/redo, save/reopen and original rotation refusal remain intact.
6. Keyboard focus and disabled states, Cancel/Close/Escape, inline delete/update
   confirmations, source switches, edit interruptions and repeated navigation.

Exact changed-file manifest: `RULE-PRESETS-FREEZE.json`. The older
`PORTRAIT-CROP-FREEZE.json` remains an immutable historical slice; this follow-on
supersedes only its then-unfinished rule-preset item, at source-only/UNRUN status.
