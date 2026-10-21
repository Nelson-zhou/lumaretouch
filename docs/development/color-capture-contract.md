# Identified colour sampling — implementation contract, not completed functionality

## Why this precedes a point picker

Status data is not proof of displayed pixels. Normal SHM v2 metadata and 40-byte
preview IPC do not carry document/recipe identity; sequence numbers can restart.
LRI1 now identifies mapping instances and rejects in-place recreation, but does
not identify a photograph, recipe, or actual composed frame. The picker must not
map a click on old visible pixels into a newer document's recipe.

## First delivery: explicit frozen proxy-output capture

Keep ordinary preview/benchmark IPC unchanged. Add independent capture controller,
verified binary response and presentation layer, with one outstanding capture.

1. Arm validates current load token, resource guards and a bounded capture ID.
   Generate a native monotonic ticket; never rely on caller ID uniqueness alone.
2. An engine-owned producer generation increments before known potentially mutating
   commands. Conservative invalidation on rejected changes is acceptable. Read-only
   scopes/hello do not mutate it; no per-frame image or recipe hashing.
3. Arm renders the final proxy output once through the existing chain, publishes
   the exact full frame and a small descriptor: version, capture ID/ticket,
   producer generation, load token, SHM instance, seq, dimensions, view/domain and
   proxy quality. This command is not an edit or history entry.
4. Native validates the producer epoch and requested identity. Under the existing
   shared flock it copies only the exact instance+seq, never whichever frame is
   newest. If overwritten, fail and explicitly rearm. Ignore benchmark dirty-row
   and skip-pixels modes for this complete capture.
5. Return a separately versioned bounded binary frame carrying its full identity.
   Validate dimensions, checked byte arithmetic, exact payload length and reserved
   fields before constructing a browser pixel view. u64 identities are strings or
   BigInt, never JS Number.
6. Render frozen pixels in the existing body-portal `.mirrorClip`, after live/detail
   canvases, without changing the long WebGL effect. Keep pointer hit handling
   inside `.viewer`. Upload pixels once per capture; pan/zoom updates CSS geometry
   only. Do not reset canvas dimensions during navigation.
7. A dedicated hook gates pointer selection until the same capture survives two
   animation-frame opportunities and a native acknowledgement. This is presentation
   eligibility, not proof the user physically saw the screen. Cancel queued work
   and late continuations on real edit intent, document/workspace changes, Escape,
   comparison/refinement-mode changes and unmount.
8. Sampling carries the immutable capture identity and producer generation. Native
   rejects unacknowledged capture requests; engine rejects stale generations before
   sampling. Read producer float values through the same rendering recipe, not
   quantized canvas pixels. Return exact point or neighbourhood averages with
   working-sRGB/Lab-D65 provenance.

The initial frozen view is proxy-output only. Full-source/comparison and action-
specific eyedroppers are unfinished requirements, not removed scope.

## Module boundaries

- Engine capture controller: generation, descriptor and arm/cancel/sample policy
  via explicit document/guard/render/sample/event ports; never receives Engine.
- Native capture host: epoch, latest ticket, descriptor, copied/presentation-eligible
  phases, latest sample reply and invalidation. No renderer/project ownership.
- Native capture API/wire: exact locked copy and checked bounded framing.
- `colorSampleGeometry`: pure displayed rectangle → pixel/neighbourhood mapping.
- Independent capture hook: async identity checks, cancellation and request state.
- Frozen visual canvas + pointer overlay + readout panel: separate components.
- App/Viewer only pass narrow bindings and geometry; no new large global context.

## Interaction choices versus source requirements

The manual explicitly requires RGB/Lab readouts and level/white-balance/curve/HSL
related eyedroppers. It does not specify arbitrary rectangle sampling or a set of
neighbourhood sizes. Point sampling with 1×1, 3×3, 5×5 and 11×11 averaging is an
implementation choice, not a quoted requirement. A readout-only picker does not
complete black/white-point, white-balance, curve or HSL editing actions.

Map using the frozen capture dimensions and actual displayed rectangle. Reject
black margins rather than clamping an outside click to the border. Clip a chosen
neighbourhood at image edges and report its actual pixel count. Left sampling must
not also trigger brush, face selection, swipe or pan. Middle-button/wheel navigation
can retain the frozen capture; navigation-only inspection invalidation is not an
image edit. A transform change cancels an in-progress gesture, not the capture.

## Later full-source and comparison paths

- Full-source `inspectionLayout.rect` maps CSS to full post-crop coordinates.
  Alternatively map through patch→ROI. DPR has already been accounted for; do not
  multiply it twice. Require the exact delivered inspection identity, not only a
  current status key. Quantized detail-canvas data is not producer float data.
- Split uses two explicit pane domains; swipe resolves the side at the seam.
  Original bypasses edits and crop, so its coordinates cannot be treated as edited
  output coordinates. A neighbourhood crossing a seam must be rejected or analyzed
  as two independently identified regions.
- Full-source float readout must extend the existing bounded worker/recipe path,
  not allocate an unrestricted full-image browser buffer.

## Required verification

Same-size document switches; crop while an old frame remains visible; mapping and
seq reuse; legacy display-only frames; old producer epochs; overwritten captures;
late bitmap/RAF/ACK completion; edits queued during arm/sample; repeated IDs and
cancel/rearm; dirty-row/skip/ping-pong modes; pan/zoom and margins; neighbourhood
edge clipping; large u64 values; source-stage and comparison-domain mismatches.
No UI, sample or action is marked complete merely because this contract exists.

## Candidate implementation, 2026-10-21

The first implementation is an explicit frozen proxy-output point/neighbourhood
reader. UI ownership lives in colorCaptureController/useColorSampler; the visual
canvas is portalled into the existing mirror clipping layer. It preserves the
producer presentation aspect independently of fixed raster dimensions. Two RAF
opportunities and a native delivery acknowledgement gate input; neither proves
physical screen presentation. Pixel sampling rerenders the unchanged float recipe
and copies only the selected at-most-121 values to the Rust colour analyzer.

Static review corrected obsolete-request rejection handling, ImageData buffer
typing, and pointer-down identity across cancel/rearm. Basic CI/Qoder checks subsequently passed; see color-capture-verification-2026-10-21.md.
GUI/visual testing remains pending. No action eyedropper is marked implemented.
