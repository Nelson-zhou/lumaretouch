# Optional semantic sky/water proposals: source-integrated package

Status: source-integrated, NOT runtime-accepted. Application/native/engine/project
and export hooks are wired; no claim of completed runtime or quality acceptance.
No model, wheel or weight download,
installation, inference, product execution, test, build, typecheck, quality
benchmark or runtime-equivalence check has been performed for this package.
The existing reviewed manual-region workflow remains the working fallback.

## Official assets and licenses

The candidate is SHI Labs OneFormer ADE20K Swin Tiny. It predicts actual semantic
classes, not the inverse of a portrait mask. The official model card declares
MIT. This does not provide licensed stock skies: sky images remain user supplied.

- Model: `shi-labs/oneformer_ade20k_swin_tiny`.
- Immutable revision: `05f2812b1eccf9909b3897777450f8d68148cafc`.
- Weight: `pytorch_model.bin`, exactly 203,389,501 bytes; SHA256
  `909b07dbf4129c2bbb8df4498e35dcd46f305e3ec45329d3ff6d4f0360de27f3`.
- All eight model files total 205,072,098 bytes. README, model configuration,
  preprocessing configuration, tokenizer configuration, special tokens,
  vocabulary and merges have individual fixed sizes and SHA256 identities in
  `sky_semantic/assets-lock.json`. No safetensors asset exists in this pinned
  official tree. The loader uses `torch.load(weights_only=True)` on the exact
  hash-verified bytes, requires a pure tensor dictionary and strict state load.
  No arbitrary pickle loader, custom model code or remote code is permitted.
- Original OneFormer MIT notice is retained verbatim as
  `ONEFORMER-LICENSE-MIT.txt`; `license-source.json` fixes its official Git blob
  `8ea0dead0eae2bb8274320bfb16f633c3f386dda` and SHA256. The pinned model card is
  the independent license declaration for the weights.
