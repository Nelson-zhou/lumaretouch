#!/usr/bin/env bash
# 打包前把引擎源码暂存进 src-tauri/gen/engine-stage，供 tauri 的 resources 收进 .deb。
#
# 为什么不直接把 ../engine/src 指给 resources：那样会把开发树的 __pycache__/*.pyc
# 一起打进发行包（第一次出包就中招了）。发布物只该有源码，不该有别人机器上的字节码。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
stage="$here/../ui/src-tauri/gen/engine-stage"
mkdir -p "$stage"
( cd "$here/../engine/src" && tar cf - --exclude='__pycache__' --exclude='*.pyc' . ) \
  | ( cd "$stage" && tar xf - )

# Optional semantic source/locks/notices are part of the package; acquired
# weights and private wheels live outside this tree in the user's data directory.
mkdir -p "$stage/lumaretouch_engine/third_party/sky_semantic"
cp "$here/../docs/development/sky-semantic-proposals.md" "$stage/lumaretouch_engine/third_party/sky_semantic/README.md"

# Ship the Rust compiler used by headless recipe restore and batch processing.
# Build into staging, not the source tree, so no host-specific binary is committed.
bash "$here/build-curve-compiler.sh" "$stage/lumaretouch_engine/bin/curve-compiler"
bash "$here/build-color-scopes.sh" "$stage/lumaretouch_engine/bin/color-scopes"
bash "$here/build-local-masks.sh" "$stage/lumaretouch_engine/bin/local-masks"
bash "$here/build-manual-liquify.sh" "$stage/lumaretouch_engine/bin/manual-liquify"
bash "$here/build-brow-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_brow_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/brow_shape"
cp "$here/../core/brow_shape/lib.rs" "$here/../LICENSE" "$here/../docs/BROW-SHAPE-INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/brow_shape/"
bash "$here/build-nose-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_nose_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/nose_shape"
cp "$here/../core/nose_shape/lib.rs" "$here/../LICENSE" "$here/../docs/NOSE-SHAPE-INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/nose_shape/"
bash "$here/build-mouth-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_mouth_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/mouth_shape"
cp "$here/../core/mouth_shape/lib.rs" "$here/../LICENSE" "$here/../docs/MOUTH-SHAPE-INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/mouth_shape/"
# Original shoulder solver plus separate optional Pose Landmarker notices. No
# model bytes or runtime package acquisition is performed by engine startup.
bash "$here/build-leg-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_leg_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/leg_shape"
cp "$here/../core/leg_shape/lib.rs" "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/leg_shape/"
cp "$here/../docs/leg-shape/README.md" "$stage/lumaretouch_engine/third_party/leg_shape/README.md"
cp "$here/../engine/src/lumaretouch_engine/body_pose_licenses/"*.txt "$stage/lumaretouch_engine/third_party/leg_shape/"
bash "$here/build-arm-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_arm_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/arm_shape"
cp "$here/../core/arm_shape/lib.rs" "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/arm_shape/"
cp "$here/../docs/arm-shape/README.md" "$stage/lumaretouch_engine/third_party/arm_shape/README.md"
cp "$here/../engine/src/lumaretouch_engine/body_pose_licenses/"*.txt "$stage/lumaretouch_engine/third_party/arm_shape/"
cp "$here/../docs/model-licenses/archive/sam2-LICENSE.txt" "$here/../docs/model-licenses/archive/sam2-README.md" "$stage/lumaretouch_engine/third_party/arm_shape/"
bash "$here/build-waist-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_waist_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/waist_shape"
cp "$here/../core/waist_shape/lib.rs" "$here/../LICENSE" "$here/../docs/waist-shape/README.md" "$stage/lumaretouch_engine/third_party/waist_shape/"
cp "$here/../engine/src/lumaretouch_engine/body_pose_licenses/"*.txt "$stage/lumaretouch_engine/third_party/waist_shape/"
bash "$here/build-shoulder-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_shoulder_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/shoulder_shape"
cp "$here/../core/shoulder_shape/lib.rs" "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/shoulder_shape/"
cp "$here/../docs/shoulder-shape/README.md" "$stage/lumaretouch_engine/third_party/shoulder_shape/README.md"
cp "$here/../engine/src/lumaretouch_engine/body_pose_licenses/"*.txt "$stage/lumaretouch_engine/third_party/shoulder_shape/"
bash "$here/build-eye-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_eye_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/eye_shape"
cp "$here/../core/eye_shape/lib.rs" "$here/../LICENSE" "$here/../docs/EYE-SHAPE-INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/eye_shape/"
bash "$here/build-lip-makeup.sh" "$stage/lumaretouch_engine/bin/liblrt_lip_makeup.so"
bash "$here/build-eye-light.sh" "$stage/lumaretouch_engine/bin/liblrt_eye_light.so"
bash "$here/build-eyeliner.sh" "$stage/lumaretouch_engine/bin/liblrt_eyeliner.so"
bash "$here/build-iris-makeup.sh" "$stage/lumaretouch_engine/bin/liblrt_iris_makeup.so"
bash "$here/build-eyelash.sh" "$stage/lumaretouch_engine/bin/liblrt_eyelash.so"
cp "$here/../engine/src/lumaretouch_engine/eyeliner_patterns.json" "$stage/lumaretouch_engine/"
cp "$here/../engine/src/lumaretouch_engine/eyelash_patterns.json" "$stage/lumaretouch_engine/"
mkdir -p "$stage/lumaretouch_engine/third_party/eyeliner"
mkdir -p "$stage/lumaretouch_engine/third_party/eyelash"
bash "$here/build-brow-makeup.sh" "$stage/lumaretouch_engine/bin/liblrt_brow_makeup.so"
cp "$here/../engine/src/lumaretouch_engine/brow_makeup_patterns.json" "$stage/lumaretouch_engine/"
mkdir -p "$stage/lumaretouch_engine/third_party/brow_makeup"
cp "$here/../core/brow_makeup/brow_makeup.rs" "$here/../LICENSE" "$here/../docs/brow-makeup/README.md" "$stage/lumaretouch_engine/third_party/brow_makeup/"
cp "$here/../core/eyeliner/eyeliner.rs" "$here/../LICENSE" "$here/../docs/eyeliner/INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/eyeliner/"
cp "$here/../core/eyelash/eyelash.rs" "$here/../LICENSE" "$here/../docs/eyelash/INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/eyelash/"
bash "$here/build-lipstick.sh" "$stage/lumaretouch_engine/bin/liblrt_lipstick.so"
cp "$here/../engine/src/lumaretouch_engine/lipstick_patterns.json" "$stage/lumaretouch_engine/"
mkdir -p "$stage/lumaretouch_engine/third_party/lipstick"
cp "$here/../core/lipstick/lib.rs" "$here/../LICENSE" "$here/../docs/lipstick/INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/lipstick/"
bash "$here/build-blush-makeup.sh" "$stage/lumaretouch_engine/bin/liblrt_blush_makeup.so"
cp "$here/../engine/src/lumaretouch_engine/blush_makeup_patterns.json" "$stage/lumaretouch_engine/"
mkdir -p "$stage/lumaretouch_engine/third_party/blush_makeup"
cp "$here/../core/blush_makeup/lib.rs" "$here/../LICENSE" "$here/../docs/blush-makeup/README.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/blush_makeup/"
mkdir -p "$stage/lumaretouch_engine/third_party/lip_makeup"
cp "$here/../core/lip_makeup/lib.rs" "$here/../LICENSE" "$here/../docs/LIP-MAKEUP-INTEGRATION.md" "$here/../docs/model-licenses/archive/mediapipe-LICENSE.txt" "$stage/lumaretouch_engine/third_party/lip_makeup/"
bash "$here/build-facial-wrinkles.sh" "$stage/lumaretouch_engine/bin/liblrt_facial_wrinkles.so"
mkdir -p "$stage/lumaretouch_engine/third_party/facial_wrinkles"
cp "$here/../core/facial_wrinkles/lib.rs" "$stage/lumaretouch_engine/third_party/facial_wrinkles/"
cp "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/facial_wrinkles/COPYING"
cp "$here/../docs/FACIAL-WRINKLES-INTEGRATION.md" "$stage/lumaretouch_engine/third_party/facial_wrinkles/README.md"
bash "$here/build-optics.sh" "$stage/lumaretouch_engine/bin/liblrt_optics.so"
bash "$here/build-id-background.sh" "$stage/lumaretouch_engine/bin/liblrt_id_background.so"
bash "$here/build-creative-layers.sh" "$stage/lumaretouch_engine/bin/liblrt_creative_layers.so"
mkdir -p "$stage/lumaretouch_engine/third_party/creative_layers"
cp "$here/../core/creative_layers/"{lib.rs,creative_layers.h,ABI.md,Cargo.toml} "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/creative_layers/"
bash "$here/build-studio-background.sh" "$stage/lumaretouch_engine/bin/studio-background"
# Distribute the exact adapted worker sources and LGPL/GPL texts with its binary.
mkdir -p "$stage/lumaretouch_engine/third_party/manual_liquify"
cp "$here/../core/manual_liquify/"{*.rs,README.md,COPYING.LESSER} "$stage/lumaretouch_engine/third_party/manual_liquify/"
cp "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/manual_liquify/COPYING"

