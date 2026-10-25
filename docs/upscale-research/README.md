# AI超清 research: a missing creative feature, not export sharpening

Research date: 2026-10-25. Documentation-only handoff. No product source changed,
model downloaded, dependency installed, product imported, inference executed,
test/build/typecheck run or Git write performed. This is not source-connected or
accepted functionality. Existing feature/acceptance ledgers remain unchanged.

## Exact requirements and official behavior

| Requirement | Baseline / traceability | Required behavior |
| --- | --- | --- |
| LNX-REF-WF-158251-a4c9a2ccc1 | PC-158251; WF-158251-a4c9a2ccc1; creative:158251 | AI超清 clarity restoration; single/multiple images; whole-image, face, body and background strengths; zoomed before/after review; Apply; creative recipes |
| LNX-REF-WF-127932-657ed77402 | PC-127932; WF-127932-657ed77402; ui:7 | Actual AI超清 result layer supports alignment, position, size, opacity and rotation |
| LNX-REF-WF-127932-a9c143a25d | ui:8; shared creative return requirement | Return edited creative result as a new image or update the existing photo without changing original source bytes |
| LNX-REF-WF-127932-c7783ea5fb | ui:9; shared history requirement | Recover earlier/original state through the existing history owner |
| LNX-REF-WF-32480-c75523501b | workflow:32480; shared workflow requirement | Batch synchronization / creative recipes; not a new AI algorithm ID |

Original evidence: supplied manual-text.txt lines 771–776 and 917; supplied
功能需求验收映射.json AI超清 / 超清层属性 records; repository
ui/src/spec/creative.json entry 158251 and
docs/development/handbook-traceability.json entries creative:158251 / ui:7.
Both primary entries still say pending_independent_verification with no
implementation/verification list. The original mapping assigns both to P2 and
does not supply dedicated acceptance cases.

