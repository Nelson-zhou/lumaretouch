# Optional automatic lens depth v1

**SOURCE AUTHORED / ALL EXECUTION UNRUN (2026-10-25).** The owned source chain is
now setup → CPU readiness → full-frame inference → depth review → existing lens
preview/save-copy. It is not a build result, installed model, photo-quality result
or performance acceptance. Current setup is **unavailable** because four optional
runtime components still lack sufficient primary license evidence. The authored
installer checks that eligibility before any download; no flag in a user receipt
can override it. Missing metadata is not evidence of a restrictive license.

## One supported candidate and honest admission

Model: official `depth-anything/Depth-Anything-V2-Small-hf`, revision
`5426e4f0f36572d16453bbda7a8389317b1bef99`. Small is Apache-2.0;
[upstream license scope](https://github.com/DepthAnything/Depth-Anything-V2#license)
puts Base/Large/Giant under CC-BY-NC-4.0. They are not alternatives in this profile.
There is no .pth/pickle, V1, metric, ONNX, remote-code, arbitrary model ID, community
node, cache discovery or manual/luminance depth disguised as AI.

| Revision-scoped file | Bytes | SHA256 |
|---|---:|---|
| model.safetensors | 99,173,660 | `3152477ce0d8d6978d76b995120de97cb5b928701fd0f817769f59e249a16b70` |
| config.json | 950 | `c56698d3643dde1f83ea2212759e6b31a22b8f827246a36dd007ee8a22b3ff75` |
| preprocessor_config.json | 775 | `d41175c0d889477ca8fc67191e540faef14baf6275157b3fdecf78469e6bbf84` |

Config and preprocessor hashes were computed from actual raw HTTPS response bytes
at the fixed revision on 2026-10-25, not rendered text:
[config](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/resolve/5426e4f0f36572d16453bbda7a8389317b1bef99/config.json),
[processor](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/resolve/5426e4f0f36572d16453bbda7a8389317b1bef99/preprocessor_config.json).
The weight hash remains the earlier official
[revision-scoped metadata evidence](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/blob/5426e4f0f36572d16453bbda7a8389317b1bef99/model.safetensors),
not a locally downloaded/verified checkpoint. A redundant pointer read was denied;
no denial was bypassed and no weights were downloaded.

Runtime profile is Linux x86_64, glibc ≥2.28, CPython 3.12; existing explicitly
selected app `torch==2.7.1+cpu`, `torchvision==0.22.1+cpu`, NumPy ≥2.1 and Pillow
≥11, ≤15.0 are prerequisites. **This extension does not install/authenticate the
base interpreter, Torch native libraries or their dependency graph.** They are
trusted app components; base metadata/RECORD hashes only detect drift, not origin.
No GPU, interpreter fallback or global environment package replacement occurs.

`lens_depth_runtime_lock.json` records 26 exact optional wheels, 24,652,473 bytes,
from official PyPI metadata including recursive applicable dependency edges.
The root is `transformers==5.11.0`, wheel 11,094,597 bytes,
SHA256 `06d0a34eab529955f8e704b530663c7d6bd6f9c7a9e47a05cddb4a44e7b6566b`.
[Official metadata](https://pypi.org/pypi/transformers/5.11.0/json) reported no listed
advisories at research time; this is **not** a security audit or compatibility
clearance. The older 4.45.2 digest retained in the source is historical research,
not an installation requirement. No package archive was fetched in development.

The optional graph includes MPL-2.0 components (certifi, tqdm); do not call it
"all permissive." `tokenizers==0.22.2`, `safetensors==0.8.0`,
`markdown-it-py==4.2.0`, `mdurl==0.1.2` had missing license fields in the retained
metadata. Additional primary-evidence queries were denied and not retried.
Their setup/distribution eligibility remains explicitly pending. This is a
research gap, not a finding that these packages are proprietary. Retain actual
license/notice files if distribution later becomes eligible.

## Concrete setup and runtime boundaries

- The existing native optional-model subprocess owner serializes SAM/depth setup,
  routes only fixed helper modules, labels extension identity and refuses
  cancellation from another extension. No automatic setup on opening the panel.
- Once eligibility is established in reviewed source, explicit install reuses the
  resumable fixed-Hugging-Face downloader and model-owner lock. Exact size and
  complete SHA256 precede use. The three model files have an exact allowlist.
- Optional wheels are fetched by exact HTTPS URL with `--require-hashes --no-deps`.
  The installer retains each wheel; extraction forbids traversal, links, .pth,
  bytecode and .data relocation, limits decompression, rejects duplicate ownership.
  Runtime admission rehashes original wheels and compares every extracted file
  against their actual member bytes, rejects unowned files and foreign loaded
  modules. It does not trust a mutable installed inventory receipt.
- Candidate staging is probed before publication. Prior bytes are retained during
  repair. Two renames are recoverable in-process but not an atomic crash exchange;
  rollback/uninstall UX is not implemented.
- A passing generated 64×48 CPU fixture is retained only for unchanged runtime
  identity. Recheck removes old readiness first. This local receipt is **not a
  tamperproof attestation** and never means a real photograph passed acceptance.
- Both probe and actual inference execute in a child with parent-death binding,
  actual Linux seccomp network denial, no model downloads, CPU 100-second limit,
  wall 110-second timeout, 8 GiB address-space cap, 400 MB output limit and visible
  available-memory floor of 4 GiB. Cancellation kills/reaps the process group,
  including a stuck model kernel. These bounds are not measured RSS/speed promises.
- Offline status currently performs full model/wheel/code integrity reads; repeated
  status may be expensive and has not been benchmarked. Installation and reads
  cannot establish compatibility without the actual future CPU probe.

## Whole-source inference and precision

The immutable owner binds document ID, epoch, canonical uint64 revision and
oriented source digest/grid. The existing lens source owner captures the complete
current edited image and cold-rechecks file/graph ownership after analysis. Stale
requests are rejected; cancellation and replay use the original read identity.
Source colour pixels, document history and source files are never changed by
analysis. Saving a blur result remains the separate existing reviewed new-copy
operation, not an inference side effect.

The first profile accepts genuine opaque finite unit-range SDR linear-sRGB only.
Transparent/HDR sources are rejected rather than silently flattened/tone-mapped.
A nearest-centre whole-frame RGB8 analysis proxy (long edge ≤1024, no upscaling)
uses the existing native sRGB presentation transform; exact transform and proxy
hashes are retained. No crop, rotated-grid guess or use of the proxy as source
render pixels occurs. Source admission is ≤100M pixels, edges ≥2 and aspect ≤4:1;
existing lens memory budgets may impose stricter limits.

The pinned upstream config specifies Small DINOv2 width384, heads6, stages
3/6/9/12, patch14 and neck48/96/192/384. Do not use class defaults (different stages).
The 5.11 default `DPTImageProcessor` changed backend: this adapter explicitly uses
[`DPTImageProcessorPil`](https://raw.githubusercontent.com/huggingface/transformers/v5.11.0/src/transformers/models/dpt/image_processing_pil_dpt.py)
for the researched Pillow RGB8 resize semantics. Model input is CPU float32,
finite RGB batch1, multiples14, max edge1536 and 786,432 pixels; unsupported
preprocessor extents fail rather than distort/crop. Exact verified safetensors
bytes feed `load`, and `strict=True` rejects checkpoint/architecture mismatch.
No remote `from_pretrained` path exists. Actual upstream parity is UNRUN.

The [paper](https://arxiv.org/html/2406.09414v2#S5.SS2) describes affine-invariant
inverse depth. Full-grid bicubic interpolation uses `align_corners=False`; global
post-interpolation min/max maps `(max-p)/(max-min)` to near-zero/far-one using
float64 chunk arithmetic, stored little-endian f32. Nonfinite/constant fields are
rejected. This is not metres, physical camera blur, uncertainty or confidence.
Subject focus stays null; nearest pixels are not assumed to be the subject.

**Native processing now retains the actual full-source f32 depth separately from
UI u16 visualization.** It never reconstructs AI processing depth from quantized
UI bytes. The UI proxy records nearest-centre sampling and `floor(v*65535+0.5)`
quantization. Point focus still samples that UI proxy and has its sampling error.
Only `direct-v1` consumes model depth; `cohort-fft-v2` remains manual-plane only.

The UI requires distinct depth-map review before a model-depth preview and then
independent actual before/after confirmation before saving a new copy. Failed
visualization, changed owner/depth, hiding or unmounting revokes depth review.

## What remains unverified

Primary license evidence/eligibility for four optional packages is the current
setup blocker. Base runtime automatic provisioning, complete base native-library
provenance, crash recovery/uninstall UX and GPU profiles are outside this slice.
Actual install, checkpoint integrity, CPU readiness, model inference, Rust/TS
builds, tests, real-photo detail/edges/occlusion, native depth alignment, save/reopen,
export and performance acceptance are **all UNRUN**. Only source reading,
metadata research, authored fixtures and static Python AST parsing were performed.