# 运行时引导那两件（M5-c）也随包走：torch 不进 .deb（体积与许可），但
# “按显卡装对应清单”这件事得有可执行的东西留在装机件里，而且它得在**没有仓库
# 的机器上**能跑——所以 GPU 清单本身也要进包，不能只留在 engine/ 目录里。
rt="$stage/runtime"
# 先清再生成：gen/ 是上一轮的目录，留着旧文件就会把“本轮不该随包走”的那几条
# 继续打进 .deb（上面那条 mediapipe 的规矩只能靠不残留来保证）。
[ -d "$rt" ] && find "$rt" -type f -delete
mkdir -p "$rt"
# Verified, prebuilt Lensfun runtime: supplied by the coordinated optics package.
cp "$here/setup-optics.py" "$stage/setup-optics.py"
cp "$here/optics-sources.lock.json" "$stage/runtime/optics-sources.lock.json"
cp "$here/../docs/optics/INSTALL.md" "$stage/runtime/OPTICS-INSTALL.md"
bash "$here/stage-optics-runtime.sh" "$stage"
cp "$here/../packaging/setup-runtime.sh" "$stage/setup-runtime.sh"
chmod +x "$stage/setup-runtime.sh"
cp "$here/../engine/requirements-rocm.txt" "$here/../engine/requirements-cuda.txt" "$rt/"
# requirements-cpu.txt 随包（手册 P0 首版②：无 GPU 也能安装的路径）。setup-runtime.sh
# --variant cpu 是一条显式 opt-in 降级路径，它得在**没有仓库的装机机**上真能跑——清单只躺在
# engine/ 目录里等于这条路径形同虚设（装机后 runtime 目录里没有 cpu 清单，--variant cpu 直接
# "× 清单不存在"）。这与上面 GPU 清单随包是同一条理由，不改变 auto/rocm/cuda 的默认探测
# （决策 10 仍禁止静默 CPU 回落；边界见 docs/adr/0022）。check-release.sh ④ 会反向查这份在不在。
cp "$here/../engine/requirements-cpu.txt" "$rt/"
# 人脸关键点清单**从 2026-10-18 起随包**（ADR-0002 推翻旧的“不进包”）：总工已放行
# 非商业定位下的 Apache-2.0 权重与 mediapipe 运行时，而 setup-runtime.sh 要拿这份清单
# 才能装上面部重塑。旧注释说的“审计未放行”不是没有审计——那棵 16 包的许可逐包列在
# 文件里，结论是“Python 包名层面零 GPL”，欠的是两处声明义务：matplotlib 不可剔除
# （已源码取证）携的 FreeType/Qhull/OFL 字体，与 sounddevice 经 ctypes 加载的
# libportaudio（LGPL，动态链接不传染）——两者均由 THIRD_PARTY_NOTICES 补齐，
# check-release.sh ⑤ 会把“这份清单在不在包里”当硬门禁反向查。
cp "$here/../engine/requirements-mediapipe.txt" "$rt/"
cp "$here/../THIRD_PARTY_NOTICES" "$rt/" 2>/dev/null || echo "  ! THIRD_PARTY_NOTICES 缺失（发布校验会拦）"
cp "$here/../packaging/VERSION" "$rt/VERSION"   # 发布校验拿它对账，运行时里那份必须与包同源

