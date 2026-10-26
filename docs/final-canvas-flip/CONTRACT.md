# Original-photo horizontal / vertical reflection

**Source implementation; all runtime acceptance UNRUN.** Handbook `PC-32478:21`
(horizontal) and `PC-32478:22` (vertical). Operation `lnx.final_canvas_flip.v1`.
This is not sky-only, creative-layer-only, viewport CSS, anatomical left/right,
or a destructive rewrite of the original.

## One processing → final boundary

`_final_canvas_flip` contains exactly JSON booleans `horizontal` and `vertical`.
Missing old state means false/false; explicit null, extra fields and integer/string
booleans reject. Existing `lnx.crop.v1` schema and crop/rotation math are unchanged.

`final_canvas_output.processing_to_final` is the sole reflection implementation.
Rust copies packed RGB sample bytes to a disjoint output: u8/u16/f32, with an
additional f64 permutation ABI for explicitly typed callers. No quantization, arithmetic, masks,
landmark edits or original-file mutation occur. Neutral returns the input object
before importing numeric/native dependencies. Nonneutral missing ABI, unsupported
layout or memory refusal fails explicitly; no hidden build, fallback or downsample.

Preview `retouch()` remains processing-domain; image-stream delivery also adapts
its final tensor before packing. `PreviewPipeline.render()` reflects
only after the full suffix, including any original-source replacement callback.
`photo_grain_runtime` requests processing output for `pack=False` callbacks and
final output for direct packed previews. Original comparison bypasses this adapter.

Public export APIs have explicit `output_domain='final'|'processing'`. The internal
renderer defaults to processing so exposure/tone prepasses cannot flip. At final
output, reflection follows crop, reference/semantic colour, grading, detail,
fringe, grain and extended-tone finishing, then precedes quantization. Active flip
uses the existing full-source delivery route for resize/sharpen: source edit →
reflection → delivery resize/sharpen → writer watermarks/ICC/metadata. RGB8,
PNG16→RGB8, RGB16/TIFF16/RAW routes carry the same recipe. RGB8 deferred geometry
and inspection are forced through internal crop before reflection. ROI slices the
already reflected canvas. Complete candidate review receives reflected pixels.
NumPy arbitrary-angle geometry interpolates in f64; the export adapter explicitly
returns normalized f32 before every finishing stage (including neutral detail
validation), matching the existing processing/native ABI. This boundary is floating
rounding, not 8-bit quantization; final u16 quantization remains after reflection.
Legacy crop recipe/math are not modified. Scale/crop rounding incompatibilities
retain their explicit refusal rather than inventing another canvas.

Source evidence/provenance is always processing-domain. Reference, semantic-colour and optical analysis explicitly
request processing output; active-flip final output refuses a provenance tap.
No semantic/optical/support source identity or anatomical parameter is reflected.
The narrow grading-prefix optimization is excluded while flip is active.

## Ownership, history and persistence

The native/UI command supplies desired booleans and the exact load-document ID and
revision, never a replayable toggle. Engine command registration, state inventory,
fresh/capture/apply, pipeline attachment, snapshot/spec, badges and native command
registration are connected. Each changed accepted command renders before recording
one non-coalesced history step and advancing the fence. Every request has a retained
bounded identity and exact original document/revision/desired-state receipt. An exact
replay returns its original receipt without writing; a new request with stale binding
rejects. Queue ACK is never success. Native receives bounded duplicate-key-rejected
JSON and validates epoch, original request, terminal phase, recipe and resulting
revision before settling its existing recovery fence. The crop/spec controls share
one session-retained pending owner; errors are visible, unknown stays query-only,
and neither unmount nor a matching-looking frame unlocks or resends the edit.
A synchronous native admission failure for a fresh reserved request ID is an exact
`not_sent` terminal: this unkeyed dispatch path returns errors before queue push;
asynchronous OS transport loss after queue admission is still unknown. Duplicate
IDs only replay; a later failed invocation cannot relabel an earlier queued request.

Unknown has a bounded recovery escape, not a timeout unlock. After the queue is idle,
an explicit UI action may abandon only the old wait when native proves a different
engine epoch or a later verified project-open/create event. The old outcome stays
`unknown`; no success, recipe change or resend is invented. Reset generation is
anchored only on an explicit unresolved-request status query after admission finishes
and the native queue is idle. The query observes idle first, then reads the reset
generation: earlier buffered opens precede the FIFO command_done that establishes
idle, so an earlier reset cannot authorize abandonment. A same-epoch reset must be
verified after this baseline. If the native mailbox was lost, status reserves the old
identity (late invocations cannot send it), observes its own idle baseline, and requires
a later reset or subsequent epoch replacement. An offline orphan is not treated as a
known old engine. A known retained terminal remains queryable across epoch changes.
Native not_sent settlement has a bidirectional event-family/original-command guard;
a colliding request ID cannot settle or suppress another owner's real receipt.

Render failure restores recipe/history/dirty flag and edit-time metadata. Known
rollback requires a full captured-state/history hash, matching pipeline recipe and
unchanged document revision; any unproved rollback (including partial fence advance)
is unknown/reload-required. Recovery uses private host no-write/applied/rolled-back/
unknown facts rather than wire success flags or generic exception handling, so stale,
missing-native and proved-rollback refusals do not permanently taint autosave. A
terminal delivery failure after proved commit remains applied, not a fake rollback.
Old undo snapshots missing the field explicitly restore neutral rather than inheriting
current active flip. Rendering-only frames preserve the same document recipe.

Project writer is v24: old readers reject instead of dropping an unknown active
recipe. v23 remains explicitly accepted for all its existing features and strict
logical/virtual-copy identities; identity migration is only pre-v23. Recursive
validation covers active/inactive versions and undo/redo. The portable package
inventory accepts v23/v24. Ordinary save retains inactive versions and referenced
assets, preserving active version names, under the existing project-size ceiling.
Neutral state signatures, full candidate fingerprints and frame presentation hashes
omit only strictly validated neutral flip; active flip changes final view identity.

## Deliberately unavailable while active

No claim that all coordinate tools compose. Version-1 crop/rotation projection has
no reflection inverse, so new source-patch/clone/heal/local-mask/recovery/liquify,
WB/colour/ID/editor sampling, fringe review/paint, ID spill/shadow paint, portrait
crop and raw main-canvas mask/light/face placement are refused at backend admissions.
UI gates captures and hides/disables guides without discarding their state. Existing
source-bound recipes still render before the final reflection. Scalar edits remain
available where they do not require a new capture. Close flip to capture, then restore
it. Generic presets/batch transfer do not add this operation, and an active flip is
not silently copied onto an unrelated bare export source.

Creative current-edited-asset capture refuses nonneutral flip before decode or bake:
its bounded late/deferred-crop allocation path has not been integrated for reflection.
Neutral new snapshot/spec fields are explicitly accounted for in strict capture
inventories, so this restriction does not disable old neutral creative workflows.

## Verification boundary

Only static Python AST parsing, JSON parsing/hash inventory and whitespace review
are permitted in this task. No product imports, builds, tests, typechecks, installs,
downloads, inference or real-image runs were executed. `test_final_canvas_flip_unrun.py`
and Rust tests are authored cases, not test results. See `ACCEPTANCE-UNRUN.md`.
