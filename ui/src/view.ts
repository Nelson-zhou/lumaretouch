/**
 * 视口坐标映射（P1-9）。
 *
 * 显示层（.mirror）用 `object-fit: contain` 等比居中——当 viewer 盒子宽高比 ≠ 图像宽高比时
 * 必然产生留白（黑边），再叠加 `translate(panX,panY) scale(zoom)`。画笔/框选要落到图像上正确的
 * 位置，就必须按「图像在屏幕上的实际显示矩形」换算，而不是按整个盒子。
 *
 * 上一版 toImg 直接拿 overlay（铺满盒子，inset:0）的 getBoundingClientRect 折算，把整盒当成整图：
 * 一留白，指针在留白维度的落点就会偏移、且按错的刻度拉伸——这正是 P1-9。而同一文件里 updateSwipe
 * （滑动对比线）早就用对了这套几何。这里把它抽成单一出处，toImg / overlay 定位 / swipe 共用，
 * 防止三份各写各的又漂移。
 *
 * 坐标一律相对 viewer 盒子（0,0 = viewer 左上角），CSS 像素；zoom=1 即「适应窗口」。
 */
export interface DisplayRect {
  /** 相对 viewer 盒子左边的像素偏移（已含居中留白与平移） */
  left: number;
  top: number;
  /** 图像显示宽/高（CSS 像素） */
  width: number;
  height: number;
}

export interface ViewGeom {
  /** viewer 盒子尺寸（CSS 像素） */
  boxW: number;
  boxH: number;
  /** 代理帧/图像像素尺寸（shm_ready 的 w/h） */
  frameW: number;
  frameH: number;
  /** 相对「适应窗口」的倍率：1 = Fit */
  zoom: number;
  /** 平移（CSS 像素） */
  panX: number;
  panY: number;
}

/** 适应窗口的等比缩放因子：长边贴边，短侧留白。任一维非正返回 0（还没量到）。 */
export function fitScaleOf(boxW: number, boxH: number, frameW: number, frameH: number): number {
  if (frameW <= 0 || frameH <= 0 || boxW <= 0 || boxH <= 0) return 0;
  return Math.min(boxW / frameW, boxH / frameH);
}

/**
 * 图像在 viewer 盒子里的实际显示矩形（contain 居中 + zoom 关于盒心 + 平移）。
 *
 * 口径与 updateSwipe 一致：显示宽 = frameW · fitScale · zoom，水平居中于盒子后再平移。
 * 因为图像是等比居中显示在盒子正中，盒心 == 图心，所以「关于盒心缩放」与「关于图心缩放」
 * 等价——scale(v.zoom)（transformOrigin: center center）落点与此式吻合。
 * 退化输入（尺寸 0）返回全 0，调用方据此跳过换算而不是画到 (NaN,NaN)。
 */
export function imageDisplayRect(g: ViewGeom): DisplayRect {
  const fit = fitScaleOf(g.boxW, g.boxH, g.frameW, g.frameH);
  if (fit <= 0) return { left: 0, top: 0, width: 0, height: 0 };
  const width = g.frameW * fit * g.zoom;
  const height = g.frameH * fit * g.zoom;
  const left = (g.boxW - width) / 2 + g.panX;
  const top = (g.boxH - height) / 2 + g.panY;
  return { left, top, width, height };
}

/**
 * 屏幕坐标（相对 viewer 盒子）→ 代理帧图像坐标。落在图像矩形外时仍返回线性外推的值，
 * 由调用方决定是否夹取——与 overlay 事件只在图像区内触发配合，正常笔迹都落在 [0,frameW] 内。
 */
export function clientToImage(relX: number, relY: number, g: ViewGeom): { x: number; y: number } | null {
  const r = imageDisplayRect(g);
  if (r.width <= 0 || r.height <= 0 || g.frameW <= 0 || g.frameH <= 0) return null;
  return { x: ((relX - r.left) / r.width) * g.frameW, y: ((relY - r.top) / r.height) * g.frameH };
}
