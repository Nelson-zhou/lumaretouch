# PC-32474 studio background cleanup

Implementation written, not run. No product run, tests, build, typecheck, model download, performance measurement, photograph acceptance or publication was performed by this package owner. Qoder owns local validation. This document is code traceability, not acceptance evidence or proprietary-AI parity.

## Source and scope

- Frozen guidance: manual-text.txt lines 568–572; AI development package feature PC-32474, all 19 child/control records.
- Official behavior: https://www.pixcakeai.com/guide/32474 (consulted 2026-10-22).
- Primary operator contract: https://docs.opencv.org/4.x/d7/d8b/group__photo__inpaint.html . OpenCV accepts float32 single-channel inpaint, not float32 three-channel input. Each RGB channel is passed separately as float32 using Navier–Stokes; masks alone are uint8.
- Existing `ops/inpaint.py`, `ops/lama.py`, `ops/guided.py`, source-bound local masks and operator-local recovery were inspected. No model is silently downloaded or reported as LaMa. The packaged LaMa adapter is weight-gated and is not substituted for this deterministic solid-background operator.

## Implemented chain

App → dedicated source/actual-output workspace → Rust presentation/receipt hosts → revision-bound async prepare → one confirm/history transaction → source-bound retained recipe → production GPU stage → project v8 → full source RGB8/RGB16 inspection/export → per-target-preserving preset/batch parameter scope.

All seven parameters default zero. Brightness is -100..100 and only acts while uniformity is nonzero. Other strengths are 0..1, presented 0..100. These non-brightness numerical ranges are local implementation choices, not undisclosed reference-product thresholds.

The source locator is visibly uncropped and unwarped. The processed review is the actual complete pipeline, including independent grade groups, existing effect recovery and final manual liquify. PNGs never enter saved recipes. Showing source+mask is optional, but drawing happens only on that source locator. Full export rerasterizes vectors at original dimensions and remeasures complete original RGB, never enlarges the proxy effect fields. The optional six-class background segmentation is regenerated from the decoded full source with the identical model digest; its 8-bit observation is only model input, not the RGB16 rendering path.

## Controls: exact baseline IDs and consumers

All IDs below have prefix `PC-32474-C-` and appear in `ui/src/studioBackground/model.ts`.

| ID suffix | Control | Concrete consumer |
|---|---|---|
| d637886dca | 纯色背景祛穿帮 | robust colour-surface outlier components + explicit intrusion marking → masked float-channel OpenCV inpaint delta |
| c03981fad1 | 纯色背景祛瑕疵 | small measured outlier components + enhancement-mask correction → distinct masked inpaint field |
| 75549ae6f0 | 背景 | target-owned background support and independent blemish strength |
| f06957c177 | 地面 | explicit floor brush support and independent floor blemish strength; no inferred floor class |
| 508ddebe87 | 光影均匀 | per-region complete-image robust low-frequency light fit → bounded linear-light gain, not image blur |
| 07dabe5ea7 | 明度 | -100..100 → -1..+1 stop after fitting, gated by uniformity |
| b5e8d5499a | 祛色阶断层 | edge-aware residual bilateral correction with fine texture re-added and strong-edge suppression |
| 98057214a1 | 背景增强 | selected background/floor saturation and contrast, no replacement pixels |
| 0eb173d7d8 | 祛瑕疵增强画笔 | actual detected blemish mask refined by ordered brush composition |
| 8505883728 | 添加 | alpha-union adds coverage to current detected/painted support |
| 77953fa019 | 减去 | multiplicative coverage removal, including detected false positives |
| 5efc6b6509 | 大小 | normalized elliptical dab axes, source-size rerasterized |
| 4f3c23e230 | 羽化 | smoothstep falloff within brush radius |
| 7c9a2c1313 | 流量 | per-dab pressure-weighted coverage accumulation |
| 6cd4af46bd | 不透明度 | distinct per-stroke coverage ceiling; not an alias of flow |
| fcfeb35c00 | 显示原图和蒙版 | source photograph plus actual raster overlay visibility, distinct from output preview |
| 7e059306ef | 更新效果 | async current proposal preparation and actual production before/after render |
| 6a47eb1816 | 确定 | exact displayed candidate proof, one-shot submit, history receipt; uncertain sends are queried, not repeated |
| c68a287a5a | 恢复画笔 | four independently targeted operator input/output attenuation masks; B selects recovery inside the workspace |

## Region and photographic constraints

Manual source markings are the default. Optional verified background segmentation means the existing human-portrait background category, not a general scene/floor detector. Floor is always manually marked. Explicit floor wins over background, and protection shrinks both; protect people, objects and desired contact shadows. Region selection is not a claim that every subject is automatically protected.

The first four effects require a sufficiently large measured solid region and reject strongly textured/multicolour regions with a visible reason. Intrusions are actual connected outlier holes; no blanket background blur is called intrusion removal. The operator fills only selected holes from clean background context and composites only their coverage. Texture preservation and realism still require real photographs to validate. Large or unusual intrusion shapes, highly textured floors, busy backgrounds, ambiguous edges and severe banding can require manual marking or be rejected. These are implementation limits, not passed acceptance.

Stage order is repair/light → skin recovery → fabric recovery → studio cleanup/recovery → automatic deformation → ordinary colour/grade/groups → marked sky (when installed) / legacy background → final manual liquify → crop/rotation. Studio recovery blends each operator's real input/output, not the original photograph. Sky composition is allowed; only explicitly replaced sky pixels lose earlier background appearance, while floor cleanup remains. Full legacy replacement is mutually exclusive because it would silently override cleanup. Existing final manual field, grade groups and recovery records are untouched.

## Persistence and transfer

`_studio_background` / snapshot `studio_background`: v1 source-normalized recipe, SHA-256 + original dimensions, optional semantic model owner, neutral parameters and bounded vector strokes. Session capture/restore, undo/redo, document switch and export snapshots include it. Project schema v8 strictly validates nested active/inactive/history records, migrates older schemas to empty studio intent, and preserves all v7 manual liquify data. Explicit null/corrupt records fail rather than disappearing.

Scope `lnx.studio_background.v1` transfers only parameter values. Each target keeps its own source binding, background/floor/protection and recovery strokes. Targets lacking their own required region are rejected rather than receiving another photograph's coordinates. Full export rechecks source stamps before decode, preparation and output completion.

## Packaging and resource bounds

`packaging/build-studio-background.sh` builds the dependency-free Rust coverage worker from this checkout and stage-engine packages it. Missing worker fails explicitly; no Python raster fallback. Up to 128 strokes, 8192 points overall, 2048 per stroke, 65536 dabs, 64M pixels, bounded work and a 120-second cancellable transport deadline. Memory admission uses the existing cgroup-aware CPU estimate; full-source failure does not select a proxy export. These are admission bounds, not a speed or memory-performance certification.

Rust coverage uses separate flow/opacity and ordered alpha transforms against an automatic base mask. Complete-image fitting/inpainting is Python orchestration of mature OpenCV/NumPy; frame-rate mixing stays on existing Torch device tensors. No hidden per-frame model inference or inpaint is added.