- Exact official source pages: [model card](https://huggingface.co/shi-labs/oneformer_ade20k_swin_tiny/blob/05f2812b1eccf9909b3897777450f8d68148cafc/README.md),
  [immutable model inventory](https://huggingface.co/api/models/shi-labs/oneformer_ade20k_swin_tiny/tree/05f2812b1eccf9909b3897777450f8d68148cafc),
  [original MIT notice blob](https://api.github.com/repos/SHI-Labs/OneFormer/git/blobs/8ea0dead0eae2bb8274320bfb16f633c3f386dda).

The private runtime is explicitly named
`lumaretouch-oneformer-semantic / 5.20.2+lumaretouch.semantic1`, based on official
Transformers commit `18329f1065382e54db698e242cf98bd3f3e5a766` (Apache-2.0).
Original wheel: `transformers-5.20.2-py3-none-any.whl`, 12,844,921 bytes, SHA256
`7ae75dbc1fb3922aff1b6c97b9e5479d6cf26fd86a8866bfb71324190479f807`.
All 25 runtime distributions, exact versions, official PyPI metadata URLs,
eligible Linux CPython 3.12–3.14 x86_64/aarch64 wheel filenames, byte sizes and
SHA256 values are in the lock. Platform selection uses actual wheel tags; an
unsupported platform fails visibly instead of compiling or choosing a source
archive. Original licenses, notices, metadata and wheel archives are retained.
The modified METADATA version and dependency list are explicit; original RECORD
is provenance only, not the integrity proof for patched files. The derived
installation receipt validates every byte against locked original wheels and
the exact fork transformations, not against an editable receipt alone.

The host's accelerator stack is NOT replaced. Actual Python, Torch, torchvision,
NumPy and Pillow identities are retained with each accepted proposal. This is
not a claim of a hermetic host dependency closure. Compatible host versions and
actual CPU/CUDA/ROCm behavior still require local acceptance.

### Regex licensing issue and resolution

The general upstream dependency `regex 2026.9.29` declares
`Apache-2.0 AND CNRI-Python`. Its upstream notice describes CPython 2.6/3.1-derived
code under a Python 1.6 license. Python's own historical license page distinguishes
GPL-incompatible Python 1.6 variants from later compatible variants. These are
not assumed interchangeable. This ambiguity was surfaced before adoption;
`regex` is excluded from the approved distribution, not silently added.
[Upstream notice](https://github.com/mrabarnett/mrab-regex/blob/hg/LICENSE.txt),
[Python historical license table](https://www.python.org/doc/copyright/),
[SPDX CNRI-Python text](https://spdx.org/licenses/CNRI-Python.html).

There is NO fake regex module and NO regex-to-stdlib substitution. In particular,
Unicode `\w`/`\s` in generated-documentation helpers are not asserted equivalent.
The supported model path never imports that module. A small project-authored
adapter implements only the two identity-decorator signatures used by the pinned
Swin/OneFormer path, preserving existing static docstrings without generation or
parsing. General documentation and tokenizer APIs are explicitly unsupported.

## Exact fork and static import audit

`fork-patches.json` records each replacement, official Git blob, before SHA256
and after SHA256. Seven original files are changed:

1. `dependency_versions_check.py`: remove the dependency not used by this fork.
2. `utils/__init__.py`: import only the two private documentation decorators,
   not the original generated-documentation module or its data/helper API.
3. `models/oneformer/modeling_oneformer.py`: instantiate the pinned SwinBackbone
   directly instead of the generic auto-backbone loader; import unchanged
   checkpointing support from a separated attributed module.
4. `models/swin/modeling_swin.py`: same checkpointing support and direct
   `typing_extensions.Unpack` instead of processor/tokenizer imports.
5. `modeling_utils.py`: point the checkpointing helper to that same support.
6. `configuration_utils.py`: move the existing legacy GGUF loader import into
   its explicit GGUF-only branch. Direct dictionary construction never uses it.
7. `__init__.py`: disclose the private fork version.

The checkpointing class is copied unchanged with the original Apache header;
its source/output identity is recorded. No attention, Swin, decoder, query,
classification, mask, task-encoding, weight-initialization or model-forward math
is intentionally patched. Direct fixed-backbone construction and the isolated
documentation surface still require runtime compatibility validation.

The static audit covers supported preprocessing and construction, not merely a
guard that makes an incomplete path fail. The inspected import edges include:

- Transformers root -> dependency checks -> utils. Generated docs previously
  imported Python regex; the private two-decorator adapter removes that edge.
  Utility doc/chat-template/generic/output-capturing modules use no Python regex
  dependency on this path. Standard-library `re` in unchanged modules remains
  unchanged; no expression has been translated between dialects.
- OneFormerConfig -> configuration utilities -> lazy AutoConfig/SwinConfig.
  AutoConfig is needed for the nested fixed Swin config; AutoModel/auto_factory
  is not. The legacy eager GGUF loader led to tokenizer mappings; its import is
  now in the unused GGUF branch. Fast GGUF quantizer reader/kernel helpers were
  also inspected: they do not require tokenizer mappings at import.
- OneFormer/Swin models -> modeling_utils, activations, model outputs, backbone
  utilities, model loading, losses and attention integrations. The original
  generic modeling_layers import reached processing/tokenizer code; the exact
  checkpointing class is separated. The original load_backbone auto-factory
  path reached generation/tokenizers; direct pinned Swin construction avoids it.
- Eager/SDPA/flash integration imports include continuous-batching modules.
  Their cache, API, requests, model runner, input/output, initialization and
  logits-processor edges were inspected rather than assuming they were lazy.
  This inference path explicitly selects eager attention and never generates
  text. No inference-only semantic labels invoke the training matcher/SciPy.
- Preprocessing does not instantiate OneFormerProcessor/ImageProcessor or an
  AutoProcessor. The official processor constructor can fetch extra dataset
  metadata; that path is intentionally absent. Only pinned local configuration,
  NumPy/Pillow input preparation, known task tokens and the builtin model are used.

`SemanticOnly` is installed before private-runtime/model imports in a fresh
worker. It denies Python regex, processor/tokenizer, generated-documentation,
generic model-factory, legacy GGUF and text-generation entry paths. It does not
impersonate modules, monkeypatch global installed packages or provide failing
semantic stubs. The private directory is added without site processing, so no
`.pth` execution occurs. Any unexpected retained dependency is a visible error
requiring correction, not success. The static audit is NOT runtime proof.

## Fixed official task tokens, preprocessing and semantic math

Official task string: `the task is semantic`. Pinned vocabulary/merges produce:

`the</w>`, `task</w>`, `is</w>`, `seman`, `tic</w>`.

Token sequence including BOS/EOS:
`49406, 518, 10549, 533, 29119, 1550, 49407`.
Sequence length is 77. The official tokenizer pads using EOS 49407; the official
OneFormerProcessor multiplies token IDs by the attention mask. Thus the first
seven mask entries are 1 and the remaining 70 are 0, yielding 70 zero task IDs.
`task_tokens.py` re-derives exactly this single ASCII string from the pinned
official vocab and first 48,894 ranked merges, and checks the locked IDs. It is
not a general CLIP tokenizer and performs no unsupported Unicode substitution.
[Pinned processor](https://github.com/huggingface/transformers/blob/18329f1065382e54db698e242cf98bd3f3e5a766/src/transformers/models/oneformer/processing_oneformer.py),
[pinned model](https://github.com/huggingface/transformers/blob/18329f1065382e54db698e242cf98bd3f3e5a766/src/transformers/models/oneformer/modeling_oneformer.py).

The proposal-only contract is source-normalized, RGB8 model input, short edge
512 / long edge at most 1024, FP32, eager attention, explicit CPU or CUDA, no
automatic device fallback. The official preprocessing file's rescale/mean/std
values are used. Bounded Pillow bilinear resize is a declared adapter, not a
claim of equivalence to every Transformers processor version. RGB16 source
pixels and the working-color/export pipeline are never replaced by this RGB8
input. Input bytes, dimensions, runtime identities and model/adapter identity
are captured for replay.

Semantic output uses the official softmax excluding null class, sigmoid masks,
query/class einsum, torchvision v2 bilinear logit resize and argmax first-class
tie rule. Class chunks bound temporary memory. Chunked floating-point behavior
still requires local comparison. Support scores are explicitly uncalibrated
relative class scores, not correctness probabilities.

Pinned ADE20K IDs: sky 2, person 12; water 21, sea 26, river 60, swimming pool 109,
lake 128. Waterfall/fountain are excluded from this horizontal-reflection
proposal family. No class absence declares “no people.” No model output supplies
or guesses a horizon. No inverse-portrait shortcut or lower-half water fallback
exists. People, sky and water remain independently inspectable and correctable.

## Acquisition, offline worker and review

Only explicit installer action accesses the network. It accepts no photo or
arbitrary URL, checks official HTTPS redirect hosts and fixed sizes/hashes,
streams progress, supports cancellation, locks the install and publishes only
after complete verification. Wheels are extracted as data, not installed by pip
or setup.py. Path traversal, symlinks, `.pth`, bytecode and relocation-script
payloads are rejected. A mismatch fails visibly. Forced termination may leave
an unpublished staging directory; it is never recognized as a valid install.

Inference is a separate owned process, with offline environment and seccomp
policy, parent-death termination, bounded source/RAM/VRAM admission, 180-second
deadline, output-size limit and cancellation. No image is uploaded. Proposed
lossless labels/support fields and RGB8 overlays are display artifacts only.

The review owner binds source content and current document/edit context. Each
accepted region must have been displayed. Acceptance returns a DRAFT ONLY
descriptor with “requires sky output review”; it cannot mutate project history,
commit a sky effect, infer a horizon, declare no people or authorize export.
Existing final sky composition display acknowledgement and atomic commit remain
mandatory. Retained proposals can be replayed against exact source/model/runtime
and field hashes. Brush corrections compose over the semantic operand using
the existing Rust LMR2 ordered add/subtract implementation, not contour fitting
or a full-image fallback. Removing the optional semantic operand retains brushes.

## Connected application contract

- The dedicated PC-32476 sky panel owns acquisition and proposal review. Stable
  ports are App-owned through `useSkyReplacementWorkflow`; the original pending
  sky commit receipt is preserved. This is not installed in localMasksPanel.
- Native `sky_semantic_model` is the sole network acquisition entry. Status starts
  one inventory helper; polling never restarts it. Download requires the visible
  license/content opt-in. Progress, cancel, error and manual fallback stay reachable.
- `sky_semantic` start/shown/accept/cancel binds engine epoch, document, source-
  locator session, run ID and request ID. New runs supersede older ones. Each
  selected overlay must load and paint before acknowledgement. Both native and
  engine reject stale context; cancellation cannot cancel a newer run.
- Accept changes only the draft. It does not infer no-person or reflection horizon.
  The existing actual sky output preview and one-shot commit receipt remain required.
- Recipe v2 retains source-bound provenance plus existing ordered add/subtract
  brush corrections and manual recovery. Rust LMR2 combines the semantic operand
  and brush stack; one object slot is reserved per region. Combined masks drive
  readiness. User sky assets and independent manual marking remain supported.
- Project v11 migrates v10 manual sky to v2 with semantic=null, preserving manual
  v7, studio v8, optics v9 and existing portrait/history records. Current, history
  and recipe snapshots retain intent, not display PNGs. Unavailable older model
  identities remain removable without requiring installed weights just to parse.
- Strict export/inspection replays source/model/input/host identities and field
  SHA256. Interactive caches check installation stamps; strict replay verifies all
  locked bytes. RGB8 model/locator pixels never replace RGB16 export source pixels.
  Missing or corrupt dependencies show the persistent suspended label and cannot
  become valid export/inspection or bare applied frames. Disable/removal keeps
  manual corrections and remains reachable after a failed preview.
- Preset/batch transfer keeps target source, semantic/brush regions, person
  declaration and horizon; only selected sky asset and controls transfer. Target
  dependencies are checked before real review/export. An installed model is not
  proof of detection for another image.
- Stage order stays source/studio -> auto-deform -> grades -> sky -> legacy full
  replacement -> manual -> optics -> crop. Sky and full replacement are exclusive;
  studio floor cleanup can coexist with the selected sky pixels.
- Real lifecycle helpers tick owned workers at idle without closing sessions.
  Context invalidation/cancel/shutdown releases proposal workers; model installer
  and inference processes are separately owned and terminated on actual exit.
- Packaging carries source, exact inventories/patches, MIT/Apache notices and this
  document. Acquired weights/private wheels stay outside the engine environment
  and are not bundled in the default installer. No general Transformers or host
  GPU environment is silently replaced.

Local acceptance still needs actual acquisition/cancel/corruption behavior,
runtime import and strict checkpoint load, official-output comparison, device
memory/latency observation, semantic quality on diverse photos, view/brush/
horizon controls, undo/project replay, missing-asset recovery, RGB16 export and
asset-aware transfer. None is reported passed here.
