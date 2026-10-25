# Manual root/tip hair-colour unification: connected source, acceptance UNRUN

Baseline: `050508e0d3c75681f17a77834221f62e52579eae`.
Full-source measurement correction baseline: `e68481eadb66c70b33f6271b1780c529b3f8c501`.
Exact requirement: `LNX-REF-PC-32472-C-fb2fe59a22`, preserved `control:PC-32472:13`.
The [official guide](https://www.pixcakeai.com/guide/32472) specifies negative/left
referencing hair ends and positive/right referencing roots. It does not publish
its numerical algorithm, range, reference detector or targeting implementation.

## Actual implementation and ownership

An independent `lnx.hair_unification.v1` recipe uses an original signed [-1,1]
amount. Existing palette/gloss recipes and their numerical implementation remain
unchanged. This is a manual-reference partial implementation, not learned AI,
automatic root/tip detection, a vendor-equivalence claim, or full PC-32472 acceptance.

The person first needs the existing explicitly reviewed hair ownership and actual
retained hair-class evidence. They paint source-normalized root/tip samples, confirm
ownership, and inspect a complete actual before/after render plus sample overlay.
Sample roles are not inferred from the upper/lower image, face location or hairstyle.
The chosen nonzero sample footprint is excluded exactly from this operator's target;
all other reviewed hair of that person is eligible. Its boundary is not promised
seamless. References and samples never transfer automatically to another person.

Reference statistics are measured on the immutable effective source before repair
or portrait corrections, not a claim to match the final edited reference hair.
Original Rust full-source robust chromatic measurement is separate from bounded
current-pixel tile application. Current linear luminance is retained, including
prior edits; no old source RGB delta is added, no spatial RGB blur, no new strands,
no independent channel clipping. Brightness-only colour differences, bleached or
clipped hair, mixed illumination and ambiguous samples remain real limitations.
The new stage follows existing hair colour/gloss and precedes the single people
geometry sampler. Combined palettes need not equal the untouched reference RGB.

### Ordinary preview reference correction

Independent source review after the initial capture found that ordinary preview
passed its RGB8 proxy into measurement, while full review/export used full pixels.
The follow-on source slice removes that inconsistency: ordinary preview lazily
decodes the authenticated immutable source at native precision for fitting.
Original-file export uses the same fit decoder independently of output precision
(including existing RAW8 delivery); derived export uses its canonical full float
source. RGB16 ICC conversion is performed once by the existing shared decoder
contract. No original source, old delivery decoder or old effect recipe is changed.

The fit retains full-source dimensions and sample statistics. A separate explicit
application-grid native entry accepts authenticated full or ALIGN=8 whole-source
preview grids; it does not resize/relabel the reference. Application coverage is
reconstructed on that grid, with all retained neighbouring ownership checked.
If the selected protected sample vanishes on an excessively reduced display grid,
preparation refuses rather than quietly treating it as editable target hair.
Full-source sample measurement and old compose entry function bodies remain
unchanged. Display resampling/quantization and other preview-stage differences
still preclude a claim of complete preview/export pixel parity.

Full decode/fitting and application-grid residents are separately budgeted; the
source buffer is released after preparation, not embedded into history or kept
as a permanent preview cache. This may decode repeatedly and can refuse large
images under the actual budget. Performance/24 MP support is not established.

## Shared integration map

- `people_algorithms`, `people_effects`, `people_pipeline`, `vram`: independent
  recipe registration and one current-source stage; sole native numerical core.
- `people_render_runtime`, `people_engine_runtime`, `people_owned_inputs`: all-face
  preparation with exact independently retained sample/hair evidence banks and
  remaining working-set admission, original and derived source inputs.
- `people_host`, `virtual_copy_people`, `full_candidate_render`, `project`:
  append-only sample bank, strict historical reference validation, candidate graph
  plus bank staging without live mutation, project/history and frozen export.
  Old contexts admit an absent bank only as empty; unresolved references refuse.
- Dedicated controller and native mailbox: exact request/action/context/payload,
  actual image hashes, presented acknowledgement and single-use commit evidence.
  The controller owns exactly one canonical history transaction; generic dispatch
  does not create a second one. Unknown writes retain the original request.
- App-lifetime UI owner, actual source sample painting and exact image inspection;
  no active generic scalar patch behind the review. Missing core capability is
  unavailable, while supported neutral clearing does not require this new native
  core or new sample measurement. Existing source/other-effect analysis remains
  mandatory; neutral clearing is not a bypass for unavailable baseline evidence.
- Recovery remains reachable inside the workflow guard, including engine restart
  and explicit saved-project selection with discard-unsaved confirmation. Only
  native-confirmed actual project reopening permits explicit retirement of the
  old UI lock, preserving its unknown receipt and draft archive. Timeouts, a
  changed selection and merely sending a reopen request never release it.
  The in-process unknown archive is bounded at 32 entries / 16 MiB and does not
  promise survival across application restart; reaching capacity retains the lock.
- Encoded read-image receipts have a 32 MiB retained budget and exact-ID no-write
  tombstones; 1024 admitted identities refuse further requests rather than erase
  replay protection. This is bounded session capacity, not unlimited operation.
- Packaging sources include the Rust implementation, header, GPL licence and
  numerical contracts. The build script was not executed.

## Explicit incomplete work

Current-photo independent ownership only. Persistent cohort, shared-source aliases,
preset/batch activation and automatic reference selection remain refused where
complete target-owned evidence/review does not exist. Manual samples are immutable
source-owned assets, not transferable scalar parameters. A dedicated contribution
recovery brush is not implemented in this slice; neutral reset and canonical undo
remain distinct. Display images are bounded RGB8 views, not high-bit or native-size
inspection. Model evidence is not person-instance segmentation or source-pixel
perfect hair edges. Retouch HDR/alpha limitations remain unchanged, without clipping.

Every build, test, typecheck, numerical parity, image quality, UI, cancellation,
crash, history/reopen and performance acceptance is UNRUN. Static source review and
AST/JSON/hash checks do not establish photographic quality or ordinary 24 MP capacity.

The independent `core/skin_reference_match` parallel lane is not part of this
family's freeze and is not represented as a user-facing completed capability here.
