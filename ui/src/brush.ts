/**
 * 消除笔的画笔层：在**代理帧坐标系**里累积覆盖度，松手时编成行程编码发给引擎。
 *
 * 三件事必须在这里说清楚，否则后面每次改动都要重新想一遍：
 * 1. 坐标一律是代理帧像素（引擎会话尺寸 = shm_ready 的 w/h），不是 CSS 像素也不是原图像素。
 *    换算由 Viewer 负责（它知道 canvas.width 与显示矩形的比），这里只吃图像坐标。
 * 2. 传的是"这一笔新增的覆盖度"，不是整幅掩膜：一次痘印点击只有几十条行程
 *    （实测 13 条 / ~312 B），而逐像素 uint8 走 JSON 是 1.1 MB。控制通道是文本行，
 *    把它塞满等于自己造一个延迟尖峰。
 * 3. 值域是 0..255 的整数覆盖度。引擎侧再羽化并夹到 [0,1]；这里不做浮点，
 *    免得同一支笔在 JS 与 Python 各算一遍 soft 边缘、结果对不上。
 */

export type Rle = number[][];   // [[y, x, len, value255], ...]，与 engine/ops/inpaint.mask_from_rle 同构

export class BrushPad {
  w: number;
  h: number;
  /** 这一笔的覆盖度（0..255），每次 pointerdown 清零 */
  private cov: Uint8Array;
  /** 脏区闭区间（y0>y1 表示空）：只在 stamp/segment 写过的包围盒里扫描与清理。
   *
   * 为什么要脏区：上一版 `toRle()` 是逐像素扫整幅代理帧，实测与 Python 同构版本
   * 一样贵（1024×1280 量级要上百毫秒），而一笔只盖几十像素。脏区外恒为 0（构造/
   * reset 后如此，stamp 只写自己的包围盒），所以只扫脏区与逐像素扫全幅结果逐字相同。 */
  private y0 = 1;
  private y1 = 0;
  private x0 = 1;
  private x1 = 0;

  constructor(w: number, h: number) {
    this.w = w;
    this.h = h;
    this.cov = new Uint8Array(w * h);
  }

  /** 会话尺寸变了就必须重建：旧坐标对新图没有任何意义（引擎侧同一条规矩）。 */
  resize(w: number, h: number) {
    if (w !== this.w || h !== this.h) {
      this.w = w;
      this.h = h;
      this.cov = new Uint8Array(w * h);
      this.reset();
    }
  }

  reset() {
    // 只清上一笔碰过的包围盒：一整幅 fill(0) 要写 1.3 MB，而笔印只几 KB
    for (let y = this.y0; y <= this.y1; y++) {
      this.cov.fill(0, y * this.w + this.x0, y * this.w + this.x1 + 1);
    }
    this.y0 = 1; this.y1 = 0; this.x0 = 1; this.x1 = 0;
  }

  /** 把包围盒扩到 [ya..yb]×[xa..xb]（已夹在图内）。 */
  private grow(ya: number, yb: number, xa: number, xb: number) {
    if (this.y1 < this.y0) {
      this.y0 = ya; this.y1 = yb; this.x0 = xa; this.x1 = xb;
    } else {
      if (ya < this.y0) this.y0 = ya;
      if (yb > this.y1) this.y1 = yb;
      if (xa < this.x0) this.x0 = xa;
      if (xb > this.x1) this.x1 = xb;
    }
  }

  /** 盖一个圆笔印（图像坐标，半径也是图像像素）。同一笔内重叠取最大值，不做平均。 */
  stamp(cx: number, cy: number, r: number, value = 255) {
    const rr = Math.max(0.5, r);
    const ya = Math.max(0, Math.floor(cy - rr));
    const yb = Math.min(this.h - 1, Math.ceil(cy + rr));
    const xa = Math.max(0, Math.floor(cx - rr));
    const xb = Math.min(this.w - 1, Math.ceil(cx + rr));
    if (yb < ya || xb < xa) return;                      // 整支笔落在图外
    this.grow(ya, yb, xa, xb);
    for (let y = ya; y <= yb; y++) {
      const dy = y - cy;
      const dx = Math.sqrt(Math.max(0, rr * rr - dy * dy));
      const x0 = Math.max(0, Math.floor(cx - dx));
      const x1 = Math.min(this.w - 1, Math.ceil(cx + dx));
      const row = y * this.w;
      for (let x = x0; x <= x1; x++) {
        // 边缘一圈按到圆心距离衰减：硬边圆在 60 fps 下会显出一层锯齿台阶
        const d = Math.hypot(x - cx, y - cy);
        const v = d <= rr - 1 ? value : Math.round(value * Math.max(0, (rr - d) / 1.5));
        if (v > 0 && this.cov[row + x] < v) this.cov[row + x] = v;
      }
    }
  }

  /** 在两点之间连描（拖动采样的间隔可能大于笔半径，不补就会断线）。 */
  segment(x0: number, y0: number, x1: number, y1: number, r: number, value = 255) {
    const steps = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / Math.max(1, r * 0.5)));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      this.stamp(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, value);
    }
  }

  /** 逐行扫出等值行程；只扫脏区包围盒，空白行一个字也不产生。 */
  toRle(): Rle {
    const out: Rle = [];
    const { w, cov } = this;
    for (let y = this.y0; y <= this.y1; y++) {
      let x = this.x0;
      const row = y * w;
      const xe = this.x1;
      while (x <= xe) {
        const v = cov[row + x];
        if (v === 0) {
          x++;
          continue;
        }
        let e = x + 1;
        while (e <= xe && cov[row + e] === v) e++;
        out.push([y, x, e - x, v]);
        x = e;
      }
    }
    return out;
  }

  /** 给叠加层画预览用的 RGBA（半透明红）：只在有覆盖处写像素，其余全透明。
   *  叠加层尺寸与会话不一致时直接抛：静默错位等于把笔印画到别的坐标上。 */
  paintOverlay(target: ImageData) {
    const { w, h, cov } = this;
    if (target.width !== w || target.height !== h) {
      throw new Error(`叠加层尺寸 ${target.width}×${target.height} 与会话 ${w}×${h} 不符`);
    }
    const d = target.data;
    for (let i = 0; i < cov.length; i++) {
      const v = cov[i];
      const o = i * 4;
      if (v === 0) {
        d[o + 3] = 0;
        continue;
      }
      d[o] = 255;
      d[o + 1] = 40;
      d[o + 2] = 60;
      d[o + 3] = Math.min(255, 60 + v * 0.6);
    }
  }

  /** 脏区内的覆盖像素数（引擎也会报一份，这里只给 UI 实时显示用）。 */
  coveredPixels(): number {
    let n = 0;
    for (let y = this.y0; y <= this.y1; y++) {
      const row = y * this.w;
      for (let x = this.x0; x <= this.x1; x++) if (this.cov[row + x] > 0) n++;
    }
    return n;
  }
}

/** 把一次点击近似成一个圆笔印（无拖动时）：给键盘/测试用的入口。 */
export function clickRle(w: number, h: number, cx: number, cy: number, r: number): Rle {
  const pad = new BrushPad(w, h);
  pad.stamp(cx, cy, r);
  return pad.toRle();
}
