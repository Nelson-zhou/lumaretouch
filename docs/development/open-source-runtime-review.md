# 纯开源与离线运行时复核（未完成项明确保留）

本轮基线是纯开源项目，不把“作者不收费”误写成“禁止任何商业用途”。代码现有 GPL-3.0-or-later 未改。历史 README / NOTICE / models.json 中的“纯开源、非商业自由软件”及对第三方训练数据义务的笼统推断需要逐项修订，不能据此自动批准模型打包。

## 强制选择准则

1. 将源码、权重、训练/测试数据、运行时二进制分别审计。代码仓库挂 Apache 标识不自动证明每份权重与样片可再分发。
2. 用途限制与开源定义分开：OSI定义第6条不允许排除商业领域，故非商业限制不能作为纯开源主发行物依赖的默认许可。依据：https://opensource.org/osd 。
3. CodeFormer上游S-Lab License 1.0明确限非商业，不能因为本项目开源就认定它无条件适配。依据：https://github.com/sczhou/CodeFormer/blob/master/LICENSE 。面部恢复功能保留在需求中，需选适配后端，不删功能以通过许可检查。
4. GFPGAN作为候选而非已定“最优”：源码Apache-2.0，提供无需自定义CUDA扩展的clean版本；上游同时说明部分版本可能轻微改变身份。仍须对具体权重/分发条件/照片质量逐项核验，不能单凭开源标识或示例图放行。依据：https://github.com/TencentARC/GFPGAN 。
5. MediaPipe PyPI运行时的指标遥测不能被“图片不上传”掩盖。源码版日志工厂返回DummyLogger已核，但源码构建未成功，当前测试必须保留断网隔离。官方说明：https://github.com/google-ai-edge/mediapipe/issues/6291 。
6. 测试集许可、肖像与隐私不能通过“非商业”一句话全部豁免。当前回归仅用仓库自制/明确授权夹具；未上传用户照片，未下载用途未核的数据集。

## 本轮可证实的新增依赖

- tifffile2026.10.15 / imagecodecs2026.10.10来自官方PyPI发行，源码上游BSD-3-Clause。实际wheel中的许可路径、长度与SHA-256记录在tiff-codec-license-manifest.json；imagecodecs包含多个第三方编解码组件，保留其各自许可，不把整个wheel简单概括为单一许可。
- LibRaw0.21.5仅用于复现既有偏移表的测试环境；官方网站当前提供更新的0.22系列，未来正式发行不应把测试匹配结论误写成最新版支持或安全性评估。0.21.5真头文件生成的106项偏移/常量与仓库一致，RAW64项通过。

这份文件记录已核与待核，未修改上游版权条款，也未声称许可/遥测问题已经全部解决。

## 2026-10-20 后续纠正

实际复核GFPGAN上游LICENSE而非只看首页：文件明确列有第三方例外，包括DFDNet相关CC-BY-NC-SA及NVIDIA相关文本。因此“Apache源码候选”不能作为整个推理依赖/权重无条件放行的依据；需按实际调用路径和具体文件继续核查。来源：https://github.com/TencentARC/GFPGAN/blob/master/LICENSE 。

ADR-0001、NOTICE、台账README纠正“纯开源=禁止商用”“MIT允许丢署名”“免费自动豁免模型许可”等旧推断，LICENSE原文和第三方许可档案未改。CodeFormer移为blocked候选，LaMa移为fetched-pending，面部修复和智能消除产品需求保留，不以换后端为理由删功能。

打包门禁新增双向字节检查：原脚本漏扫tflite，也没有检验已宣称bundled但实际缺失的模型。新增统一脚本及反向测试；它只证明清单/字节/声明一致，不冒充全部权利审核或实际安装验收。
