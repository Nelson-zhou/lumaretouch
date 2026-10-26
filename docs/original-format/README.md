# Original-format export policy — source handoff

**Status: AUTHORED / UNRUN.** No product imports, application launch, inference,
codec execution, tests, typechecks, Rust compilation, builds, installations,
downloads, commits or pushes were performed by the implementation team. Static
Python AST parsing, JSON parsing, whitespace inspection and source hashes are
not runtime or image-quality acceptance. Qoder owns local execution acceptance.

Baseline: local `86b6f5f3d0161ceb4dd604b2c2448037ed68ae11`, content tree
`e2d3b1769aad1f177050a26d0ea1a2008b3576fc`, corresponding to supplied remote
`aa813dcc6ddd542d4b64bb0075d404df79593916`. The root publisher independently
reviews and publishes; this source handoff does not claim remote publication.

## Meaning and ownership

`format: "original"` is a **policy intent**, not a codec in `export.FORMATS`.
For each authenticated document, the dependency-free Rust ABI resolves supported
encoded source precision and container to the existing JPG/PNG/TIFF/WebP writer.
Canonical suffixes are `.jpg`, `.png`, `.tif`, `.webp`. RGB8 remains 8-bit; true
supported PNG16/TIFF16 remains native 16-bit. RAW, unknown/unsupported container,
precision, topology or source variant, and unavailable codecs refuse without
JPEG/8-bit fallback. Original does not mean original bytes, original compression,
losslessness relative to the source, complete metadata preservation or RAW rewriting.

The active route is:

```
App destination preview (document IDs + intent only)
  -> cmd_export_destination -> cmd_export
  -> VCX.freeze: owned recipe + authentic source fingerprint
  -> export_source_facts: bounded metadata/header evidence
  -> export_format_native -> core/export_format Rust policy
  -> export_format_plan: per-document options/identities/decisions
  -> export_destination_runtime -> existing destination_policy.freeze
  -> start re-authenticates and requires the exact same plan ID
  -> existing queue + _export_loop, per-entry codec/precision
  -> existing full decoder agrees with frozen source facts
  -> existing RGB8 or native/edited RGB16 + watermark writer
  -> existing commit_encoded_bytes (single no-clobber publisher)
  -> actual image/variant/task receipts
```

Original native16 always uses the existing canonical edited-RGB16 recipe/render
path, including neutral documents. It never relies on the legacy master-copy
shortcut's neutral classifier. This preserves all document edits without
introducing an RGB8 fallback. The independent explicit-format classifier was
subsequently hardened for six omitted families and malformed state; see
[`../master16-policy/README.md`](../master16-policy/README.md). Original routing
remains independent of those gates. Neutral identity is a pixel expectation when no color conversion or
other edit is requested, not a byte-identical encoded-file guarantee.

There is no second renderer, file naming owner or task queue. The inactive
export controllers were not substituted for the active server route. Layout
pages retain their independent PNG/PDF 8-bit contract, not Original/native16.
Automatic workflow export profiles and their immutable hashes are unchanged;
the manual successful-group adapter continues to call canonical export.

## Frozen contract

Destination `lrt.export-destination.v1` top-level fields are unchanged. Its
`settings_json.format_plan` contains an independently versioned
`lrt.export-format-plan.v1` envelope: `requested_format`, `selection_order`,
`output_profile_asset`, and `entries`. Explicit selection order is hashed too,
including the order subsequently consumed by optional layout composition.

Each `lrt.export-format-decision.v1` binds item/document/source/recipe identity,
the exact owned recipe SHA256, full source fingerprint and descriptor stamp,
validated source-facts digest, effective asset identity, codec, bits, extension,
applicable options, effective options and decision SHA256. Nested strict schemas
and hashes are checked on restore; source/codec/precision/applicability
contradictions are rejected even if an outer digest was recomputed.

