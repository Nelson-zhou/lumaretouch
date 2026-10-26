# Optional hand proposals — source-only integration

Status: **AUTHORED / UNRUN**. No model has been installed or retained by this
work, and no MediaPipe import, inference, build or runtime test has been run.
Hash observation below is evidence about exact asset bytes, not model quality.

## Primary evidence and observed pin

- [Official guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)
  describes the palm-detector plus 21-landmark bundle.
- [Google repository versioned example](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/web/vision/README.md)
  names the `float16/1` asset, rather than relying on the mutable `latest` alias.
- [Official model card, page 2](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf)
  states Apache License, Version 2.0. The card describes both Lite and Full hand
  tracking pipelines. [Producer code](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/hand_landmarker.py)
  is separately Apache-2.0 licensed. Code licensing is not substituted for the
  model-card evidence.

Exact URL:
`https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`

Observed 2026-10-25 by an authorized HTTPS streaming hash-only read, refusing
redirects and imposing a 16 MiB cap:

- bytes: **7,819,105**
- SHA-256: **fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1**
- no file retained, no deserialization, no installation, no inference

This is a locally observed digest of Google-hosted bytes, not a Google signature
or a claim of independent scientific validation. Do not replace the pinned URL
with `latest` or assume that another archive is byte-equivalent.

## Distribution/runtime boundary

`hand_shape_model.py` is offline. It contains no downloader or package installer.
The explicit hand-panel installer (see [SETUP-UNRUN.md](SETUP-UNRUN.md)) can acquire the exact fixed official artifact with resume, full hash/size verification and a generated-image CPU capability probe. No automatic dependency installation is supplied. An authorized distributor can alternatively provision the exact pinned regular file
at `$XDG_DATA_HOME/lumaretouch/optional-models/mediapipe-hand-landmarker-full-float16-v1/hand_landmarker.task`
(`~/.local/share` if XDG_DATA_HOME is unset), together with applicable Apache
license/attribution notices. A supplied `model_root` changes only this explicit
local file location. It is not a request for network acquisition.

The optional runtime must use the existing reviewed packaging channel,
`engine/requirements-mediapipe.txt` (currently MediaPipe 1.1.1), not an automatic
`pip install`. Final distributor dependency and bundled-component license audit
remain governed by that channel. The hand adapter does not certify an entire
transitive dependency lock or relax its existing release approvals.

Before use, the adapter rejects symlink paths/nonregular files/changed files,
checks exact bounded bytes and SHA-256, and passes that very byte buffer to the
backend. It records the actual installed runtime version and the SHA-256 of the
actual loaded `hand_landmarker` Python source file. That source hash is provenance,
not a certification of every native runtime binary. Status checks installed bytes plus a current explicit CPU capability receipt, bound to the selected runtime identity. A manually provisioned file also requires an explicit CPU recheck before proposals are enabled; `inference_verified` remains false because this is not photographic acceptance.
Missing model/runtime or a changed runtime version is an explicit unavailable
state, never a synthetic/"AI" fallback.

## Proposal semantics and visible anatomy

The host supplies immutable, whole-frame canonical RGB8 analysis pixels (full
source or canonical aspect-preserving decoder proxy), not a retouched display
image. Proxy inference does not replace the full-resolution render source. The
adapter uses CPU IMAGE mode and records the exact input hash/dimensions. The
host must fence the source before and after inference and retain the actual
producer result; a client JSON blob or guessed points must not impersonate it.

Results have 21 actual output coordinates per detected hand and actual
handedness categories. Out-of-frame points remain unchanged. No per-point
visibility/presence is invented. Handedness is a model hint only, not established
left/right anatomy, identity, mirrored-image interpretation or ownership.

Every proposal requires explicit visible-point/support confirmation and, where
needed, correction against the current source. Hidden points must be excluded,
not reconstructed. No proposal automatically supplies finger thickness, joint
width, a silhouette, occlusion safety or a ready-to-apply deformation. Manual
support remains honestly labeled manual and does not become model evidence.

The model card identifies gloves, occlusions, held objects and hand decorations
such as jewelry as outside its intended reliability scope. These are **not
license prohibitions**. There is no automatic jewelry/occlusion detector here;
unknown visibility is not proof of visibility. A user must inspect each actually
used region and reject obscured/contact/ambiguous anatomy. A detector limit is a
resource cap, not proof that all hands in the photograph have been found.

The downstream Rust geometry is original bounded source-plane geometry. It does
not reproduce a commercial proprietary algorithm or synthesize a preferred hand
from demographics. The adapter provides no identity, medical or demographic
inference, and no scientific/photographic quality acceptance is claimed.

## Deferred local validation

Qoder/local validation remains responsible for pinned-model absence/corruption,
symlink/nonregular-file rejection, runtime mismatch, immutable source fencing,
CPU IMAGE proposal behavior, out-of-frame and occluded points, multiple hands,
handedness mirroring, stale proposal rejection, explicit correction, cancellation
and resource peaks. All such checks are **UNRUN**, including real-photo quality.