Live primary recheck:
- [AI超清 guide](https://www.pixcakeai.com/guide/158251), updated 2026-09-17:
  describes learned defocus/clarity recovery, four regional strengths, zoomed
  comparison, Apply and multi-image creative recipes. Creative viewing uses
  original-image dimensions; the 4000px refine preview is not an export limit.
- [Creative workspace guide](https://www.pixcakeai.com/guide/127932), updated
  2026-09-14: AI超清 layer properties are specifically listed, independently of
  the background and passerby-removal layer types. Shared return, history and
  recipe controls are described on the same page.

Not disclosed: slider numeric ranges/defaults, regional overlap algebra,
segmentation model, exact definition of face/body boundaries, image scaling
factor, proprietary restoration architecture or quality/error guarantees.
In particular, original-size *viewing* does not establish a required 2×/4× model
or a vendor output-size formula. A local same-size restoration policy is proposed
below, not attributed to the vendor. Flip is listed for background layers but
not explicitly for the AI超清 layer; do not expand its official control list.
Two candidates/regeneration are documented for other tools, not this requirement.

## Duplicate and coverage audit

1. engine/src/lumaretouch_engine/ops/upscale.py already implements deterministic
   Lanczos plus unsharp and exposes scales 1/2/3/4. core/photo_detail and existing
   clarity/sharpen/skin-texture controls are non-AI detail operations. They do not
   restore learned details or provide this creative workflow. Retain them under
   their honest existing names; do not count them again as AI超清.
2. export.py declares UPSCALE_BACKENDS_WIRED = ("lanczos3",), and its ExportSpec
   rejects realesrgan. server.py cmd_export likewise rejects it before starting.
   ops/upscale.py lists realesrgan only in weights_gated with the additional
   unwired-export caveat. Supplying a weight checksum does not enable export.
3. ops/realesrgan.py is a custom RRDB-like experimental network, not a compatible
   official Real-ESRGAN loader. Its small random-network shape/overlap fixtures
   in engine/tests/test_upscale.py do not establish checkpoint compatibility,
   perceptual quality, full-image memory safety or a working creative feature.
4. CreativeWorkspace.tsx currently wires only smart heal and the independently
   developing lens entry in its tool catalogue. Entry 158251 is not connected.
   This observation is a source snapshot, not runtime UI verification.
5. The creative layer foundation already has generic image transforms, opacity,
   immutable assets, source-aware return, project storage and unified history.
   docs/creative-layers/IMPLEMENTATION.md explicitly calls 657ed77402 only a
   generic transform foundation, not a superresolution algorithm. Reuse that
   owner rather than building a duplicate document/history stack.
6. creative_generation_* is an isolated Kandinsky passerby/inpaint proposal.
   It is not image-wide restoration and must not be relabelled as AI超清.
   Existing expression and lens work are separate features and untouched here.

### Why the existing network cannot take official weights

Read against pinned
[BasicSR RRDBNet](https://github.com/XPixelGroup/BasicSR/blob/651835a1b9d38dbbdaf45750f56906be2364f01a/basicsr/archs/rrdbnet_arch.py)
and [Real-ESRGAN loading](https://github.com/xinntao/Real-ESRGAN/blob/fa4c8a03ae3dbc9ea6ed471a6ab5da94ac15c2ea/realesrgan/utils.py).

| Existing local network | Official RRDBNet / checkpoint contract |
| --- | --- |
| r1/r2/r3 containing c1…c5 | rdb1/rdb2/rdb3 containing conv1…conv5 |
| Additional RRDB.bd convolution, output scaled by 2.3 | No RRDB.bd; RRDB residual scaled by 0.2 |
| conv → PixelShuffle upsample list, no intervening official activation sequence | nearest-neighbor 2× → conv_up1 → LeakyReLU, then corresponding conv_up2 sequence |
| Scale 1/2 simply removes upsampling stages | Scale 1/2 pixel-unshuffles input by 4/2, changing conv_first input channels; both upsampling stages remain |
| Unwraps optional net key only | Prefer params_ema, otherwise params; strict state dictionary |

This is an architectural mismatch, not just key renaming. Do not weaken strict
loading, reshape arbitrary tensors, claim an existing checksum fixes it, or
regenerate official-looking weights from the random local architecture.

## Conditional model recommendation and hard blockers

Use an optional, separately licensed/admitted **official general-image RRDBNet**
backend as the technical reference, never the current custom implementation.
RealESRGAN_x2plus is a reasonable first *candidate* for native-size restoration:
its 2× intermediate has four times the input pixels versus sixteen for x4plus.
That is arithmetic, not a measured latency/quality win. RealESRGAN_x4plus remains
a reference candidate to compare during photographic evaluation. Both produce
learned superresolution, not guaranteed recovery of the actual missing detail.

The proposed AI超清 mode restores to the frozen source's native dimensions after
actual neural inference. A separately exposed enlargement mode may be added
later; it is not required by the supplied guide and not silently driven by the
existing export scale. The general-x4v3 compact model is not initially preferred
because upstream describes weaker deblur/denoise capability, and its denoise
control is model-specific network interpolation, not four region strengths.
Anime checkpoints and GFPGAN face reconstruction are outside this first scope.

There is **no approved/installable production model pack from this research**:
- Official code revisions, file Git blob hashes and code licenses are pinned in
  [PROVENANCE.json](PROVENANCE.json). Git object IDs are not weight SHA256s or
  authenticated installed wheel hashes.
- Official release metadata gives exact sizes but digest=null for all inspected
  relevant checkpoints. Their content SHA256 stays null. No model bytes were
  obtained or locally hashed. Mutable release tags/assets do not replace hashes.
- Real-ESRGAN code is BSD-3-Clause; BasicSR code is Apache-2.0. The inspected
  project license and releases did not provide an independently explicit grant
  covering these exact checkpoint artifacts. This is unresolved license scope,
  not a finding that their use is forbidden. Questions #677/#1015/#1016 remain
  unanswered by an authorized maintainer in the responses inspected. A community
  question or mirror's license label cannot fill that gap.
- The pinned x4 training configuration names DF2K+OST. Synthetic degradation is
  not proof that all source photographs were synthetic or that their rights are
  cleared; no automatic transfer of dataset restrictions to weights is asserted.
- Exact offline runtime distribution hashes, compatibility and security review
  for Python/Torch/BasicSR/Real-ESRGAN are still missing. Historical lower bounds
  and the repository's existing ROCm variant are not backend acceptance.

Continue with [the proposed numeric/backend contract](BACKEND-CONTRACT.md) and
[the minimal implementation/acceptance map](IMPLEMENTATION-MAP.md). No source
integration, installation, model access or execution is authorized by these notes.

LOCAL-SOURCE-SHA256.txt records selected local evidence files as read, not an
atomic freeze of other developers' active work or proof of test execution.
The two code-license texts are archived under licenses/; no upstream model or
inference source code was copied into product modules or a runtime package.
