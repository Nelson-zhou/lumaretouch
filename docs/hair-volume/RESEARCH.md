# Hair geometry research and licensing

Consulted 2026-10-25. Source reading and a local model hash/size check only;
no downloaded code/model, installed dependency, build, import, inference, test or
render was performed. New Rust/Python implementation is original
GPL-3.0-or-later code, not copied upstream deformation code.

## Preserved reference behaviour

[PixCake official hair-adjustment guide](https://www.pixcakeai.com/guide/32472),
page updated 2026-09-18, describes crown height decreasing to the left and
increasing to the right, plus side volume decreasing/increasing with an unlock
for independent sides. It does not establish exact ranges, defaults or the
algorithmic difference between its two crown labels. We retain the user-visible
directions and lock semantics as `control:PC-32472:2` and `:3`; our scalar scale,
gain, support proof and original algorithm are separate. Full-head shrink,
colour and hair generation are not substitutions for these requested controls.

## Actual semantic evidence

[Google MediaPipe multiclass segmentation model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Multiclass%20Segmentation.pdf)
describes background, hair, body skin, face skin, clothes and accessory/other
classes for image segmentation. It labels the model Apache License 2.0, and
warns that masks are not pixel-perfect and degrade under difficult light,
motion and occlusion. Hair pixels are semantic classes, not person-instance
ownership or crown/ear contour measurements. The model card is not evidence
that any arbitrary similarly named local bytes are the admitted model.

The actual existing local multiclass asset was independently size/hash checked:
16,371,837 bytes,
`c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`.
Existing `hair_colour_analysis`/`hair_colour_evidence` pins that source producer
and its real weight digest. Geometry uses it only as corroboration for manually
observed samples. Existing colour-support consent is not reused.

## Candidate geometric methods

The official [scikit-image piecewise-affine example](https://scikit-image.org/docs/stable/auto_examples/transform/plot_piecewise_affine.html)
illustrates control correspondences and a transformation/sampling pipeline.
The project's [licence](https://scikit-image.org/docs/stable/license.html) is
BSD-3-Clause for its general code, with listed per-file exceptions. Piecewise
affine is a useful research baseline, but triangle continuity alone does not
prove non-overlap or an exact globally invertible hair field. We neither copy
its example nor add its image sampler or dependency to production.

The official [OpenCV TPS transformer reference](https://docs.opencv.org/4.13.0/dc/d18/classcv_1_1ThinPlateSplineShapeTransformer.html)
describes fitting point correspondences and a regularization parameter.
[OpenCV licensing](https://opencv.org/license/) specifies Apache 2.0 for 4.5+
and BSD-3-Clause for older versions. TPS remains a research comparator, not a
production dependency of this family. Fitting swapped source/target points
does NOT generally calculate the exact inverse of a nonlinear fitted map;
regularization or point interpolation alone does not guarantee absence of folds.

## Chosen original method and limits

An explicit C2 tensor profile with measured/manual source support provides a
closed-form global derivative bound and bounded contracting inverse. Unlike an
arbitrary dense mask-weighted displacement, its spatial derivatives and compact
boundary behaviour are known. Crown and side axes remain distinct, fixed lower
and inner regions remain exact, and the same existing one-pass image sampler
consumes its inverse coordinates. No upstream model weights, example images,
commercial formulas or incompatible code are redistributed by this module.

The method's simple strip model is intentionally honest: complicated occlusion,
interwoven hair, contact with clothing or anatomy, clipped crown and unsafe
transition geometry require a different observed support or refusal. Numeric
invertibility is not photographic quality. Real-photo acceptance and all
authored UNRUN checks remain outstanding.
