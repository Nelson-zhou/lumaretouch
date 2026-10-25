# Selected same-photo reference core

Status: **AUTHORED / UNRUN**. Source-only implementation and unexecuted fixtures.
No build, import, test collection/execution, typecheck, inference, installation,
download, benchmark or real-photo acceptance was performed for this lane.

## Requirement and honest scope

Preserved public requirement: `control:PC-32465:19`, **AI多人肤色统一**.
[Official guide](https://www.pixcakeai.com/guide/32465) and
[official wiki](https://wiki.pixcakeai.com/guide/9404.html) describe using the
brightest face as reference, changing target face/body colour and brightness,
and leaving that reference face unchanged. The original hashed LNX mapping was
lost. This work does not invent a replacement mapping or mark that requirement
fully implemented.

The independent implementation scope is `lnx.skin_reference_match.v1`: an
explicitly user-selected **actual same-photo face reference**, with reviewed,
measured target face/body support. The Rust crate performs statistical fitting
and pointwise application, not selection, segmentation, identity inference or UI.
Automatic brightest-face selection and instance/body segmentation are absent.

The existing body-to-own-face operation is different: it matches chroma without
matching brightness. This crate neither aliases nor modifies it.

## Host preconditions

Before an active fit/application the host must establish all of the following:

1. Reference and target evidence comes from the same authenticated photo/source
   generation and declared working-sRGB-D65 SDR transform. Neither is a swatch,
   generated complexion, resized pairing image or unrelated library image.
2. The reference is the face explicitly selected by the user. Its coverage is
   actual reviewed usable skin evidence, not a rectangle/landmark proxy.
3. Each fitted target is an independently reviewed face **or** body region with
   authenticated owner and actual skin permission. Pooling unrelated people or
   face/body regions into one population does not resolve their individual match.
4. Effective apply support excludes the complete reference-face support and all
   unrelated/protected pixels. The numerical core cannot discover the exclusion.
   The reference face must remain bit-identical in host-level acceptance tests.
5. Review support, image/version, owner, colour-space, reference selection and
   source-stage changes invalidate cached fits. Application coverage is registered
   to the actual current pixel grid and never inferred from fitting coordinates.
6. A source fit is completed before render tiles are applied. Do not refit each
   tile, use preceding edited output as source, or update the transform mid-frame.

The transform contains no ownership certificate. Bounded numerical values alone
are insufficient to authorize its reuse on another photo/person. The host retains
validated ownership/source metadata and presents the partial feature honestly.

## Interface

`core/skin_reference_match` is a dependency-free GPL-3.0-or-later Rust crate,
`cdylib` plus `rlib`. The C header is `skin_reference_match.h`.

- `lrt_skin_reference_match_abi() -> 1`.
- `lrt_skin_reference_match_fit_v1`: independently sized contiguous reference
  RGB/coverage and target RGB/coverage, two limits, transform[4], diagnostics[24],
  cancellation callback/context.
- `lrt_skin_reference_match_apply_v1`: contiguous **current** RGB/coverage tile,
  width/height, immutable transform[4], amount, RGB output, cancellation/context.

RGB is float32 HWC3, encoded working-sRGB-D65 SDR in [0,1]. Coverage is float32
HW in [0,1]. All arrays are finite, contiguous and native-endian. Lengths count
elements, not bytes. Independent source ROI dimensions never imply a pixel pair.
Host strided windows need bounded contiguous materialization before the ABI.

The Rust safe entrypoints are `fit_reference`, `apply_into`,
`fit_memory_bytes`, and `apply_memory_bytes`. `Fit` exposes borrowed immutable
transform/diagnostic arrays. The bridge must preserve this immutability rather
than publishing a shared writable transform. No native binary or bridge is
provided by this isolated core lane.

## Neutral and failure behavior

Amount zero is a real bypass: `apply` accepts missing support and transform,
validates current pixels, and copies the exact float32 bits. Supplied optional
inputs still validate. A fit is not required just to obtain neutral output.
An active fit, including one with both correction limits zero, still requires
real evidence; callers wanting neutral should bypass fitting, not fabricate it.

Zero coverage, a valid all-zero shift, and current pixels rejected by the
reliability gate also retain original bits. Missing reference/target evidence,
excessive dispersion, malformed ownership in the host, missing native support,
cancelled work and resource refusal must not become success-with-neutral output.

All native nonzero statuses leave caller outputs untouched. Host composition of
multiple tiles/targets must similarly publish only a complete accepted frame.
Native success publication is a non-cancellable memory copy, not inter-thread
atomic synchronization or crash safety. See [NUMERICS](NUMERICS.md) for exact
ABI fields, thresholds, memory bounds and approximation limits.

## No implied completion

This source does not implement skin detection, brightest-face ranking, person
identity, ethnicity inference, intrinsic reflectance recovery, a beauty target,
geometry warp, blur, generation, an image decoder or colour management. It does
not claim proprietary algorithm equivalence, automatic multi-person feature
completion, executable integration or validated photographic quality.
