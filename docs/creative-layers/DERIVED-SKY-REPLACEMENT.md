# Derived-source manual sky replacement

Baseline `f116db320146c7d590f6cd45a6661d53520931c4`. This is source integration of the existing sky replacement algorithm, not a new AI model or proof of official visual parity. All authored fixtures are UNRUN. No product imports, execution, builds, typechecks, inference or downloads were performed.

## Handbook and exact requirements

The supplied handbook's sky section describes sky transforms/colour, scene/person colour influence, water reflection and recovery. Its published scene/person minimum is -100, meaning preservation of pre-sky colour; undocumented ranges remain product-specific scales, not official claims. The development-package mapping uses prefix `LNX-REF-PC-32476-C-`:

- `1f5b94eaeb` sky adjustment; `6b87bf7388` vertical, `679dae32e6` horizontal, `62a11b207d` flip, `48ec19a95a` angle, `703d8271d5` edge, `999e4bf2f2` gradient.
- `106048a96f` temperature, `dcca1d21c9` tint, `482ce42caa` saturation, `329a11842f` brightness, `4a4a602101` blur, `d57398ba6c` opacity.
- `2db62a27f5` scene/person adjustment; `aef60501f4` scene colour and `0b58cf183b` person colour.
- `47bf45fbb5` water adjustment; `98eade3987` reflection and `3da6103009` reflection blur.
- `c68a287a5a` recovery brush.

Official URL: https://www.pixcakeai.com/guide/32476 . The live read on 2026-10-23 returned inaccessible; the supplied handbook and mapping are the evidence here, not an invented live quote. No proprietary sky assets or model compatibility are asserted.

## Implemented source boundary

- Manual sky, person, water and recovery vectors own the immutable returned source. Disabled retained recipes, linked asset identities and history states are validated too. Physical original-file hash/stamp remains provenance, never the identity of returned pixels.
- Source locator and production-output review retain the existing native presentation/receipt/history flow. Async preparation cannot relabel a result after a source, recipe, asset or prepared-buffer change. Explicit selected-asset tokens and broken-link disable/reselect behavior remain intact.
- Existing Rust LMR2 replays normalized vectors at the complete source size. Existing full-image asset transforms and full-domain masks are prepared once, sliced into true tiles, then aligned with actual automatic geometry at the sky consumer. Person protection, horizon/water constraints and out-of-asset coverage refusal are preserved.
- Existing linear-light sky/atmosphere/reflection composition remains unchanged. Recovery attenuates the sky operator's contribution to current edited pixels; it does not restore original-file pixels or undo unrelated edits. This is the sky recipe's own recovery, not common `background_replace` recovery.
- Canonical full-resolution float32 returned pixels are stamped before sky export preparation. Wrong shape, quantized substitution or altered source is refused. Physical decode dimensions may differ from returned canvas dimensions. Snapshot provenance permits the derived 100% inspection route without substituting original pixels.
- Existing source/mask/asset/tile memory budgets and linked-asset content verification remain. Asset high-bit PNG decoding reuses the compatible existing ID-background uint16 orientation/ICC helpers while preserving the sky-specific opaque RGB contract and 64 MiB/32 MP bounds. JPEG/BMP/RGB TIFF retain their established path. `engine/pyproject.toml` already pins `imagecodecs==2026.10.10`; the existing `docs/development/tiff-codec-license-manifest.json` records its BSD-3-Clause wrapper and separate libpng license. No new package, model, stock asset or copied engine was introduced. Alpha/HDR source support is not implied by RGB16 asset support.

## Integration map

`creative_derived_sky`: durable source validation, recipe/asset/provenance context, actual source/repair/geometry preview key, canonical float export proof.

`creative_sky_host` and `sky_replacement_preview`: exact existing manual preview/apply envelopes, source-owned locator, frozen async candidate and rechecks through presented/apply. Existing controller owns commit, rollback and receipts. Static inspection of `sky_replacement_api.rs` and `sky_replacement_host.rs` confirms the native protocol already admits the exact sky/person/water/recovery targets and final-output presentation flow. No native validator was widened.

`sky_replacement_runtime`: effective-source verification/cache key, provenance-only physical decode check, context configuration and full-float export admission. `export_snapshot`, `ExportSpec` and canonical export resolution transport the ephemeral proof, never persisted rasters.

`creative_document_project` and server restore validate retained nested history before mutation. `creative_document_base` replaces only the sky fence with strict source verification. Preset/batch/shared transfer guards remain.

## Automatic sky semantic work remains separate

Historical boundary for this manual-sky freeze: the subsequent source-only automatic integration and installation migration are documented in `DERIVED-AUTOMATIC-SKY.md`. The following describes what this earlier snapshot intentionally left guarded, not a claim that later source integration has been runtime-tested.

Automatic OneFormer proposals are still explicitly refused for derived sources, including retained semantic descriptors. Original-photo automatic support remains unchanged. This avoids borrowing original masks under a new source hash.

The complete next dependency chain is `sky_semantic/controller`, `review`, `job`, `worker`, `resolver`, runtime raster/prepare and full-source export. It needs a dedicated immutable model-input packet derived from canonical floats, with actual source/input/transform proofs and exact reviewed-result replay. OneFormer owns a 512-short/1024-long bilinear transform, not the existing SAM/arm 2048-edge Lanczos transform. Merely reusing that packet would change model pixels.

`sky_semantic/manifest.py` hashes predictor, task-token, resolver and worker implementation into adapter identity; installation directory names also depend on that identity. Transport changes therefore require a deliberate verified installation migration/reinstallation and explicit regeneration/review of older descriptors. Never rewrite old accepted identities or reuse a previous installation as proof of a changed adapter.

## Other residuals

ID replacement support masks, prompted artifacts, pickers, immutable asset bundles and its separate stage still need a coherent source port. Legacy replacement/common recovery and cross-image transfers remain guarded. Transparent/HDR returned sources remain refused by the portrait RGB path, not flattened or clipped. Existing sky composition is an SDR operator; RGB16 asset decoding is not HDR support. Native runtime, visual quality, full-resolution inference, codecs, memory and latency are unverified here.