echo "引擎已暂存: $stage"
find "$stage" -name '*.py' | sed 's|^|  · |'
echo "  · setup-runtime.sh + $(ls "$rt" | tr '\n' ' ')"

# Optics kernel is our GPL source; optional Lensfun/db are separately staged, never downloaded here.
mkdir -p "$stage/lumaretouch_engine/third_party/optics"
cp "$here/../core/optics/lib.rs" "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/optics/"
cp "$here/../docs/optics/DEPENDENCIES.md" "$stage/lumaretouch_engine/third_party/optics/"

# Original local correspondence solver; no weights or runtime download.
bash "$here/build-reference-color.sh" "$stage/lumaretouch_engine/bin/liblrt_reference_color.so"
mkdir -p "$stage/lumaretouch_engine/third_party/reference_color/core/reference_color" "$stage/lumaretouch_engine/third_party/reference_color/core/curves"
cp "$here/../core/reference_color/lib.rs" "$stage/lumaretouch_engine/third_party/reference_color/core/reference_color/"
cp "$here/../core/curves/curve.rs" "$stage/lumaretouch_engine/third_party/reference_color/core/curves/"
cp "$here/../LICENSE" "$here/../docs/REFERENCE-COLOR-INTEGRATION.md" "$stage/lumaretouch_engine/third_party/reference_color/"