The recipe digest reuses `optics_candidate_identity.fingerprint(..., exact=True)`
on the queue-frozen snapshot **before** worker analysis/decode enrichment.
Original snapshot ownership reuses `render_snapshot.own_render_inputs`, capped
at 512 MiB retained assets per document and 1 GiB for the selected batch. These
are snapshot budgets, not a claim about total render/RSS memory. An isolated
owned worker copy prevents enrichment from mutating same-session retry inputs.

Managed imports inspect/hash the retained exact-byte copy; `original_path` is
only a logical filename. Virtual copies keep distinct document/recipe/item/name
identities while sharing immutable source facts. Creative-derived documents
require authenticated retained encoded ancestry and separately bind immutable
effective creative pixels. Actual rendering still consumes the creative asset;
RAW-derived or unauthenticated ancestry refuses. Existing alpha/HDR guards remain.

## Options, publication and retry

- Original requires explicit authenticated `document_ids` and a frozen
  destination preview. Legacy `images`/`out_dir` requests remain explicit-format
  only. A supplied `bit_depth`, including 8, conflicts and is rejected.
- UI remembers explicit-format precision but disables and omits depth in
  Original. It preserves requested GPS rather than silently turning it off.
- Target size requires **every** resolved entry to be JPEG8; any non-JPEG8
  entry rejects the entire intent before directory creation or queue admission.
- Requested GPS plus any 16-bit entry rejects the batch. TIFF compression is
  recorded only for TIFF entries; omitted preference retains 8-bit Deflate and
  16-bit none defaults. Existing JPEG/WebP quality and PNG8 effort semantics stay.
- Custom ICC files are copied into a single bounded (at most 1 MiB) immutable
  content-addressed plan asset. Existing conversion/writer code consumes those
  bytes through the active destination context, not a mutable path on retry.
  Built-in/source profile behavior and real ICC conversion/refusal remain.
- Preview/start hashes every decision and target; clean variants reserve their
  own paths using the same codec/precision. Existing protected-original,
  case-folded batch reservations, copy IDs and no-overwrite behavior remain.
- Retry validates retained destination/format decisions and exact recipe and
  source identities; it never resolves a new codec, depth, name or live recipe.
  Lost-session recipe snapshots still refuse instead of reconstructing a task.
- A complete clean/watermarked variant can be reused only when its original
  encoded-byte SHA256, current no-symlink descriptor/stat/content identity,
  exact frozen path, decision and source facts still agree. This lets a failed
  other variant continue without overwriting/re-encoding the successful one.
  Changed/missing files and incomplete/uncertain/verification-failed commits
  refuse reuse. Already committed receipts survive subsequent retry failures.
- PNG16/TIFF16 post-commit readback failures retain structured committed output
  receipts with `verification_failed`, never success or silently lost output.

Image/variant receipts retain actual codec and bits plus `decision_id`, `fact_id`
and effective asset identity. Batch `requested_format` remains `original`;
batch `bit_depth` and actual `quality` are null rather than falsely describing a
mixed batch. `requested_quality` preserves intent; actual per-entry applicability
and encoder quality are separate. Layout results keep their own 8-bit fields.

## Authored fixtures versus planned acceptance

The exact authored cases are in:

- `core/export_format/tests.rs` and
  `engine/tests/test_export_format_native_unrun.py`: native policy/ABI contract.
- `engine/tests/test_export_source_facts_unrun.py`: bounded synthetic metadata,
  authenticity/schema/decoder agreement and routing cases documented separately
  in [source-facts.md](source-facts.md).
- `engine/tests/test_export_original_plan_unrun.py`: host plan integration,
  explicit test-double resolver, mixed decisions/clean paths, all-batch GPS/size
  refusal, strict nested schema, retained recipe/source checks, actual receipt
  shape, authenticated partial reuse and frozen custom ICC bytes. Synthetic
  host bytes are explicitly **not** a codec/decode success fixture.
