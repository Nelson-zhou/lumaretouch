# 模型与数据许可台账

项目为纯开源。作者是否收费、是否有商业计划，与下游可享有的开源权利是不同问题；不自动附加非商业限制。项目GPL-3.0-or-later代码许可保持不变，各模型与运行时仍分别核验。规范依据见ADR-0001（2026-10-20修订）。

## 台账与分发状态

models.json记录候选与已登记资产，不是“所有列出的模型都已启用”的承诺。

- bundled：已登记要随包的具体文件；还必须核对发行目录实际内容、完整许可文本及运行时。
- fetched：仅适用于已核准具体版本、许可与摘要的按需获取，不能绕过分发许可。
- fetched-pending / bundled-candidate：尚未放行，不得默认获取或混入发行物。
- blocked：该后端不符合主发行条件；功能需求不取消，仍须实现兼容替代。

当前登记包括MediaPipe Face Landmarker与Selfie Segmenter两个bundled条目，其摘要与体积非空。LaMa是fetched-pending，CodeFormer因S-Lab非商业限制为blocked，YuNet仍是bundled-candidate。具体版本/文件信息以models.json为准，不再沿用“所有哈希都为null”的旧说明。

## 验收必须分开

1. 字节与清单：packaging/check-model-artifacts.py双向核验声明和暂存文件。包含tflite、task、onnx、pth、pt、ckpt、safetensors；拒绝缺失、未知、重复、摘要冲突、大小错误或符号链接。机械门禁通过不是法律审核通过。
2. 许可：源码、实际权重、依赖与训练/评测数据分别核验。源码有Apache/MIT标识不能自动证明所有权重适用同样许可；训练集限制也不能未经分析便断言自动转移到权重。非商业目的不是通用豁免。
3. 隐私：模型文件的许可与运行时遥测独立。MediaPipe PyPI运行时的遥测问题仍未由源码构建解决，当前测试断网隔离不能当作已解决发行隐私问题。
4. 质量：测试夹具或synthetic掩膜不代替真实照片效果、人像身份一致性与分区保护验收。

下载说明应提供来源、版本、体积、许可与摘要。附许可文本和署名是分发义务，不必然要求逐次点击；透明下载与避免未经核验的自动更新是产品控制要求。未知权重不自动下载，不上传用户照片。

## 样片与文档图片

只使用自产或具有明确对应授权的素材。记录来源、使用范围及指纹，未经确认不把研究数据集或他人肖像打入发行物。当前回归夹具不等于已取得所有未来训练/评测素材许可。

## 原文与审计链接

- https://opensource.org/osd
- https://opensource.org/license/mit
- https://github.com/sczhou/CodeFormer/blob/master/LICENSE
- https://github.com/TencentARC/GFPGAN/blob/master/LICENSE
- ../adr/0001-code-license-and-model-distribution-tiers.md
- ../development/open-source-runtime-review.md
- archive/目录保留的上游许可原文不作改写。