# Genuine neural-guided editable colour recipe: original Rust evaluator + fitter.
bash "$here/build-semantic-colour.sh" "$stage/lumaretouch_engine/bin/liblrt_semantic_colour.so"
mkdir -p "$stage/lumaretouch_engine/third_party/semantic_colour/core/semantic_colour" "$stage/lumaretouch_engine/third_party/semantic_colour/core/curves"
cp "$here/../core/semantic_colour/"*.rs "$stage/lumaretouch_engine/third_party/semantic_colour/core/semantic_colour/"
cp "$here/../core/curves/curve.rs" "$stage/lumaretouch_engine/third_party/semantic_colour/core/curves/"
cp "$here/../LICENSE" "$here/../docs/semantic_colour/README.md" "$stage/lumaretouch_engine/third_party/semantic_colour/"
mkdir -p "$stage/lumaretouch_engine/third_party/semantic_colour/batch"
cp "$here/../docs/semantic_colour_batch/"*.md "$stage/lumaretouch_engine/third_party/semantic_colour/batch/"

# Original source-domain hair colour and measured-highlight operator, no weights.
bash "$here/build-hair-colour.sh" "$stage/lumaretouch_engine/bin/liblrt_hair_colour.so"
mkdir -p "$stage/lumaretouch_engine/third_party/hair_colour/core/hair_colour"
cp "$here/../core/hair_colour/lib.rs" "$here/../core/hair_colour/README.md" "$stage/lumaretouch_engine/third_party/hair_colour/core/hair_colour/"
cp "$here/../LICENSE" "$here/../docs/hair_colour/README.md" "$stage/lumaretouch_engine/third_party/hair_colour/"

bash "$here/build-leg-length.sh" "$stage/lumaretouch_engine/bin/liblrt_leg_length.so"
mkdir -p "$stage/lumaretouch_engine/third_party/leg_length"
cp "$here/../core/leg_length/lib.rs" "$here/../LICENSE" "$here/../docs/leg-length/README.md" "$stage/lumaretouch_engine/third_party/leg_length/"
cp "$here/../engine/src/lumaretouch_engine/body_pose_licenses/"*.txt "$stage/lumaretouch_engine/third_party/leg_length/"

# Original reviewed neck length/width core.
bash "$here/build-neck-shape.sh" "$stage/lumaretouch_engine/bin/liblrt_neck_shape.so"
mkdir -p "$stage/lumaretouch_engine/third_party/neck_shape"
cp "$here/../core/neck_shape/lib.rs" "$here/../LICENSE" "$here/../docs/neck-shape/README.md" "$stage/lumaretouch_engine/third_party/neck_shape/"

# Original iris texture source and license accompany the native library.
mkdir -p "$stage/lumaretouch_engine/third_party/iris_makeup"
cp "$here/../core/iris_makeup/lib.rs" "$here/../LICENSE" "$here/../docs/iris-makeup/README.md" "$stage/lumaretouch_engine/third_party/iris_makeup/"

# Original bounded custom CUBE parser/interpolator; no runtime compilation.
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/custom_lut/lib.rs" -o "$stage/lumaretouch_engine/bin/liblrt_custom_lut.so"
mkdir -p "$stage/lumaretouch_engine/third_party/custom_lut"
cp "$here/../core/custom_lut/lib.rs" "$here/../LICENSE" "$here/../docs/custom-lut/README.md" "$stage/lumaretouch_engine/third_party/custom_lut/"