- `engine/tests/test_export_original_native16_unrun.py`: Original PNG16/TIFF16
  dispatch guards for colour grading, selective colour, primary calibration,
  extended tone, photo detail, ID background, mixed edits and neutral documents;
  explicit-format shortcut regression and canonical neutral-RGB16 pixel/low-bit
  expectations. Active-effect guards are source-route fixtures, not numeric
  effect or full-worker acceptance. Neutral publication is intercepted.
- `ui/src/exportModel.test.ts`: intent preference/omission, preview parsing,
  target-size retention and mixed receipt cases described in [ui.md](ui.md).

**All are UNRUN. The matrix below is planned local acceptance, not a claim that
each row has an executable fixture or that any row passed.**

| Local acceptance | Expected result / evidence needed |
| --- | --- |
| JPG8, PNG8, TIFF8, WebP8 and true PNG16/TIFF16, neutral and edited | Per-file decoder/writer/readback agrees with frozen codec/precision; no promoted RGB8 |
| Original PNG16/TIFF16 with each colour-grading/selective-colour/primary-calibration/extended-tone/photo-detail/ID-background edit alone, then mixed | Canonical edited16 recipe applies each requested effect or explicitly refuses; no successful unedited carrier shortcut. Compare actual pixels with canonical renderer and retain native precision |
| Neutral Original PNG16/TIFF16 without profile conversion | Canonical edited16 route retains exact source pixels and low bits; encoded bytes/compression need not match |
| Mixed batch + watermark and clean variants | Canonical per-entry suffixes, distinct reserved paths, same entry precision, actual receipts |
| Managed copies + virtual copies with different recipes | Retained copied bytes, logical names only; shared source facts but distinct decisions and rendered edits |
| Creative RGB8/native16 ancestry; RAW/missing ancestry | Actual creative asset rendered; unsupported ancestry explicitly refused, no carrier passthrough |
| Wrong suffixes, legacy vendor ORF/RW2 | Bitmap content routes to existing decoder; genuine vendor RAW still reaches existing LibRaw for explicit export, Original refuses |
| Valid BigTIFF/strip/tile and malformed counts/cycles/overflow | Bounded inspector and real codec agree; unknown/multiframe refuses |
| APNG/MPO/animated WebP/multi-IFD TIFF; unsupported precision/codec | Entire Original intent refuses before any output directories/tasks |
| Descriptor substitution, same-size source drift, recipe/asset change | Preview/start or worker identity refusal; no stale facts or live recipe substitution |
| Corrupt compressed payload with plausible headers | Full decode fails before publication; header evidence never claimed payload validity |
| GPS with mixed/native16; JPEG-only/mixed target size | Explicit whole-intent rejection or all-JPEG8 existing target search; no silent dropping |
| Default/explicit TIFF compression; ICC path replacement after start | Applicable defaults preserved; immutable admitted ICC bytes used; actual ICC conversion/readback |
| Source-folder/case/copy-ID conflicts, symlink races, destination permission/disk-full | Existing naming/no-clobber owner protects originals and existing outputs |
| Clean succeeds then marked fails; tampered prior output; readback failure | Same-plan partial continuation only for proven commits; honest retained failure receipts otherwise |
| Pause/cancel/retry/restart; lost retained recipe | Existing queue transitions, fixed paths/decisions; restart without snapshot refuses |
| Layout with mixed/native16 image exports | Images keep their decisions; pages/PDF report independent 8-bit delivery |
| Missing helper/ABI mismatch/codec unavailable | Readiness/preview refusal, no runtime compilation/install or Python decision fallback |
| Explicit export and automatic workflow profile regressions | Existing profiles/hashes and explicit format behavior retained |

See `source-manifest.json` for the final frozen source inventory and hashes. The
manifest excludes itself to avoid a self-referential hash. Build helper and
source/license staging are authored only; packaging is not verified executable.
