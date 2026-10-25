# Original neutral people census proof

Status: **AUTHORED / UNRUN**. Reimplemented against the recovered verified source
baseline; these are not recovered uncommitted bytes. No product imports, tests,
inference, build, benchmark, numerical comparison or photographic review ran
during authoring. AST parsing and source hashes are not runtime evidence.

## Narrow contract

`creative_capture_people.py` supplies two helpers for the explicit private
edited-original capture strategy:

- `neutral_census_candidate(people) -> bool` selects a possible neutral census
  before decoding/preparation. It reads the actual unchanged graph, not a supplied
  `is_neutral` flag. It does not authorize skipping people preparation.
- `neutral_original_census(spec, source) -> bool` checks that same bank against
  the actual RGB8/16 decode and a separately captured source/document context.
  Only this definitive result can authorize the private strategy's no-effect
  people preparation skip.

The helper never clears/replaces `spec.people`, creates a face or FaceRef,
invents an association, resizes masks, builds geometry or substitutes a preview
effect. A zero-face bank materializes its real photograph-wide leaves without
fabricating an instance. Generic preview, export, batch and derived-source paths
retain their existing preparation behavior.

At initial strategy selection, a valid unsupported candidate remains on the
ordinary legacy route. After private capture is selected, a failed definitive
proof must **refuse** that private capture. It must not silently drop the people
bank or fall through to full preparation whose allocations were not admitted.
Malformed actual owner/evidence raises, not a permissive candidate result.

## Independent original/document binding

The capture owner supplies `spec._creative_capture_original_source` with exactly:

```text
path: actual original decode path
file_stamp: five-integer decode stamp, tuple or list
asset_sha256: SHA-256 of the actual original file bytes
document_id: independently selected native document owner
```

Missing context returns `False`; malformed context raises. The helper compares
its document with `spec.people_document_id`, calls the existing snapshot and
cross-owner validators, and compares the graph asset with the context digest.
It independently verifies file stamp and streamed digest before and after a
successful census proof. All target face evidence dimensions must equal the
actual decoded original dimensions. A retained hair source path, even dormant,
must match the original path exactly.

The capture owner still proves that the supplied pixels actually came from the
true orientation-normalized original decoder at the requested bit depth. A hash
of an encoded file cannot prove its relationship to an arbitrary NumPy array.
The owner must reject repaired-source substitution and retain its document,
file and publication race fences. This helper is not a transferable publication
authority and cannot independently inspect the live host document selection.

## Shared strict neutrality policy

Both helpers share structural graph, source-metadata, canonical recipe and
retained-analysis checks. They reuse existing document/state/support-store
validators, the unconditional face-decoration/facial-sculpt/eye-makeup graph
validators, sparse inheritance resolver, canonical operation validators and
compatibility check. The definitive proof additionally uses the existing
fast-path blocker and all-face render planner.

Every target face's resolved recipe must equal the canonical default, including
disabled faces. Every raw leaf must also equal its default, preventing a neutral
winner from hiding shadowed active intent. A dormant but nondefault mode remains
outside this first version. Boolean/numeric aliases cannot pass through Python
equality or legacy float coercion. Unknown operations/paths and malformed scalar
domains raise, including actual photograph-wide leaves in a zero-face bank.

The final plan must be current, cover all enabled source faces, contain only
ready entries, and contain no analysis-consuming effect. No face is omitted to
make an otherwise active bank appear neutral.

The strict scope declines:

- Any person, group, link or reviewed cross-owner association, even neutral.
- Foreign-source graph faces, analysis-run entries or photograph-wide leaves.
  Supplied analysis rows without the exact target-source face raise instead of
  being filtered out.
- Any unresolved, retained or confirmed legacy archive record.
- Any local asset, retained support or hair store, hair evidence or replay stamp,
  including disabled pointers and detached immutable assets retained for history.
- Body observations or body replay/proof inputs, repair inputs, recovery targets
  or recovery path/stamp metadata, even when dormant.
- Recovery fields except `None` or an exact empty list. The existing neutral
  `effect_recovery_runtime.export_prepare` writes `[]` before people preparation;
  this known empty transition is supported. Nonempty fields and other container
  types remain excluded, as do any recovery targets or source metadata.
- Manual/unverified target faces and missing target analyses, including disabled
  faces. This is deliberately stricter than generic neutral rendering.
- Unknown snapshot fields, creative bases/derived-source records, float RGB,
  inconsistent retained grids, or named semantic planes no longer at their
  recorded producer dimensions.

These are optimization scope limits, not relaxed rules for the generic renderer.

## Retained analysis and memory boundary

Every supplied row is validated, including disabled faces and rows not needed by
the no-effect render plan, even when another bank property already disqualifies
the optimization. Validation covers exact FaceRef/revision, matching durable
evidence, verified detector/model schema, finite 478x3 landmark bytes and digest,
allowed keys, finite ranged masks, and existing named face/body-skin observations.

Each row is checked at its actual common retained mask grid, not enlarged export
dimensions. Different faces may retain different producer grids. Different mask
grids within one row are independently value/owner-checked and then declined.
Named semantic arrays must match recorded producer width/height. Legacy
`excluded` and `skin` have no independent producer-grid metadata; their actual
shared array shape plus model evidence is the strongest existing transport
contract, not proof of newly inferred full-resolution semantics. Maskless
verified landmark rows do not require invented coverage.

No target-grid float coverage copies, full RGB conversion or joint geometry map
are allocated. This is **not** a constant-memory claim: existing finite/range
checks create Boolean scratch at retained producer dimensions, potentially about
three simultaneous Boolean planes. Those retained arrays may themselves already
be full-resolution. The caller must admit retained backing storage and validation
scratch **before either helper**, including pre-decode candidate classification.
A conservative caller can reserve four bytes per element of its largest
retained array in addition to actual backing storage and bounded metadata.
Graph/vector validators also copy their bounded JSON metadata. The explicit
numeric conversion is shape-checked to 478x3 before allocation. File hashing is
streaming I/O, not another decoded RGB buffer. Actual peak RSS is unmeasured.

## Authored coverage and remaining acceptance

`engine/tests/test_creative_capture_people_unrun.py` covers RGB8/16 and array
identity preservation; no target-grid preparation; actual producer grids and
maskless rows; missing/malformed private context; source stamp/digest races;
same-byte document ownership; derived/alpha exclusion; active, disabled,
shadowed and dormant intent; scalar aliases; zero-face leaves; stale/corrupt and
foreign analyses; invalid masks/model evidence; named semantic observations;
different/mixed grids; aliased arrays; missing/manual evidence; foreign runs;
legacy and cross-owner records; disabled local assets; corrupt/detached stores;
disabled recovery and body/repair exclusions; unknown retained inputs; planner
refusal; the real neutral recovery-preparation transition; and the private
`people_export.prepare` true/false/repaired/generic routing boundaries.

All fixtures remain **UNRUN**, and their model hashes/landmarks/file bytes are
synthetic schema data, not real detector or decode evidence. Before accepting
the strategy, run them under the authorized project runtime and compare actual
RGB8/16 capture output against legacy rendering. Owner-level decode/document
races, active/repaired fallback, peak-memory instrumentation, full-resolution
representative photos and end-to-end publication remain acceptance gates. This
module alone establishes neither pixel equivalence nor release readiness.
