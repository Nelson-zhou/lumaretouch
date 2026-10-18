# ADR-0002：MediaPipe 由「可选插件」升格为随包运行时，权重进 deb

状态：已采纳（2026-10-18）。推翻 ADR-0001 的部分：决策 B 里"不进 deb、不进 CI 主门禁"
这一交付形态；许可分层与台账门禁的机制**保留**（它这轮真的拦住了一次漏登记）。

## 背景与触发

决策 B 当初把 mediapipe 挡在发行物外，唯一的硬理由是"许可审计未放行"，而不是技术缺陷。
总工 2026-10-18 明确了项目定位：纯开源、非商业自由软件，Apache-2.0 权重全面放行。
前提变了，结论就必须跟着变——留在原地会让产品Feature 列表里"面部重塑"永远显示为不可用。

## 决策

1. `face_landmarker.task`(3,758,596 B) 与 `selfie_segmenter.tflite`(249,537 B) **进 deb**，
   装在 `…/lumaretouch_engine/data/`，装机零操作。
2. `requirements-mediapipe.txt` + `THIRD_PARTY_NOTICES` 随包；`setup-runtime.sh` 增加一步
   走 PyPI 装 mediapipe，**失败不阻断整个运行时**。
3. 运行时推理继续用 mediapipe Tasks API，不用 LiteRT 自实现管线。

## 为什么不是 LiteRT（我一度选它，然后错了）

先量了依赖树：`ai-edge-litert` 6 个包 vs `mediapipe` 16 个包，前者干净得多，我当场裁决走
LiteRT + 自实现 BlazeFace 解码。这条判断错在没有先查仓库里已有什么：

- `face.py::MediaPipeFace` 早就按同一条 478 点契约写好了；
- `requirements-mediapipe.txt` 里躺着**逐包许可审计**（16 包，结论"Python 包名层面零 GPL"），
  还带 matplotlib 不可剔除的源码取证。

也就是说重写换来的唯一好处（少 10 个包）要付出的代价是重新实现锚点解码/NMS/ROI 变换，
并且扔掉一份已经做完的审计。为"看起来更干净"去付真实风险，不值。

## 两处裁定（旧文件里写着"待总工裁定"）

- **libportaudio（LGPL）**：sounddevice 经 ctypes 动态加载，LGPL 只要求"可替换 + 附文本"，
  不传染；deb 里该库本就是系统包（可替换）。实测本机 `libportaudio2` 状态为 **未安装**，
  而人脸链路照常跑通——它连运行期依赖都不是。裁定：接受。
- **matplotlib 随附组件**：不可从 mediapipe 剔除（`vision/__init__.py` eager 导入 drawing_utils，
  后者顶层 import matplotlib.pyplot）。裁定：以**生成**的 THIRD_PARTY_NOTICES 承接，
  不手写——手抄那份已证明会腐烂（见下）。

## 这一轮实际犯下并被机制抓住的三个错

1. `MediaPipeFace` 三处 API 从未执行过就写错了（`num_face_landmarks`/`Segmenter`/`seg.mask[0]`，
   其中掩膜取的是**背景**通道语义）。教训：不跑的代码等于没写的代码。
2. 生成器用 `realpath(sys.executable)` 判断是否跳环境，被 venv 软链判成相等，于是
   **对着开发 venv 出了一张缺 torch 的许可表**、rc 还是 0。改为显式 `sysconfig purelib`
   + 只扫该目录 + torch/mediapipe 不在场就拒绝出表。
3. 权重先进了包、台账没登记，被 check-release ⑥ 拦下才补。

## 被否掉的方案

- 静默按需拉取：与"完全本地"矛盾，且 Apache-2.0 §4(a) 要求许可文本随副本分发。
- 全部重型模型进 deb（LaMa/CodeFormer 数百 MB）：本轮不放行，它们仍留在 fetched/未核档。
- 把 mediapipe 并进 GPU 清单：那份带 `--index-url` 指向 pytorch 专仓，PyPI 包会去错仓找。
