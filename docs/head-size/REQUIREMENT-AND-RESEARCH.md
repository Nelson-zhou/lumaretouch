# Small head including hair: exact scope and primary evidence

Baseline `b62028f82ea969b06aa5015a1583c4a7e383b6b1`.
Requirement **LNX-REF-PC-32473-C-dc1b0ba40a**, 小头, remains **PARTIAL / UNRUN**.
This is a new material geometry operation, not a new count for each transport.

The original AI development package maps this ID to PC-32473. The historical
body audit identifies complete head/hair resizing as missing. Current source
reconciliation distinguishes it from `lnx.face_size.v1` (measured facial contents)
and neck length (rigid complete-head transport). Torso/waist length are already
source-connected and are not counted again as missing by this slice.

The [official mobile body guide](https://www.pixcakeai.com/guide/125979), read
2026-10-24, section 小头 explicitly includes hair in head-size adjustment. This
corroborates the scope, not an official numerical range, pivot, gain or kernel.
The [desktop guide](https://www.pixcakeai.com/guide/32473) timed out on the same
read; no inaccessible desktop text is represented as newly verified.

The [MediaPipe Pose guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)
describes actual pose observations. Pose landmarks do not supply a complete
hairstyle outline. Existing measured head/shoulder points are evidence of visible
observations only; neither a face oval nor ear/nose coordinates fabricate hair.
The user must independently mark the complete head/hair box, scale center and
outer transition on the genuine effective-source reference.

[OpenCV geometric transformations](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html)
explain destination-to-source mapping and the distinction between coordinate
transforms and interpolation. [ITK's inverse displacement documentation](https://docs.itk.org/projects/doxygen/en/stable/classitk_1_1IterativeInverseDisplacementFieldImageFilter.html)
provides mature context for iterative inverse fields. Neither is copied or used
as a binary dependency. The new compact quintic affine field and contraction
bound are original local mathematics; they do not claim ITK algorithm parity.
Existing project one-pass image sampling remains the sole sampler.

## License and honest applicability

New source is original GPL-3.0-or-later work within the project's existing
license. No third-party implementation, model, weights or imagery is downloaded
or incorporated. Existing pose/face model ownership and installed-code licensing
remain unchanged; no new model compatibility is claimed.

Only visibly complete, near-upright, isolated head/hair with enough clear
transition above the measured shoulders is admitted. Long hair crossing the
shoulders, contact, hats/occlusion, cropped hair or ambiguous ownership can
refuse. The user is not offered a false face-only fallback. Background and neck
pixels inside the smooth transition can move. This is manually reviewed 2D
geometry, not learned body shaping, anatomical measurement or reconstruction.
Numerical, compiler, image-quality and runtime acceptance remain UNRUN.
