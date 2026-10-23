# Blush makeup, source-integrated slice

Status: SOURCE AUTHORED AND HOST/UI INTEGRATED, UNRUN. Not runtime acceptance, not visual acceptance, not complete whole makeup. Isolated source base: `30494a6e`; shared integration base: `5eeca0229c9ab2cd0a13f7ae8bce9a72d49266b4`. No product import, execution, tests, builds, compiler/typecheck, inference, downloads/installs, Git writes or pushes were performed by this slice author. Python AST/JSON parsing, source inspection and SHA-256 hashing are the only verification performed.

## Evidence and exact requirement scope

Official page inspected 2026-10-23: https://www.pixcakeai.com/guide/32471 (page displayed update 2026-07-09). Its blush section describes twelve effects, adjustable amount, eyedropper, RGB/HEX colour entry, and six saved colours. The shared makeup-colour section describes recommended colours varying by material. The page does not publish numerical slider ranges or the proprietary algorithms. Local [0,1] strength, geometric designs and palettes here are original product choices, not reverse-engineered parity.

Cross-checked supplied `manual-text.txt` makeup section (lines 541–545) and `AI开发资料包/功能需求验收映射.json`. The source mapping explicitly says related PORTRAIT-010 cases are NOT proof of this control's coverage; do not promote those rows to complete.

| Requirement suffix (prefix LNX-REF-PC-32471-C-) | Meaning | Concrete isolated source | Acceptance status |
|---|---|---|---|
| e7ccb5a9e2 | Blush family, 12 patterns and strength | original pattern catalogue, Rust compositor, measured geometry, layer, UI | UNRUN |
| 6be18714f8 | Recommended colours | per-pattern catalogue and UI swatches | UNRUN |
| 53df3c11b3 | Eyedropper | picker.ts / useBlushPicker.ts use existing producer capture with source/target/revision fences | UNRUN |
| 3f0064d896 | RGB | state.rgb / UI validated explicit commit | UNRUN |
| 8059d0cdd0 | HEX | state.colour / UI validated explicit commit | UNRUN |
| 6f5d708f87 | Saved colours, max 6 | state palette validation, project library, staged host action | UNRUN |

## Material and numerical design

Twelve distinct ORIGINAL analytic lobe arrangements: round apple, horizontal oval, lifted diagonal, horizontal ribbon, narrow under-eye, paired sunset, three petals, arc crescent, cloud cluster, narrow steep diagonal, side drape and soft four-lobe square. Each has independent shape geometry. Changing only palette is not counted as a pattern. Thumbnails use the same lobe parameters, but are schematic drawings and not rendered-portrait evidence.

`blush_makeup_patterns.json` is the immutable source catalogue. Its SHA-256 is pinned in Python and a static TS mirror. Changing it requires explicit catalogue version/migration, not silently changing a saved project. No competitor illustration, image, texture, template, code or other visual asset was downloaded or reused. All new code and analytic assets are GPL-3.0-or-later, matching repository license, with SPDX headers/data license. No additional model or dependency was installed.

The Rust ABI computes a compact-support smooth field and bounded tint-chroma contribution in the existing display-referred working-sRGB float32 space. Source texture is not blurred, sharpened, synthesized or quantized. The tint adds chroma and a gentle encoded-luma shift, so black/grey/white custom colours also have a real contribution. Luma texture gain remains at least 0.92 before gamut constraints; this is not scene-linear luminance invariance. The shared compositor adds the contribution to current pixels, preserving unrelated earlier operators, rather than replacing with source RGB. Neutral returns no layer before any native/model requirement. RGB16 source fractions stay float32; only the chosen UI colour has an explicit 8-bit RGB representation.

## Ownership, anatomy and limitations

Uses stable canonical FaceRef (asset SHA, face instance, analysis revision); detector index is not identity. `people_render_runtime.verify_analysis` must run before `prepare_record`, verifying actual retained 478-point MediaPipe analysis and semantic model evidence. Skin and known-occluder maps must match source dimensions. Before active blush, a source/face/analysis-pinned, explicit bilateral cheek-visibility review is required. The user paints directly visible skin on the verified undeformed source reference; immutable vectors are retained in the canonical people support bank and rasterized anew at preview/export dimensions. This reviewed coverage only intersects actual skin/anatomy exclusions and cannot override them. The analytic field is oriented separately to each measured cheek. The selected face oval, actual eye outlines, actual lip outline, nose corridor and known hair/clothes/background are exclusions; no bounding-box fill or template face is used. Both cheeks require support; one-side failure refuses the requested effect instead of silently publishing a partial one.

Current limitations are explicit: strong profiles, cropped outlines, small faces and degenerate anatomy refuse. Six-class semantics do not perfectly detect skin-coloured hands, glasses, transient face overlap or all occluders. Per-face oval plus semantic skin is not a person-instance skin segmentation. Review such scenes and use source-owned blush recovery to exclude false positives. No complete occlusion, dermatological, demographic fairness or visual-parity claim is made without licensed real-portrait QA. Inherited group/person changes remain under existing explicit association and transaction policies.

Active source input outside the host's [0,1] working-sRGB contract is rejected, never silently clipped to fake HDR support. Neutral does not touch source or bypass the existing HDR/RGB16 owner. End-to-end HDR/gamut, GPU/CPU, tile-seam, export, memory, multi-person and undo behavior remain UNRUN.

## Integration gate

The shared host/UI/package routes in `INTEGRATION.md` have now been authored, including actual viewer mounting and producer-frame presentation acknowledgment. The runtime capability is conditional on the packaged Rust binary. Those routes were inspected statically, NOT executed. Compilation, runtime reachability, visual results and acceptance remain UNRUN. Do not claim completion based on static parsing. Existing independent left/right eye-light review/parameters/actions and body operation ordering v1–v5 remain untouched.

Authored acceptance metadata: `engine/tests/fixtures/blush_makeup/acceptance.json` (15 UNRUN cases). Numeric/unit sources: Python contract test, TS model test, Rust unit module. No portrait fixture has been invented as real acceptance evidence.

Favourites are document-owned: up to six colours per photograph persist in the normal project document recipe and undo/redo history (`_blush_makeup_library`). They are not transferable portrait intent or a separate global history owner. Pattern/strength/colour alone travel through presets and explicit confirmed-face batch mappings.
