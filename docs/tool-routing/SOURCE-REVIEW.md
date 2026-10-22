# Retouch tool routing: source-only review

This change is a presentation/routing correction, not implementation or image-quality acceptance. No application, build, typecheck, test, model inference, installer, or download was run.

## Intended routes

- PC-32454 局部调色 retains only LocalMaskPanel and its original grading controls.
- PC-32481 手动涂抹画笔 hosts EffectRecoveryPanel.
- PC-32479 手动液化 hosts ManualLiquifyPanel.
- PC-32474 背景调整 hosts StudioBackgroundPanel; it is not PC-32475 ID backdrop.
- PC-32476 换天空 hosts SkyReplacementPanel.
- PC-32455 镜头调整 hosts the sole OpticsPanel, including perspective operations. The sibling 透视矫正 subgroup navigates to that owner, not crop and not a duplicate panel.

## Exact leaf coverage evidence

`ui/src/toolRouting/coverage.ts` uses explicit family + full path pairs taken from the baseline 功能需求验收映射.json. The source specifications are unchanged. Covered leaves are omitted only with their matching real panel slot present; empty represented branches can disappear, but unfinished leaves stay visible.

- Manual liquify: nine modes plus size, density, pressure, rate, fixed edges, protection-mask visibility (15 paths). Evidence: ManualLiquifyPanel, model.LABELS.
- Studio background: 19 mapped controls. Evidence: StudioBackgroundPanel data-control-id and model.CONTROL_IDS. Manual background/floor marking, zero defaults, protected objects and effect-specific recovery remain intact.
- Sky: 20 mapped controls. Evidence: SkyReplacementPanel explicit control IDs plus model.CONTROLS. The extra local scale control is not a baseline coverage claim. User-owned licensed assets and manually marked sky/person/water remain explicit limitations.
- Optics: 20 represented paths. Lensfun switch, manual distortion/vignette/midpoint/crop locking; line-based smart/horizontal/vertical solving; editable guides; manual perspective; auxiliary result grid. Auxiliary lines are independently implemented by show_guides and opticsGrid CSS, distinct from GuideCanvas solve lines.
- Common recovery: only the exact ID backdrop leaf is suppressed (background_replace). Other supported common targets remain skin_smoothing, fabric_fine, facial_wrinkles and lip_makeup, not a broader generic blemish or clothing-fold claim. Background and sky recovery navigate to their own workflows.

## Remaining gaps and caveats

- AI perspective is not implemented by line analysis. Its baseline leaf remains visibly unfinished, with explicit wording that automatic line analysis is not AI.
- RAW/non-RAW workflow-specific baseline leaves are not hidden merely because manual optics exists.
- Generic blemish recovery and all-clothing-fold recovery remain unfinished. Fine-fabric recovery is narrower; smoothing/wrinkles/lip recovery do not imply generic blemish support.
- No licensed built-in sky library, automatic sky/water detection, or automatic floor semantics is claimed.
- Runtime portal, keyboard focus, cancel, receipt, history and image-quality acceptance still require authorized execution separately.
