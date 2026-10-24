import type {SpecNode} from "../spec";
/** Exact baseline family + path coverage, verified against the corresponding panel.
 * This is UI de-duplication, not an acceptance claim. Never hide whole families.
 * Optics auxiliary grid and editable solve guides are distinct implemented controls.
 * RAW workflows remain explicit gaps; automatic perspective is one enable plus three modes. */
const COVERED: Record<string, ReadonlySet<string>> = {
  "PC-32473": new Set(["直角肩", "肩膀宽度", "脖子长度", "瘦脖子", "AI瘦手臂&瘦手臂", "瘦腰", "瘦腿", "瘦腿/大腿", "瘦腿/小腿", "长腿", "长腿/大腿", "长腿/小腿", "上身长度", "腰部长度"]),
  "PC-32479": new Set([
    "向前变形",
    "重建",
    "平滑",
    "旋转",
    "褶皱",
    "膨胀",
    "左推",
    "冻结",
    "解冻",
    "液化：大小",
    "液化：密度",
    "液化：压力",
    "液化：速率",
    "液化：固定边缘",
    "液化：显示蒙版"
]),
  "PC-32474": new Set([
    "纯色背景祛穿帮",
    "纯色背景祛瑕疵",
    "纯色背景祛瑕疵/祛瑕疵增强画笔",
    "纯色背景光影均匀",
    "纯色背景光影均匀/明度",
    "纯色背景祛色彩断层",
    "背景增强",
    "手动涂抹画笔",
    "纯色背景祛瑕疵/背景",
    "纯色背景祛瑕疵/地面",
    "纯色背景祛瑕疵/增强画笔/添加",
    "纯色背景祛瑕疵/增强画笔/减去",
    "纯色背景祛瑕疵/增强画笔/大小",
    "纯色背景祛瑕疵/增强画笔/羽化",
    "纯色背景祛瑕疵/增强画笔/流量",
    "纯色背景祛瑕疵/增强画笔/不透明度",
    "纯色背景祛瑕疵/增强画笔/显示原图和蒙版",
    "纯色背景祛瑕疵/增强画笔/更新效果",
    "纯色背景祛瑕疵/增强画笔/确定"
]),
  "PC-32476": new Set([
    "天空调整",
    "人景调整",
    "人景调整/景物色彩（偏向天空）",
    "人景调整/人物色彩（偏向天空）",
    "水面调整",
    "水面调整/景物反射",
    "水面调整/景物水效虚化",
    "手动涂抹画笔",
    "天空调整/垂直位置",
    "天空调整/水平位置",
    "天空调整/天空翻转",
    "天空调整/角度",
    "天空调整/边缘过渡",
    "天空调整/天空渐变",
    "天空调整/色温",
    "天空调整/色调",
    "天空调整/饱和度",
    "天空调整/亮度",
    "天空调整/虚化",
    "天空调整/不透明度"
]),
  "PC-32455": new Set([
    "颗粒", "颗粒/颗粒效果", "颗粒/阴影", "颗粒/中间调", "颗粒/高光", "颗粒/颗粒大小", "颗粒/粗糙度", "颗粒/颗粒色彩",
    "校准", "校准/红原色", "校准/绿原色", "校准/蓝原色", "校准/红原色色相", "校准/红原色饱和度", "校准/绿原色色相", "校准/绿原色饱和度", "校准/蓝原色色相", "校准/蓝原色饱和度",
    "可选颜色", "可选颜色/红", "可选颜色/黄", "可选颜色/绿", "可选颜色/青", "可选颜色/蓝", "可选颜色/洋红", "可选颜色/白", "可选颜色/中间色", "可选颜色/黑", "可选颜色/青色量", "可选颜色/洋红量", "可选颜色/黄色量", "可选颜色/黑色量", "可选颜色/相对", "可选颜色/绝对",
    "颜色分级", "颜色分级/高光", "颜色分级/阴影", "颜色分级/中间调", "颜色分级/全局", "颜色分级/混合", "颜色分级/平衡", "颜色分级/明亮度","影调/亮度", "影调/白色", "影调/黑色", "影调/纹理", "影调/清晰度", "影调/祛雾", "影调/鲜艳度",
    "镜头调整",
    "透视矫正",
    "镜头调整/镜头矫正开关",
    "镜头调整/畸变矫正",
    "镜头调整/锁定裁剪",
    "镜头调整/暗角调节",
    "镜头调整/中点调节",
    "透视矫正/AI透视矫正",
    "透视矫正/智能",
    "透视矫正/水平自动",
    "透视矫正/垂直自动",
    "透视矫正/引导线",
    "透视矫正/垂直",
    "透视矫正/水平",
    "透视矫正/旋转",
    "透视矫正/长宽比",
    "透视矫正/缩放",
    "透视矫正/水平偏移",
    "透视矫正/垂直偏移",
    "透视矫正/辅助线",
    "透视矫正/锁定裁剪"
]),
  "PC-32481": new Set([
    "证件照换背景涂抹笔"
]),
};
export function withoutCoveredLeaves(nodes: SpecNode[], feature: string, slotPresent: boolean): SpecNode[] {
  if (!slotPresent) return nodes;
  const covered = COVERED[feature];
  if (!covered) return nodes;
  return nodes.flatMap(node => {
    const children = withoutCoveredLeaves(node.children, feature, true);
    const leaf = node.leaf && !covered.has(node.leaf.path) ? node.leaf : undefined;
    const anchor = feature === "PC-32455" && ["镜头调整", "透视矫正"].includes(node.full);
    return leaf || children.length || anchor ? [{...node, leaf, children}] : [];
  });
}