# Original extended-tone ABI2 with cooperative cancellation.
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/extended_tone/extended_tone.rs" -o "$stage/lumaretouch_engine/bin/liblrt_extended_tone.so"
mkdir -p "$stage/lumaretouch_engine/third_party/extended_tone"
cp "$here/../core/extended_tone/extended_tone.rs" "$here/../LICENSE" "$here/../docs/extended-tone/README.md" "$stage/lumaretouch_engine/third_party/extended_tone/"

# Original independent colour-grading float32 ABI1; never compiled at runtime.
bash "$here/build-colour-grading.sh" "$stage/lumaretouch_engine/bin/liblrt_colour_grading.so"
mkdir -p "$stage/lumaretouch_engine/third_party/colour_grading"
cp "$here/../core/colour_grading/lib.rs" "$here/../LICENSE" "$here/../docs/colour-grading/CONTRACT.md" "$stage/lumaretouch_engine/third_party/colour_grading/"

# Original selective colour ABI1, offline build at packaging only.
bash "$here/build-selective-colour.sh" "$stage/lumaretouch_engine/bin/liblrt_selective_colour.so"
mkdir -p "$stage/lumaretouch_engine/third_party/selective_colour"
cp "$here/../core/selective_colour/lib.rs" "$here/../LICENSE" "$here/../docs/selective-colour/CONTRACT.md" "$stage/lumaretouch_engine/third_party/selective_colour/"

# Original RGB primary calibration ABI1; offline build-time only.
bash "$here/build-primary-calibration.sh" "$stage/lumaretouch_engine/bin/liblrt_primary_calibration.so"
mkdir -p "$stage/lumaretouch_engine/third_party/primary_calibration"
cp "$here/../core/primary_calibration/lib.rs" "$here/../LICENSE" "$here/../docs/primary-calibration/CONTRACT.md" "$stage/lumaretouch_engine/third_party/primary_calibration/"

# Original non-AI photo detail; explicit package build, never runtime compilation.
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/photo_detail/photo_detail.rs" -o "$stage/lumaretouch_engine/bin/liblrt_photo_detail.so"
mkdir -p "$stage/lumaretouch_engine/third_party/photo_detail"
cp "$here/../core/photo_detail/photo_detail.rs" "$here/../LICENSE" "$here/../docs/photo-detail/README.md" "$stage/lumaretouch_engine/third_party/photo_detail/"

# Original guided black/white halo correction; build-time only, acceptance UNRUN.
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/fringe_repair/lib.rs" -o "$stage/lumaretouch_engine/bin/liblrt_fringe_repair.so"
mkdir -p "$stage/lumaretouch_engine/third_party/fringe_repair"
cp "$here/../core/fringe_repair/lib.rs" "$here/../core/fringe_repair/fringe_repair.h" "$here/../LICENSE" "$here/../docs/fringe-repair/KERNEL.md" "$stage/lumaretouch_engine/third_party/fringe_repair/"

# Original fixed-alpha colour estimation / selective spill; offline build only.
rustc --edition=2021 --crate-type cdylib -C opt-level=3 "$here/../core/spill_removal/lib.rs" -o "$stage/lumaretouch_engine/bin/liblrt_spill_removal.so"
mkdir -p "$stage/lumaretouch_engine/third_party/spill_removal"
cp "$here/../core/spill_removal/lib.rs" "$here/../core/spill_removal/spill_removal.h" "$here/../core/spill_removal/README.md" "$here/../LICENSE" "$stage/lumaretouch_engine/third_party/spill_removal/"
cp "$here/../docs/spill-removal/README.md" "$stage/lumaretouch_engine/third_party/spill_removal/INTEGRATION.md"

# Original deterministic source-coordinate photo grain, build-time only.
bash "$here/build-photo-grain.sh" "$stage/lumaretouch_engine/bin/liblrt_photo_grain.so"
mkdir -p "$stage/lumaretouch_engine/third_party/photo_grain"
cp "$here/../core/photo_grain/lib.rs" "$here/../LICENSE" "$here/../docs/photo-grain/CONTRACT.md" "$stage/lumaretouch_engine/third_party/photo_grain/"

bash "$here/build-colour-editor.sh" "$stage/lumaretouch_engine/bin/liblrt_colour_editor.so"
mkdir -p "$stage/lumaretouch_engine/third_party/colour_editor"
cp "$here/../core/colour_editor/lib.rs" "$here/../LICENSE" "$here/../docs/colour-editor/INTEGRATION.md" "$stage/lumaretouch_engine/third_party/colour_editor/"
