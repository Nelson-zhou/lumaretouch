# Original edited-capture admission

Status: authored, source-reviewed, runtime UNRUN. This is a conservative
application-working-set ledger with explicit native reserves, not a measured RSS
bound, a 24 MP acceptance result, or permission to omit an edit. No product
imports, test execution, builds, typechecks, inference or downloads were run.

## Public interfaces

- `classify_snapshot(snapshot) -> Eligibility` is the pre-preparation gate.
  `snapshot_eligible` is its Boolean wrapper. Unknown/incomplete fields, malformed
  records and unsupported recipe families return not eligible. Keep the complete
  recipe and select the existing legacy path. Never neutralize actual inputs.
- `validate_spec(spec, snapshot=None, *, skipped=()) -> Eligibility` accepts only
  an ordinary `ExportSpec`, checks its explicit audited field inventory and
  normalized colour fingerprint, and raises `AdmissionError` on rejection. It
  neither mutates the spec nor calls the mutating `ExportSpec.check` method.
  The common renderer still runs all its existing validators.
- `inspect_storage(value, *, baseline=None) -> StorageCensus` traverses bounded
  ordinary containers, numeric CPU arrays, immutable bytes and exact known
  records. It reports unique terminal backing storage, prospective deepcopy
  array bytes, container storage and retained-array validation scratch.
- `retained_bytes(*roots, baseline=None) -> int` combines retained backing and
  container bytes. Count all simultaneous roots together. Equal byte contents
  are not shared owners. Two ndarray views retain the whole backing allocation;
  two distinct views also need distinct ordinary-deepcopy destinations.
- `admit_snapshot_copy(value, *, max_bytes, host_lease_bytes=0, copies=1)` must run
  before the new deepcopy/context/census copies. A tuple of state and raw context
  roots is accepted. `copies` must cover separate materializations and per-face
  mask duplication, not merely the number of unique input owners. This does not
  retrospectively admit a host `_capture_state()` already performed upstream.
- `plan_capture(metadata, snapshot=None, *, spec=None, max_bytes,
  retained_bytes=0, persistent_retained_bytes=0, host_lease_bytes=0, tile=1024)`
  returns an immutable plan or raises `CaptureBudgetExceeded`. Call before real
  decode, then again with the built spec and actual retained roots. Metadata is
  the public `inspect_encoded_source` result, never its private parser source.

An identity baseline is valid only while its original roots remain alive.
`retained_bytes` excludes encoded original and ICC bytes because those are named
separately. `persistent_retained_bytes` is a subset already included in retained
bytes that remains alive after the render scope, such as the caller's state. The
capture bridge also includes the raw engine people-analysis bank and all retained
virtual-copy context stores in this persistent union. Those raw owners are
counted before copying and remain charged after the transient frozen snapshot
and ExportSpec are released. Shared terminal owners across state, banks and
snapshots are deduplicated together, not by equal values. Persistent bytes are
charged separately only in output-tail phases because render retained bytes
already include them. Other session/model/assets belong in the explicit host
lease. Do not confuse any of these ledgers with process RSS.

## Eligible recipe cohort

The unchanged export chain handles exposure, white balance including picked
gains and algorithm identity, legacy tone and global grade, HSL, levels, supported
curve recipes, validated ordinary CubeLut and primary calibration. Colour grading
and selective colour use a separately reserved whole-frame finishing phase.
Crop and strictly snapped quarter turns retain the common geometry functions.
Unsnapped arbitrary angles remain outside this admission even if a separate
bounded geometry implementation is present.

Strength must be zero, channel absent, global grade scope, scale one and output
sharpen zero. Active/unaccounted people, body, repair/light, local masks/groups,
geometry fields, backgrounds, source-bound retained background records, extended
tone, photo detail, grain, continuous colour editor and fringe processing are
outside this cohort. Unknown fields and compiled/foreign records fail closed.
CustomCube immutable storage can be counted before copying, but its distinct
parser/runtime is not admitted for optimized rendering; its recipe stays intact
for legacy dispatch. Ordinary CubeLut CPU backing and conversion/upload copies
are both charged.

