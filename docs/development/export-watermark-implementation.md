# 导出水印实现记录（开发实现，尚未运行验收）

## 冻结来源

- 产品手册导出摘要、工作流与「导出与水印」图证解读：横图／竖图／方图独立配置，九宫格、旋转、大小、合适开关、不透明度、水平／垂直位置；允许同时导出无水印副本。
- 仓内 `ui/src/spec/workflows.json`，workflow 32483，原始来源 https://www.pixcakeai.com/guide/32483。
- 这不是生成式 AI 来源标识管理，也不提供移除第三方水印工具。排版打印是另一功能，不因本项而宣告完成。

## 实现与边界

- `ui/src/watermark`：独立水印配置面板；文字与图片、字体路径、颜色、三种最终画幅配置、九宫格、顺时针旋转、宽度比例、适合画幅、透明度、边距与 XY 偏移。支持将当前方向配置显式复制到另外方向。
- 设置作为本机导出偏好保存，不污染照片编辑配方；保存失败可见。没有宣称工程文件打包或跨设备同步水印资源。
- `watermark.py`：导出提交时验证并冻结图片／字体字节和 SHA-256，队列及当前会话重试不再读取源文件。三种方向均前置校验。图片最大 8 MiB、1600 万像素；字体最大 32 MiB。尺寸导致水印栅格超限会明确拒绝，不偷偷缩小。
- 字体默认优先系统 Noto CJK；拉丁文字可回退 DejaVu Sans。缺失支持字体时要求用户指定字体，不默默生成缺字方框代替默认中文。自选字体是否覆盖所有文字仍由用户所选字体决定。
- Pillow 仅栅格化文字／图片水印，处理标识自身 EXIF、ICC、透明度、尺寸与旋转。照片主体绝不进入 Pillow RGB8 转换。水印 ROI 使用线性 sRGB float32 源覆盖合成；RGB16 输出保留 16 位，透明区域及 ROI 外逐值保留。
- `watermark_delivery.py`：在最终裁剪与旋转后选择画幅、合成，在输出 ICC 转换前叠印。RGB16 使用已有 RGB16 ICC 转换与 TIFF 写入／读回核验，JPEG、压缩、冲突与元数据继续使用原有 writer。
- 勾选双份时普通目标为水印版，无水印版置于输出目录的「无水印」子目录，两份分别按既有冲突策略处理。一个副本失败会标记本条失败并保留已处理副本的明确路径与状态，不声称全部成功。两个副本均跳过时，本条按跳过记账。
- UI 展示双份以及部分成功副本的路径／同名跳过状态；失败行保留错误提示。批量每张照片按自己的最终长宽选择方向。
- 保持现有单图和批量入口、任务暂停／取消边界与当前会话固定快照重试。重启后的任务快照规则沿用既有机制，不宣称可跨会话重试。

## 未验收声明

依用户“开发优先、不逐项回归等待”的要求，本轮只有静态读写与代码审查，没有启动产品、执行测试、构建、类型检查或扩充测试。真实字体、实际 ICC/RGB16 读回、批量副本冲突、取消与重试、面板视觉效果仍待后续统一运行验证。本记录不改变冻结需求台账的验收状态。

## 成熟实现依据（官方直接文档，非博客）

- 冻结功能来源编号：PC-32483，https://www.pixcakeai.com/guide/32483 。
- Pillow ImageDraw 的 multiline_text / multiline_textbbox：先量文字边界再绘制到独立 RGBA 标识层，避免负边承裁切：https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html#PIL.ImageDraw.ImageDraw.multiline_textbbox
- Pillow Image 的 RGBA / resize / rotate / thumbnail：图片水印保留 alpha、Lanczos 缩放、旋转展开与适合画幅；这些 API 仅用于标识，不用于降低照片位深：https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize
- Pillow ImageCms profileToProfile：只将水印资源自身 ICC 归一到 sRGB，再恢复原 alpha；照片仍由仓内 RGB16 LittleCMS 路径处理：https://pillow.readthedocs.io/en/stable/reference/ImageCms.html#PIL.ImageCms.profileToProfile

没有拷贝外部项目代码、没有下载字体或新增不明来源依赖。Rust 命令桥仍负责明确传递设置；合成位于既有 Python/NumPy 高位深导出栈，避免另建一套和现有颜色管理不同的照片管线。
