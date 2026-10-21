# 人像验证素材与任务覆盖（2026-10-21核查）

状态：未完成原手册的影楼任务与250张授权样本验收，不用公开数据集数量替代它。

## 原要求不能被替换

原手册要求先与影楼确认三类真实任务及当前人工时长，取得样片测试授权，再冻结200张代表样本与50张困难样本，覆盖可见肤色、年龄、妆容、胡须、眼镜、多人、侧脸、遮挡、高ISO和混合光。当前没有上述真实业务基准，也没有完整授权样本集。公开照片只能补充算法/边界测试，不能证明影楼产能或客户授权。

## 本轮官方资料核查

- PPR10K：代码仓库标Apache-2.0，但README单独限制数据及衍生数据为非商业研究用途。不能把代码许可套给数据或预训练权重，不能作为纯开源发行包的默认自由素材池。论文的多人区域优先与组照一致性值得作为测试设计参考，并不等于本项目达到其质量。未下载该数据集或权重。
  https://github.com/csjliang/PPR10K#agreement
  https://openaccess.thecvf.com/content/CVPR2021/html/Liang_PPR10K_A_Large-Scale_Portrait_Photo_Retouching_Dataset_With_Human-Region_Mask_CVPR_2021_paper.html
- FFHQ：原照片许可混合，部分含NC；NVIDIA对数据集元数据、下载脚本、文档另设CC BY-NC-SA 4.0。不能整体复制成自由发行测试集。逐照片原始授权、署名、修改记录、撤回意愿和人物权益仍要核对。未下载数据集。
  https://github.com/NVlabs/ffhq-dataset#licenses
- 已有NASA astronaut裁剪：具体来源和版权标记记录在测试夹具provenance中，不概括成“所有NASA素材都无约束”。NASA媒体指南另提醒可识别人物的商业用途、标志与第三方材料限制。仅做内部技术测试，不用于应用展示/营销或暗示背书；没有取得人物商业肖像授权。
  https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut
  https://www.nasa.gov/nasa-brand-center/images-and-media/

## 当前证据如何使用

单张真实照片及其镜像/拼图只算一个原始样本。合成皮肤、解析几何与算法真值用于契约测试，不能算独立真人。RAW场景/色卡验证位深与文件链，不算人像画质。任何缩放、镜像、变亮或复制的增强版本不得扩充“250张已授权原片”计数。

后续样本台账至少需：来源URL或授权凭据、原始SHA256、明确使用范围、是否允许再分发/训练/仅测试、署名及修改记录、代表/困难分组与可见拍摄条件。避免无必要地保存被摄者姓名、联系方式或身份推断。许可门禁是证据完整性检查，不是自动法律背书。
