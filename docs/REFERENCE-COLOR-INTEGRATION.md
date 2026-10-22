# Same-scene reference white balance / brightness

Status: integrated source implementation, **not runtime, image-quality or feature acceptance**.
No test, compiler, build, product import, inference, installation or model download was executed in this work.

## Exact requirement and honest scope

- Handbook/control: `PC-32455-C-53da929b74`, `LNX-REF-PC-32455-C-53da929b74`, 多图色彩统一.
- Baseline handbook text: `baseline_probe/manual-text.txt` around line 604. Acceptance mapping: `AI开发资料包/功能需求验收映射.json` around line 7147, P1 research / dedicated cases pending. Existing `COLOR-001` association is **not** evidence that reference matching was already implemented.
- Current official equivalent: https://wiki.pixcakeai.com/guide/9398.html . Reference uses the current edited photo's white balance/brightness; selected other photos change, reference stays unchanged; similar scenes are recommended, colour adjustment should be late; whole-group undo/redo is specified. It does not specify a required neural architecture.
- Separate AI追色 guide https://www.pixcakeai.com/guide/32452 describes semantic skin/hair/lips/sky and editable precise masks with per-photo recomputation. This change does **not** implement or claim that semantic creative colour-transfer product.
- Existing manual WB, exposure, HSL, curves, LUT and generic parameter batch remain intact. None is relabelled as reference matching.

## Primary implementations considered

1. OpenCV 4.12.0 exposure compensators: https://raw.githubusercontent.com/opencv/opencv/4.12.0/modules/stitching/src/exposure_compensate.cpp . Real overlap/similarity support and fixed/channel gain reasoning are relevant. Its direct `uchar` source access is not a full RGB16 implementation to transplant. Algorithm design evidence only, not copied implementation.
2. OpenCV feature/homography guidance: https://docs.opencv.org/4.12.0/d1/de0/tutorial_py_feature_homography.html . ORB reciprocal descriptors, robust geometry and corresponding image patches are used through the already-pinned OpenCV runtime. No new dependency was installed. Repository runtime pin remains `opencv-contrib-python==5.0.0.93`; runtime compatibility remains unexecuted, not inferred from the 4.12 source review.
3. OpenCV license https://raw.githubusercontent.com/opencv/opencv/4.12.0/LICENSE is Apache-2.0; older exposure file retains its BSD-style Intel/Willow Garage header. This package does not copy that file or ship new weights.
4. Colour v0.4.6: https://raw.githubusercontent.com/colour-science/colour/v0.4.6/colour/adaptation/vonkries.py and https://github.com/colour-science/colour/blob/v0.4.6/LICENSE , BSD-3-Clause. Cone-domain white-point adaptation is not the same as this empirically fitted linear-RGB diagonal. No claim of Bradford/physical illuminant estimation and no copied implementation.
5. darktable manual https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/color-mapping/ and inspected master `src/iop/colormapping.c`: GPL-3.0-or-later Lab cluster/histogram colour mapping. Mutable master was evidence only; attempted release paths were unavailable. Not a pinned vendored implementation and not scene-illumination parity.
6. RawPedia image-editor automatic matching is RAW versus its own embedded JPEG, not cross-photo scene consistency. It is not counted as this requirement.

All new Rust/math glue is original GPL-3.0-or-later project code. It reuses the project's `core/curves/curve.rs` sRGB decoding. There are **no new model weights**, no model-license conflation, no hidden image upload or runtime network/build fallback.

## Actual algorithm and retained limitations

- Full original RGB8 or RGB16 decode into the actual edited float pipeline, including existing effects, automatic common geometry, manual liquify, optical mapping and crop. No proxy/camera-preview substitution. Export-only upscale/sharpen is excluded from reference sampling, as it is not part of the displayed edit recipe.
- Reference is immutable and preserved as a locally content-addressed lossless float32 NPZ with its authentic-scene mask, source SHA/dimensions, document/revision, candidate state and rendered/mask digests.
- Targets are rendered without their previous reference correction, preserving manual WB/exposure/curves and every other existing edit. A new target-owned correction replaces only `_reference_color`.
- ORB uses bounded 1400-pixel grayscale proxies **only for correspondence**, masked to retained authentic support. Reciprocal ratio-tested matches, spatial deduplication, robust homography, at least 64 correspondences, at least 65% geometric consensus, at least 6/16 grid cells and 15% convex-hull area are required.
- Actual RGB photometry samples full-float corresponding 5×5 patches. Every sample must lie in authentic support in both frames. Rust computes robust per-channel log2 linear-RGB ratios; rejects clipped/dark samples, requires at least 64 photometric inliers and 65% agreement, bounds gains to ±2 stops. Coverage is checked again on the **photometric** consensus.
- No histogram/global-average fallback. Changed clothes, changing foreground proportions, wrong scene planes, similar/repeated textures, subject movement, mixed illumination and depth changes are material quality risks. A homography and broad coverage do not prove semantic identity or all-scene consistency.
- Review reports per-channel stops, residual P90, consensus, geometry/coverage, retained-scene fractions, deterministic sampled new output-gamut overflow, warnings and strength. More than 5% sampled new overflow refuses; this diagnostic is not a full-frame clipping proof.
- Current-rendered original-scene support is **not unedited illuminant evidence**. Manual grades or sky environment tint can alter real scene pixels; UI/receipt explicitly states current-render matching, not original-light measurement.
- RGB8/16 and float transforms share extended sRGB equations; float HDR/sign are retained; integer output quantizes only at the appropriate final endpoint. Zero strength/zero gains are exact no-op paths. Original-resolution export and accurate inspection include the stage.

