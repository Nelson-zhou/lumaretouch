# Independent source-patch tool

Status: implementation assembled; remote CI and physical acceptance are separate gates.
This document is not a claim of a tested release or an installed desktop update.

## User path

Retouch → local tools → independent source patch. Start a frozen repair-input view,
lasso the defect, drag the same-shaped donor region, then explicitly apply. Escape
before submission discards the selection. A submitted request is resolved by its
original receipt, never resent automatically. Global history provides undo/redo;
project v3 retains both stacks and normalized source geometry. Full export replays
all heal/patch operations in order from the full-quality source.

The sampling view includes earlier repairs, but deliberately excludes smoothing,
lighting, deformation and grading. Existing crop/rotation remains visible. This
is labelled in the UI: selecting an apparent final deformed pixel as if it were a
pre-deformation source would be incorrect. Rotation padding is not usable source.

## Reuse and boundaries

The patch algorithm adapts Chris Cork's RapidRetouch patch/filter implementation,
pinned to 5e9d9c1d2770ff29d11a3879e5a90aad5887e028:
https://github.com/crispin81/RapidRetouch

Linear-sRGB source texture is combined with surrounding target lighting. This is
not a renamed spot-heal button, generative fill, or an 8-bit/JPEG patch cache.
The local source/target ROI crosses to the CPU; float32 results return to the
resident tensor. Full-resolution export reruns the same algorithm, rather than
upscaling a preview. Proxy/full render parity at different image sizes and real
photographic quality remain physical acceptance work.

Existing project/history/render/export mechanisms remain authoritative. New modules:
- sourcePatch UI: pointer interaction and persistent result ownership.
- Rust source_patch_*: proof-bound commands, bounded receipt ownership, private frame copy.
- source_patch_capture/geometry: repair-input view, geometry inverse, one-shot proof.
- source_patch_controller: prepare before mutation fence, transaction and rollback.
- repair_record/repair_replay: versioned mixed replay shared by preview/export.
- ops/source_patch: bounded float algorithm and tensor ROI adapter.

The capture is a separate private LRCP file, not the display shared-memory slot.
Native acknowledgment binds the frame, document, recipe revision and one-shot
selection. A failed algorithm does not publish a partial repair. A failed render
attempts rollback; failed rollback requires reload rather than claiming success.

## Runtime and license

No model weights or online inference required. The packaged runtime installs the
same opencv-contrib-python==5.0.0.93 distribution already pinned for face analysis;
multiple competing cv2 wheels must not be installed together. An existing runtime
needs its normal setup update; merely replacing UI files cannot add this dependency.

Derived algorithm files retain AGPL-3.0-only. Upstream notice, source revision and
full license ship under lumaretouch_engine/third_party/rapidretouch/. Existing
unrelated GPL-3.0-or-later files retain their terms. The combined distribution must
also satisfy the applicable AGPL interaction/source obligations; per-file notices
are not an exemption. GNU compatibility reference:
https://www.gnu.org/licenses/gpl-faq.html#v3Notwithstanding

## Verification gates

CI definitions include float algorithm, receipt/rollback, mixed replay, project
migration and ownership tests; frontend
workflow/geometry/integration tests; Rust capture/receipt/private I/O tests.
Do not equate test definitions with passing results. Record the exact CI commit and
run after completion. Coordinate inversion and Python capture lifecycle still need
focused automated coverage in the consolidated verification phase. Real GUI, GPU behavior, source edge cases, memory peaks and
photographic output quality must still be checked locally by the authorized tester.
