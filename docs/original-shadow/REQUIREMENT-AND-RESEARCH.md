# Original photographed-shadow retention: research boundary

Reconciled 2026-10-23. This document is not an implementation, model installation,
licence clearance for checkpoint redistribution, or numerical/photo acceptance.
The later [manual-assisted implementation scope](IMPLEMENTATION.md) uses reviewed
uniform-floor measurements, not these neural models. The AI retention requirement
and general photographic extraction remain unimplemented; the family stays partial.

## Exact official requirements

The [official PC-32475 guide](https://www.pixcakeai.com/guide/32475) distinguishes
原图阴影 from 增加阴影. The former retains photographed shadows; the latter
creates designed shadows. Requirement prefix `LNX-REF-PC-32475-C-`:

- `442ced0175`: 原图阴影 entry.
- `ab010073e3`: AI保留阴影.
- `48553e2d03`: 程度.
- `c959928d7a`: 正常 blend.
- `b1b766d4ce`: 正片叠底 blend.
- `9e1c732ff8`: 柔光 blend.
- `0513155f3d`: 保留范围画笔.

Supplied manual text lines 575–579 separates these families. The supplied AI
requirement mapping lines 5711–5721 and 5932–6007 marks these seven P1/research,
with empty dedicated acceptance-case lists. `ui/src/spec/refine.json` does not
disclose ranges/defaults/steps. New numeric choices must be labelled ours.

The existing `core/id_background` shadow kernel samples shifted foreground alpha
and blurs/fades it. It does not recover original photographed illumination.
Spill correction and recovery are also not original-shadow extraction. Existing
state/runtime/UI explicitly lack an independent shadow estimate, retention
coverage, original-shadow strength/blend state and authenticated field consumer.

## Primary technique candidates, not imported implementations

1. [SID, SP-Net + M-Net](https://github.com/cvlab-stonybrook/SID): illumination
   parameters plus a soft shadow matte, described in the authors' [paper](https://arxiv.org/html/2012.13018v2).
   [Code licence](https://github.com/cvlab-stonybrook/SID/blob/main/LICENSE): MIT,
   Hieu Le 2020. The official main testing route requires a shadow-mask input.
   Published 256px evaluation is not native-resolution portrait acceptance.
   Multiple shadows and inaccurate masks/parameters are known limits. Checkpoint,
   detector and dataset redistribution terms still require separate verification.
2. [SynShadow](https://github.com/naoto0804/SynShadow): synthetic shadow-free,
   shadowed and matte data plus detector/decomposition approaches.
   [Code licence](https://github.com/naoto0804/SynShadow/blob/main/LICENSE): MIT,
   Naoto Inoue 2021. Reported 480×640 outputs do not prove full-source quality.
   Dataset and checkpoint rights must not be inferred from the code licence.
3. [ShadowFormer](https://github.com/GuoLanqing/ShadowFormer), [paper](https://arxiv.org/abs/2302.01650),
   [MIT code licence](https://github.com/GuoLanqing/ShadowFormer/blob/main/LICENSE),
   GuoLanqing 2023: shadow-free appearance restoration, not directly an editable
   retained illumination layer. Extracting one would require additional work.
4. [PyMatting](https://github.com/pymatting/pymatting),
   [MIT licence](https://github.com/pymatting/pymatting/blob/master/LICENSE.md):
   trimap refinement primitive, not automatic shadow detection or complete AI
   shadow retention. Manual trimap assistance alone cannot satisfy AI retention.

No model, dependency, source code, binary or dataset was downloaded or copied.
A model being published under an apparent code licence does not establish the
licence of every external weight, training dataset or dependency.

## Bounded next implementation gate

Establish verified detector/decomposition model rights and actual input/output,
colour, precision, inference-scale and refinement contracts before enabling AI.
A SID-style parameter-plus-matte representation is a plausible design, not a
chosen validated backend. Keep source-bound illumination estimate, confidence and
retention coverage separate from person alpha, spill coverage and recovery.
Do not paste old floor pixels, relabel inverse luminance as AI, or project person
alpha as a substitute for photographed shadows.

The eventual full path needs independent enable/strength/three blends/coverage,
actual before/after review, explicit original/derived ownership, native history
and project recovery, target-local batch recomputation/review, full-source export
and tile alignment. Define ordering with designed shadows to avoid double darkening.

Dedicated acceptance must cover feet/props contact shadows, broad penumbrae,
textured or dark floors, white clothing, reflective surfaces, multiple shadows,
no-shadow inputs and ambiguous cases. Measure old-background texture leakage,
foreground preservation, neutral bypass, precision, full-source parity, stale
proof rejection, undo/reopen and per-target review. All remain UNRUN. No seven-ID
completion claim follows from this research or from existing added-shadow controls.
