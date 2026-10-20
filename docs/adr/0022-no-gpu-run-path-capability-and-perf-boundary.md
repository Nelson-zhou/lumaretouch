# ADR-0022：无 GPU 的运行路径、能力与性能边界——可运行但如实标注，不冒充 GPU

- 状态：已定档（2026-10-20）
- 关联：手册 P0 首版验收项②（用户提供追加）；`engine/src/lumaretouch_engine/vram.py`
  （`PreviewPipeline` 的 cuda→cpu 退路）、`server.py`（`pipe.fallback` → `engine_warn`）；
  回归 `engine/tests/test_no_gpu_path.py`；PyTorch 官方 `torch.cuda.is_available()` 语义。

## 背景

产品按 GPU 常驻预览设计（代理帧常驻显存、逐帧在设备内渲染）。手册 P0 与用户追加项②要求
"提供无 GPU 可安装、可运行的路径并明确性能/能力边界"。这里的关键风险不是"能不能在 CPU 上跑"，
而是"跑的时候有没有如实说清自己在 CPU 上跑"——静默把 `cuda` 当成可用会让"GPU 常驻"的结论变成
假的（F 轮就栽在"切了 device 但旧张量还在 CPU 上跑、bench 照报 cuda:true"）。

## 事实（本轮实测，非沿用历史）

1. 引擎默认 `device="cpu"`（`server.Engine.__init__`）；请求 `cuda*` 而 `torch.cuda.is_available()`
   为假时，`PreviewPipeline` 如实退到 `cpu` 并把原因写进 `self.fallback`；`server` 用
   `emit({"event":"engine_warn","warn":pipe.fallback})` 把这条退路透出去——CPU 运行不是静默降级。
2. 本机有 ROCm；用 `CUDA_VISIBLE_DEVICES=""` 隐藏设备后确定性验证：`make_pipeline("cuda:0", …)`
   落到 `cpu` 且 `fallback` 非空；`render(0.5)`→`read_back()` 产出合法 `(H,W,4) uint8`；
   `render(0.0)` 逐字节等于原图（中性档恒等在 CPU 上成立）。
3. 单次 CPU 性能样本（本机、512×640、磨皮）：首帧滤波 ~106 ms（含一次性建缓存），
   缓存命中后的混合+量化 ~1.6 ms/帧。**这是单一机器、单一尺寸的点，不是全尺寸/全效果曲线。**

## 决定

- 无 GPU **运行**路径按上述事实承认为可运行：设备默认 cpu、退路可见、渲染与中性恒等在 CPU 上成立，
  由 `test_no_gpu_path.py` 钉住（monkeypatch `is_available→False`，与宿主有没有 GPU 无关、不触 GPU）。
- 界面对"当前是不是 GPU 常驻"必须取自引擎上报的 `device`/`cuda` 与 `engine_warn`，不得前端自行宣称。
- 能力/性能边界**如实标注为待测**：真实"无 GPU 裸机安装 + 端到端 UI + 全尺寸性能曲线"本轮**未运行**
  （需要一台真无 GPU 的环境与授权）；本 ADR 只记录已证的运行正确性与单点耗时，不据此给出 SLA 或
  "任意机器可流畅"的结论。
- **安装层（本轮补正）**：此前 `setup-runtime.sh` 按决策 10 只装 GPU 变体、无 GPU 机器直接 `exit 1`——
  即 P0② 要的"无 GPU 可安装"当时**并未满足**（本 ADR 早先只证了 code 层 cuda→cpu 运行回退，未覆盖
  “安装”这一层，此处更正）。现补上显式 opt-in 的无 GPU 安装路径：`engine/requirements-cpu.txt` +
  `setup-runtime.sh --variant cpu`（auto/rocm/cuda 默认行为不变，探测到 AMD/NVIDIA 仍装 GPU；不把
  静默 CPU 回落当默认，与决策 10 不冲突）。该安装路径的**实际装机与全尺寸性能曲线仍需在真无 GPU
  裸机上首跑回填**（与 requirements-cuda.txt “N 卡未实测”同口径），未在此冒充“装机验收通过”。

## 后果

- CPU 上重效果（形变 TPS、AI 超分/抠图等）成本可能远高于 GPU 的毫秒级；这些是"能出正确结果但慢"，
  不是"不支持"——慢与不可用必须在上报里分开（沿用 DoD：接不了要说原因）。
- 无 GPU 机器上 `matting_backends`/`upscale_backends` 等能力名单仍由引擎按实际可用项报出，
  不给无权重/无算力的机器留一个按下去不响的入口。

## 明确不做 / 退出条件

- 不拿"CPU 能 import、单点 1.6 ms"冒充"完整装机验收通过"；装机级验收仍记为未运行，直至真无 GPU 环境跑通。
- 不把 CPU 退路做成静默：任何 cuda→cpu 的降级都必须能被调用方看见（fallback/engine_warn）。
- 当获得真无 GPU 环境时，补跑 `packaging/m5-release-check.sh` 那条装机臂并回填本 ADR 的性能/能力小节；
  届时用真实数据替换上面的单点样本，而不是沿用。

## 来源

- PyTorch 官方：`torch.cuda.is_available()` 返回当前进程能否使用 CUDA（隐藏设备后为 False）。
  https://pytorch.org/docs/stable/cuda.html#torch.cuda.is_available
- 本项目 `vram.py` / `server.py` 的 cuda→cpu 退路与 `engine_warn` 上报（代码即证据，回归已钉）。