The existing neutral policy is reused on a shallow diagnostic dict with only
allowed colour/geometry fields replaced there. No real snapshot, spec, slider,
effect or graph is rewritten. Strict neutral people candidates must additionally
pass the independent true-source/document census proof in the common renderer.
The private source context alone never authorizes skipping people preparation.
Retained semantic-colour masks and groups are rejected structurally before their
validator can unpack a legacy embedded mask. The postbuild inventory permits
only the audited null common-recovery and sky bookkeeping fields, not arbitrary
private prepared owners or prepass modes.

## Named phases and lifetime assumptions

N is true source pixels, M output pixels, C integer crop pixels, O encoded
original bytes, I ICC bytes, R retained state/snapshot/spec storage. The halo tile
is T = min(H, 1024 + 2m) * min(W, 1024 + 2m), with the existing margin m including
the actual radii even when smoothing strength is zero. Tile size is not tuned.

- Snapshot validation includes four largest-retained-array byte masks and fixed
  metadata/landmark scratch. Retained producer masks may be full resolution.
- Header/read includes two encoded owners, retained capture owners and parser
  reserves. The capture owner must perform its read reservation before reading.
- Decode/ICC includes three encoded owners, 64N decoder/working overlap, actual
  codec workspace, profile overlap and native reserve. The decoder's own
  availability guard remains unchanged.
- Common render includes full integer source (3N RGB8 or 6N RGB16), stitched RGB
  12N, conservative 512T colour workspace, LUT upload copies and reserves.
- Integer crop/quarter turn includes source, stitched backing 12N, crop 12C,
  output 12M and the last retained export RGB tile 12T.
- Whole-frame native colour finishing retains source and stitch backing 12N,
  input/output 24M plus conservative validation/contiguity/return reserve 36M,
  the last tile and named native reserve.
- Transfer assumes render-only owners have ended, but preserves caller-owned
  persistent state, original/ICC, the actual possible 12N RGB crop backing,
  private RGBA 16M and bounded staging 48B, B <= 65,536 pixels.
- Immutable freeze requires both mutable and immutable canonical buffers, 32M,
  after every RGB and row alias is released. Validate/intern keeps 16M plus
  bounded scratch. Immutable byte aliases are not additional payload copies.

PNG 1/2/4-bit provenance is preserved while its genuine working RGB is accounted
as uint8. PNG16 remains uint16. Working-decoder and canonical orientations must
agree even on square images. Genuine decoding still proves opacity, precision,
full dimensions, ICC semantics and original provenance. Eligibility alone does
not prove any of those pixel facts.

## UNRUN coverage and acceptance work

The companion admission fixtures cover combined colours, real common-spec
construction, no-mutation checks, unsupported/unknown/dormant families, private
prepass/prepared fields, skipped effects, complete backing ownership, byte
identity versus equal content, baseline exclusions, FacePrecompute arrays,
per-face planned copies, hostile unknown objects, cycles/subclasses/stride tricks,
CubeLut residency, actual halo radii, exact budget boundaries, native finishing
with a small crop retaining large backing, low-bit PNG, PNG16 decode overlap,
orientation disagreement and persistent state through freeze.

They are authored specifications, not executed evidence. See [INTEGRATION.md](INTEGRATION.md)
for the recovered slice's actual integration boundaries and verification limits.
Separately authorized future runtime acceptance must include:

- Execute the admission, neutral-census, sink and integration fixtures, including
  real common-spec construction, unsupported-recipe fallback and retained-owner
  lifetime cases. Record failures and the exact tested revision.
- Compare optimized output numerically against the unchanged legacy export for
  individual and combined admitted edits, crop/quarter turns, native finishing,
  ordinary CubeLut, JPEG and PNG 1/2/4/8/16, ICC and orientation fixtures.
- Verify genuine decoder opacity, precision and original-byte provenance; test
  cancellation, file/document races and failure cleanup without publishing a
  partial asset or silently dropping an edit.
- Review representative photographs at full resolution, and measure throughput,
  allocator peaks and process RSS through decode, render, transfer and immutable
  freeze, including large crop backing and persistent raw analysis/context banks.
  Include 24 MP cases and budget-boundary rejection; no such acceptance or hard
  RSS bound is claimed by the static ledger or authored fixtures.