## Authentic support producer

`reference_color_provenance.py` uses actual retained application evidence, never a missing-mask all-ones fallback:

- Source-grid interior is initialized only after full-state/full-source admission. True image boundaries are excluded.
- Heal, source-patch and clone use their actual replay planners' conservative written ROIs. Source-patch feather outside the recorded brush cannot masquerade as original scene. The ROI bound may discard valid pixels, but never certifies them as authentic.
- Prepared studio effect fields and complete operator recovery exclude actual changed regions before geometry.
- `pipe.align_source_grade_mask` transports support through exactly the existing shared `M(E(N(B(A(x)))))` grid. No second independent face warp was added.
- Retained sky/person/water/recovery fields exclude replacement material after the same common warp. The water exclusion is conservative relative to horizon. Existing full-background matte follows the same alignment condition as its actual consumer; complete verified background recovery is respected.
- Manual liquify uses its real prepared warp; optics uses actual per-channel coordinates without vignette photometric gains; crop/rotation uses the actual geometry operator. Coverage after interpolation must remain effectively 1.
- Unknown generation layers, missing footprints, suspended masks or insufficient remaining match support refuse. An enabled, composable sky/background/repair layer alone is not a blanket refusal.

Future multi-person integration must replace the common support-transport hook coherently with the same all-person RGB/mask geometry. It must not borrow another face's support or use editing selection as final render scope.

## Reachable application and workflow integration

- Gallery `ReferenceColorControls`: current displayed image is the reference, selected other images are targets; strength, explicit preflight, frozen per-target diagnostics, commit, whole-group undo and redo. Reference is excluded server-side as well as in UI.
- Existing `batch_api`/epoch-bound receipt host and `useBatchWorkflow` are extended, not bypassed. Uncertain outcomes stay queryable; no blind mutation retry.
- Frozen preflight includes the actual per-target fit and source/render/candidate identities. Commit rechecks target revision, source content, candidate fingerprint, frozen proof and local reference asset. A newly captured reference's original file and source revision must also remain unchanged. No source-fitted gain is portable to another target.
- Dedicated UI uses all-or-none `recheck`. Batch scope can also skip-and-report through existing review. Reference whole-group history is all-or-none on conflict and restores only owned fields, preserving unrelated later manual work.
- Presets carry reference intent/strength only. Applying them calls target-owned rendering/correspondence/fitting through the existing frozen preset review. No old target gain is reused.
- Local preset JSON references the retained local asset. Cross-machine standalone preset packaging with an accompanying reference bundle is **not implemented**: an imported preset without its retained asset refuses. Projects carry deduplicated bounded reference chunks and are the portable reference-asset route; existing total project budget still applies.
- Project/state/history capture includes recipe and lossless reference bundle. Missing retained reference assets refuse rather than silently save an incomplete match. Shared server workflow ports were genuinely extracted to `workflow_ports.py` to retain the line cap.
- Scope registry extension, native DTO, readiness protocol, RGB16 direct-export blockers, original export, accurate inspection and packaging hooks are included. `reference_color_protocol=1` indicates the protocol exists, not that a missing packaged Rust/OpenCV dependency or a photograph has passed acceptance.

## Remaining acceptance work, not performed here

Qoder must run authored fixtures and integrated application checks, then real-photo comparisons: source/target selection, zero exactness, RGB16 near-level preservation, crop/optics/manual/common-warp agreement, mixed synthetic and authentic support, repeated texture, changed composition/clothing, mixed lighting, rejected low support, cancelled/expired/stale review, reference invariance, native missing dependencies, source replacement, project round-trip/corruption/budget failure, preset recomputation, whole-group conflict/undo/redo, manual-edit preservation and export/preview agreement.

Full standalone cross-machine preset asset packaging, semantic creative AI追色, calibrated illuminant estimation and nonplanar all-scene consistency remain open. No runtime or photographic success is claimed.

The exact source manifest is `docs/reference-color-manifest.json`. It deliberately excludes the other worker's isolated `people_*` package.
