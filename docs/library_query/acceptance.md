# Library combined filters and stable sorting

Status: SOURCE_CONNECTED; runtime acceptance is UNRUN. No build, compiler,
typecheck, product import, image execution or test was run for this delivery.

Traceability: LNX-REF-WF-32447-06e4077247; handbook P0 rating filter; audit M01.
Official source checked 2026-10-23: https://www.pixcakeai.com/guide/32447
The source specifies AND across axes, multiple choices within flag/label/edit/
export/format/orientation, rating >= / <= / = 0–5, and ascending/descending
capture-time, edit-time, rating, type, size and filename sorts. Exact vendor
choice enums and equal-key ordering are not disclosed. This implementation's
explicit enums and stable ties are its own policy, not vendor equivalence claims.

## Contract

The engine owns the query and evaluates current source rows. The UI renders
returned paths in that order, retaining original session indices for opening.
An accepted transport send is not a successful query: request identity, session
identity and correlated rejection are reflected through session_state.
A view-only command bypasses edit fences, capture cancellation, dirty flags,
recipe/history writes, render, source reads and source writes. Session-state
receipt explicitly skips native document revision/capture invalidation.

Different axes intersect; multiple choices within one axis union. Empty choices
mean unrestricted. Filename search is case-insensitive substring, not a regex.
Normal photos, trash and both are explicit scopes. Reset clears all filters
(including hidden professional fields) while preserving chosen sort/direction.
Quick mode does not silently forget professional conditions. Their count and
summary remain visible. Both the library and retouch filmstrip share the query.

Unknown sort values stay last in either direction. Equal values use ascending
casefolded path, exact path, then original index. No in-place session sorting.
Capture time is EXIF DateTimeOriginal, never filesystem mtime; timezone-less
values remain camera-local time. Metadata is gathered during existing decode,
not by filtering. Edit time records confirmed live edits and successful undo/
redo in this session. Earlier/unrecorded timestamps remain unknown. Exported
means an actual successful item receipt in the current/restored project ledger,
not a claim that output still exists or that other software never exported it.

Selection is path-based with session/source identity reconciliation. Append
retains identities; replacement/removal/changed source identity clears affected
selection. Trash-state transitions clear affected selection. A hidden selection
is retained but is not a bulk-action target. Shift range follows visible sorted
order, not physical session indices. Opening passes path plus workspace identity
with the original index, rejecting stale-session/index reuse. Visible select-all
and explicit clear-selection are available. Pending/rejected/unconfirmed queries
do not expose stale batch targets. Zero results are distinguished from no imports.

## Compatibility

Project schema remains lrt.project.v22. No recipe or migration change. Existing
rating:N tags and colour labels are preserved. Flag tags use flag:accepted /
flag:rejected, and remain ordinary tags to older readers. Query preferences are
workspace-runtime view state, not an undoable edit and not persisted in projects.
Older projects without metadata are supported with explicit unknowns. New UI
with an old engine displays unsupported query protocol rather than fake filtering.
No original source file is modified by tags, filtering, sorting or trash flags.

## Qoder local acceptance, all UNRUN

1. Ratings 0–5 with >=, <= and =; combined rating/flag/colour/state/format/orientation;
   same-axis multi-select union; cross-axis intersection; reset from quick mode.
2. All six required sorts and import order, each direction; duplicate names and
   ties; missing times, sizes and metadata last both ways; case/Unicode filenames.
3. EXIF capture date with/without offset and subsecond; misleading file mtime;
   RAW without EXIF; corrupt EXIF must not fail thumbnail/library creation.
4. Neutral recipe, actual edits, undo-to-neutral, redo, history clear, no-op and
   rejected edits; preserve rendering/people/background/export behavior.
5. Successful/failed/skipped/cancelled exports; restored project task ledger;
   failed repeat export does not erase earlier known success.
6. Ctrl/Cmd select, visible sorted Shift range, hidden selections, select visible,
   append, scan replacement, source replacement, project reload, trash and restore.
7. Rapid filter changes, delayed reply, rejected candidate, query timeout, engine
   restart, unsupported old engine, zero matches and clear-search recovery.
8. Filter/sort while capture/preview/curve workflows are active: document revision,
   render frame, history, dirty flag, current photo and capture lease unchanged.
9. Save/reopen v22 and older-supported projects; unknown metadata remains honest;
   no unexpected schema upgrade. Original SHA256 unchanged across all view actions.
10. Both gallery views, keyboard focus, scroll/overflow, label/rating controls,
    flagged photos and batch targets; all source metadata badges remain factual.
