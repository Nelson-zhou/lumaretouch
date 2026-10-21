import { comparisonFrameSize } from "../compareCapture";
/**
 * WebGL2 视口：rAF 驱动，从宿主取裸帧 → texSubImage2D → 绘制 → 双 rAF 后回执。
 *
 * 这里就是 M0 要量死的那一段：上传+绘制时长由 performance.now() 自测（时长差，
 * 不涉及跨进程时钟基准）；「引擎→上屏」的端到端值由 Rust 侧同基纳秒相减得出。
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { frameAcked, framePresented, isNoFrame, parseFrameHead, pullFrame, type ParsedFrame } from "../native";
import { BrushPad, type Rle } from "../brush";
import { imageDisplayRect, clientToImage } from "../view";

/** 视口的显示变换（平移/缩放）。它只改显示层的 CSS 变换：帧、回执、测量链一律不动。 */
export interface View {
  /** 相对「适应窗口」的倍率：1 = Fit。100% 由 App 用 1/(dpr*fitScale) 算出来。 */
  zoom: number;
  x: number;
  y: number;
  /** true = 当前就是 Fit；滚轮/100% 会把它置 false（顶栏据此显示“适合”还是百分比） */
  fit: boolean;
}
export const VIEW_HOME: View = { zoom: 1, x: 0, y: 0, fit: true };
/** 对比模式：单视图 / 并排 / 卷帘。原图那一帧由引擎 compare 提供，缓存在视口里。 */
export type CompareMode = "single" | "split" | "swipe";

/** 消除笔的视口接口：on=false 时叠加层不吃事件，测量回路一个字也不变。 */
export interface BrushProps {
  on: boolean;
  /** 笔刷半径（代理帧像素） */
  radius: number;
  /** 松手时把这一笔的行程编码交出去（引擎只在这时算一次） */
  onStroke: (rle: Rle, pixels: number) => void;
}

/** 「框一位补脸」（LNX-PORTRAIT-006）的视口接口：on=false 时叠加层不吃事件。
 *
 * 与消除笔同一条约束：坐标只在 1:1 那一档映射（平移/缩放时锁），因为映射是按画布
 * 矩形算的，变换之后落点会偏——把用户框的位置算成另一块地方，比不响应更糟。 */
export interface PickProps {
  on: boolean;
  /** 松手时把归一化矩形 [x0,y0,x1,y1] 交出去：引擎在这一框上再跑一次真检测 */
  onRect: (rect: number[]) => void;
}

export interface Hud {
  seq: number;
  w: number;
  h: number;
  fps: number;
  lastError: string;
}

const VERT = `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() {
  v_uv = vec2(a_pos.x * 0.5 + 0.5, 0.5 - a_pos.y * 0.5); // Y 翻转：图像行主序 vs GL 纹理左下原点
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

const FRAG = `#version 300 es
precision mediump float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_tex;
void main() { o = texture(u_tex, v_uv); }`;

export default function Viewer({
  active,
  skipDraw = false,
  upload = "raw",
  ctxOpt = true,
  chunks = 1,
  mirrorOn = true,
  glVisible = false,
  brush,
  pick,
  view,
  onView,
  paintLocked = false,
  onHud,
  compareMode = "single",
  swipe = 0.5,
  onSwipe,
  originalFrame = null,
  onFitScale,
}: {
  active: boolean;
  /** 对照组：只走 IPC 不上传不绘制，用于分离「地板成本」与「上传绘制成本」 */
  skipDraw?: boolean;
  /**
   * 上传策略（M1-1 对比项，环境变量 LRT_UPLOAD 驱动）：
   *   raw      texSubImage2D(Uint8Array)——现状基准
   *   bitmap   createImageBitmap + texSubImage2D(ImageBitmap)，走 WebKit 另一条上传路径
   *   pingpong 两张纹理轮换，上传永不碰刚交给合成器的那张
   */
  upload?: "raw" | "bitmap" | "pingpong";
  /**
   * 单次上传的横向分块数。拐点实测在 3.3 MB 通过 / 4.1 MB 撞帧，位置接近 4 MiB
   * 命令缓冲分片上限——本字段就是用来验这个假设的：字节总量不变，只拆调用。
   * 1 = 不分块（原行为）。
   */
  chunks?: number;
  /**
   * 画布上下文属性优化（实测与上传策略正交，所以单列一个开关）：
   * 关掉 alpha 让合成器不再逐帧混合，并将 desynchronized 交给实现。
   * 用 LRT_NO_CTX=1 可关，做背靠背对照。
   */
  ctxOpt?: boolean;
  /** 显示层开关：GL 画布每帧镜像到一张 2D 画布（这台机器上 GL surface 不进页面合成，
   *  关掉它就回到"后备缓冲有内容、屏幕上看不见"的那个形状）。LRT_NO_MIRROR=1 可关。 */
  mirrorOn?: boolean;
  /** 对照实验用：把 GL 画布重新摆回可见位（LRT_GL_VISIBLE=1）。 */
  glVisible?: boolean;
  brush?: BrushProps;
  /** 框选补脸（只在按钮亮起时吃事件；平时叠加层与测量回路一个字也不变） */
  pick?: PickProps;
  /** 平移/缩放（只属于显示层：导出与引擎算的仍是那一份像素，缩放也不触发任何推理） */
  view: View;
  onView: (v: View) => void;
  /** 缩放/平移状态下锁画笔：笔迹坐标是按 1:1 那一档映射的，变换后落点会偏。
   *  宁可明着锁，也不画到别处去——那是"按了而画歪"最难查的一形。 */
  paintLocked?: boolean;
  onHud: (h: Hud) => void;
  compareMode?: CompareMode;
  /** 卷帘分界（图像宽度的 0–1） */
  swipe?: number;
  onSwipe?: (v: number) => void;
  /** Verified request-correlated original pixels. */
  originalFrame?: ParsedFrame | null;
  /** 把 Fit 倍率交给 App：100% = 1/(dpr*fitScale) 只能在这里算（视口知道画布与帧尺寸） */
  onFitScale?: (s: number) => void;
}) {
  // 变换只加在显示层（镜像画布）上：GL 渲染源与测量回路一个字也不改
  const coordinateLocked = paintLocked || compareMode !== "single";
  const brushActive = !!brush?.on && !coordinateLocked;
  const pickActive = !!pick?.on && !coordinateLocked;
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const onWheel = (e: React.WheelEvent) => {
    const next = Math.min(8, Math.max(0.05, view.zoom * Math.exp(-e.deltaY / 400)));
    if (Math.abs(next - view.zoom) < 1e-4) return;
    onView({ zoom: next, x: view.x, y: view.y, fit: false });
  };
  const panDown = (e: React.PointerEvent) => {
    // 卷帘模式：左键属于分界线；对比时也不许平移（两半必须同一坐标系）
    if (compareMode === "swipe") return;
    // 框选模式下左键属于"画一个框"，不属于平移：两种意图抢同一个手势时让编辑意图赢
    if (e.button !== 1 && !(e.button === 0 && !brushActive && !pickActive)) return;
    drag.current = { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const panMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    onView({ zoom: view.zoom, x: d.ox + (e.clientX - d.x), y: d.oy + (e.clientY - d.y), fit: view.fit });
  };
  const panUp = () => { drag.current = null; };
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const mirrorRef = useRef<HTMLCanvasElement | null>(null);
  // 显示层挂在 document.body 上（见下面 portal 那段），所以要跟着 .viewer 的实际矩形走
  const [box, setBox] = useState({ left: 0, top: 0, width: 0, height: 0 });
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const onHudRef = useRef(onHud);
  onHudRef.current = onHud;
  // 画笔参数走 ref：把 brush 放进 effect 依赖会让“开关画笔”重建整个 WebGL 测量回路，
  // 那既浪费一次 GL 上下文，也会把 M0 那条测量链拆散
  const brushRef = useRef(brush);
  brushRef.current = coordinateLocked && brush ? { ...brush, on: false } : brush;
  // 与 brush 同一条理由：把 pick 放进 effect 依赖会让"开关框选"重建整个 GL 测量回路
  const pickRef = useRef(pick);
  pickRef.current = coordinateLocked && pick ? { ...pick, on: false } : pick;
  const sizeRef = useRef({ w: 0, h: 0 });
  // 帧尺寸与 Fit 倍率：100% 的换算与卷帘的落点都靠它，不能靠猜
  const [frameDim, setFrameDim] = useState({ w: 0, h: 0 });
  const displayDim = comparisonFrameSize(frameDim.w, frameDim.h, compareMode);
  const fitScale = frameDim.w > 0 && box.width > 0 && box.height > 0
    ? Math.min(box.width / displayDim.w, box.height / displayDim.h) : 0;
  const fitScaleRef = useRef(fitScale); fitScaleRef.current = fitScale;
  const viewRef = useRef(view); viewRef.current = view;
  const compareRef = useRef(compareMode); compareRef.current = compareMode;
  const swipeRef = useRef(swipe); swipeRef.current = swipe;
  const originalRef = useRef(originalFrame); originalRef.current = originalFrame;
  const onSwipeRef = useRef(onSwipe); onSwipeRef.current = onSwipe;
  const updateSwipe = (e: React.PointerEvent) => {
    const el = boxRef.current;
    if (!el || !onSwipeRef.current) return;
    const r = el.getBoundingClientRect();
    const v = viewRef.current;
    // P1-9：与 toImg / overlay 定位共用同一份显示矩形口径（imageDisplayRect），
    // 不再各写各的。代数与旧式等价：left = r.left + (r.width-iw)/2 + v.x = r.left + d.left，
    // iw = d.width。滑动线一直是对的，这里只是把它收敛成单一出处、防止三份再漂移。
    const { w, h } = sizeRef.current;
    const d = imageDisplayRect({ boxW: r.width, boxH: r.height, frameW: w, frameH: h,
                                 zoom: v.zoom, panX: v.x, panY: v.y });
    if (d.width <= 0) return;
    const left = r.left + d.left;
    const frac = Math.min(0.96, Math.max(0.04, (e.clientX - left) / d.width));
    onSwipeRef.current(Math.round(frac * 1000) / 1000);
  };
  const swipeDrag = useRef(false);
  const swipeDown = (e: React.PointerEvent) => {
    if (compareMode !== "swipe" || e.button !== 0) return;
    swipeDrag.current = true;
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    updateSwipe(e);
    e.preventDefault();
  };
  const swipeMove = (e: React.PointerEvent) => {
    if (!swipeDrag.current) return;
    updateSwipe(e);
  };
  const swipeUp = (e: React.PointerEvent) => {
    if (!swipeDrag.current) return;
    swipeDrag.current = false;
    (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
  };
  // Fit 倍率变化时交给 App：100% 按钮与顶栏标签需要同一份数
  useEffect(() => { onFitScale?.(fitScale); }, [fitScale, onFitScale]);

  // 显示层的定位：这台机器上 .viewer 里的画布位图不进页面合成（GL 与 2D 都一样，实测
  // 挂在 document.body 上的 fixed 画布能正常显示），所以显示层必须离开这个子树。
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const sync = () => {
      const r = el.getBoundingClientRect();
      setBox({ left: r.left, top: r.top, width: r.width, height: r.height });
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    window.addEventListener("resize", sync);
    return () => { ro.disconnect(); window.removeEventListener("resize", sync); };
  }, []);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const overlay = overlayRef.current;
    // 显示层。这台机器（AMD + XWayland + WebKitGTK）上 WebGL 画布的内容不进页面合成：
    // 实测同一张截图里 canvas 的 CSS outline 抓得到、GL 内容抓不到，而把 GL 画布
    // drawImage 到一张 2D 画布后照片就正常显示了 —— 也就是说后备缓冲一直是好的，
    // 坏的是"GL surface → 屏幕"那一段。所以这里让 2D 画布做用户真正看到的画面，
    // GL 仍然照常渲染（测量链路、回执、画笔叠加层一个字都不动）。
    // 代价是每帧一次 drawImage；LRT_NO_MIRROR=1 可以关掉做背靠背对照。
    const mirror = mirrorRef.current;
    const mctx = (mirror && mirrorOn) ? mirror.getContext("2d", { alpha: false }) : null;
    // `preserveDrawingBuffer: true` 不是性能开关，是**正确性**开关：默认值 false 允许
    // 合成器在一个 vsync 之后就把画布后备缓冲清掉。跑帧流时每一帧都在重画，看不出来；
    // 静态图只送那一帧，下一个 vsync 之后用户面对的就是一块空缓冲——这就是装机版
    // “导入真图后视口全黑”的根因。历轮跑靶漏掉它，因为证据取的是 shm 那一帧（引擎→
    // 宿主那一段），而这件事发生在宿主→屏幕那一段；帧流又在跑，屏上“看着有东西”。
    // 两个分支都得带：ctxOpt 那条是实验对照用，默认走的是下面那条（M0 实测 ctx 属性
    // 无可复现收益，所以默认关），写漏一边就等于默认路径没修。
    const attrs: WebGLContextAttributes = ctxOpt
      ? { antialias: false, depth: false, alpha: false, desynchronized: true, powerPreference: "high-performance", preserveDrawingBuffer: true }
      : { antialias: false, depth: false, preserveDrawingBuffer: true };
    const gl = canvas.getContext("webgl2", attrs);
    if (!gl) {
      onHudRef.current({ seq: 0, w: 0, h: 0, fps: 0, lastError: "WebGL2 不可用" });
      return;
    }

    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        throw new Error(`着色器编译失败: ${gl.getShaderInfoLog(s)}`);
      }
      return s;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error(`链接失败: ${gl.getProgramInfoLog(prog)}`);
    }
    gl.useProgram(prog);

    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    // ping-pong 需要两张纹理：非 pingpong 策略永远只用 index 0，行为与原来一致
    const texs = [gl.createTexture()!, gl.createTexture()!];
    let texIdx = 0;
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texs[0]);
    gl.uniform1i(gl.getUniformLocation(prog, "u_tex"), 0);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    for (const t of texs) {
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    }
    gl.bindTexture(gl.TEXTURE_2D, texs[0]);

    let curW = 0;
    let curH = 0;
    // ---- 画笔叠加层：与 GL 测量回路同生命期，但不参与计时 ----
    const pad = new BrushPad(1, 1);
    const octx = overlay ? overlay.getContext("2d") : null;
    let painting = false;
    let lastPt = { x: 0, y: 0 };
    const toImg = (e: PointerEvent) => {
      const el = boxRef.current;
      const { w, h } = sizeRef.current;
      if (!el || !w || !h) return null;
      const br = el.getBoundingClientRect();
      const v = viewRef.current;
      // P1-9 修复：按图像「实际显示矩形」换算（contain 居中留白 + zoom + 平移），
      // 而不是铺满盒子的 overlay.getBoundingClientRect()。盒子宽高比≠图像时，
      // 上一版把整盒当整图，留白维度的落点会偏移、刻度被拉伸——画笔/框选画到错处。
      return clientToImage(e.clientX - br.left, e.clientY - br.top,
                           { boxW: br.width, boxH: br.height, frameW: w, frameH: h,
                             zoom: v.zoom, panX: v.x, panY: v.y });
    };
    const repaint = () => {
      if (!overlay || !octx) return;
      const { w, h } = sizeRef.current;
      if (!w || !h) return;
      if (overlay.width !== w || overlay.height !== h) {
        overlay.width = w;
        overlay.height = h;
      }
      const img = octx.createImageData(w, h);
      pad.paintOverlay(img);
      octx.putImageData(img, 0, 0);
    };
    let pickRect: { x0: number; y0: number; x1: number; y1: number } | null = null;
    /** 框选中的那一格画在叠加层上：先让笔刷那层照常重绘，再叠这个虚线框 */
    const repaintPick = () => {
      repaint();
      if (!pickRect || !octx) return;
      const { w } = sizeRef.current;
      octx.save();
      octx.strokeStyle = "rgba(90, 200, 255, 0.95)";
      octx.lineWidth = Math.max(2, w / 420);
      octx.setLineDash([Math.max(6, w / 90), Math.max(4, w / 130)]);
      octx.strokeRect(pickRect.x0, pickRect.y0,
                      pickRect.x1 - pickRect.x0, pickRect.y1 - pickRect.y0);
      octx.restore();
    };
    const onDown = (e: PointerEvent) => {
      const pk = pickRef.current;
      if (pk?.on && overlay && e.button === 0) {
        const p = toImg(e);
        if (!p) return;
        pickRect = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
        overlay.setPointerCapture(e.pointerId);
        repaintPick();
        e.preventDefault();
        return;
      }
      const b = brushRef.current;
      if (!b?.on || !overlay || e.button !== 0) return;
      const p = toImg(e);
      if (!p) return;
      painting = true;
      overlay.setPointerCapture(e.pointerId);
      pad.reset();
      lastPt = p;
      pad.stamp(p.x, p.y, b.radius);
      repaint();
      e.preventDefault();
    };
    const onMove = (e: PointerEvent) => {
      if (pickRect) {
        const p = toImg(e);
        if (!p) return;
        pickRect = { ...pickRect, x1: p.x, y1: p.y };
        repaintPick();
        return;
      }
      const b = brushRef.current;
      if (!painting || !b?.on) return;
      const p = toImg(e);
      if (!p) return;
      pad.segment(lastPt.x, lastPt.y, p.x, p.y, b.radius);
      lastPt = p;
      repaint();
    };
    const onUp = (e: PointerEvent) => {
      if (pickRect) {
        const { w, h } = sizeRef.current;
        const r = pickRect;
        pickRect = null;
        overlay?.releasePointerCapture(e.pointerId);
        repaint();
        const x0 = Math.min(r.x0, r.x1) / w, x1 = Math.max(r.x0, r.x1) / w;
        const y0 = Math.min(r.y0, r.y1) / h, y1 = Math.max(r.y0, r.y1) / h;
        // 太小的那一拖不当成"框了一个人"：误点的面积比一次点击还小，发过去只会得到
        // 一条"这一框里没有脸"，而用户不知道自己是误点
        if (x1 - x0 < 0.02 || y1 - y0 < 0.02) return;
        pickRef.current?.onRect([x0, y0, x1, y1]);
        return;
      }
      if (!painting) return;
      painting = false;
      overlay?.releasePointerCapture(e.pointerId);
      const rle = pad.toRle();
      const n = pad.coveredPixels();
      pad.reset();
      repaint();
      const b = brushRef.current;
      if (b?.on && rle.length > 0) b.onStroke(rle, n);   // 松手 = 唯一一次事件驱动
    };
    if (overlay) {
      overlay.addEventListener("pointerdown", onDown);
      overlay.addEventListener("pointermove", onMove);
      overlay.addEventListener("pointerup", onUp);
      overlay.addEventListener("pointercancel", onUp);
    }
    let stop = false;
    let drawn = 0;
    let fps = 0;
    let lastHudAt = 0;   // HUD 节流的上一次时刻（见 loop 末尾那段）
    let fpsWindowStart = performance.now();

    // 取帧与绘制解耦：早先的写法是在 rAF 里 await pullFrame()，排下一个 rAF 排在
    // await 之后，于是 IPC 往返与垂直同步串成一条链，帧率被系统性低估。
    // 现在每拍最多一个在途请求，响应落在哪一拍就在哪一拍上传。
    let pulling = false;
    let ready: ParsedFrame | null = null;
    // Snapshot identity is verified by the receipt, never arrival timing.
    const snap = document.createElement("canvas");
    const snapCtx = snap.getContext("2d", { alpha: false });
    let lastOriginal: ParsedFrame | null = null;
    let compositionDirty = false;
    let lastMode: CompareMode = "single";
    let lastSwipe = -1;
    const presentQueue: { seq: number; rafs: number }[] = [];

    const pump = () => {
      if (pulling) return;
      pulling = true;
      pullFrame()
        .then(async (buf) => {
          const f = parseFrameHead(buf);
          if (buf.byteLength !== 40 + f.pixelLen) {
            throw new Error(`响应长度异常: ${buf.byteLength} vs ${40 + f.pixelLen}`);
          }
          if (upload === "bitmap" && f.pixelLen > 0) {
            // Uint8ClampedArray 直接 view 宿主送来的字节，不再拷一份
            const view = new Uint8ClampedArray(buf, 40, f.pixelLen);
            f.bitmap = await createImageBitmap(new ImageData(view, f.w, f.rows), {
              colorSpaceConversion: "none",
              premultiplyAlpha: "none",
            });
          }
          ready = f;
        })
        .catch((e) => {
          if (!isNoFrame(e)) {
            onHudRef.current({ seq: 0, w: curW, h: curH, fps, lastError: String(e) });
          }
        })
        .finally(() => {
          pulling = false;
        });
    };

    const loop = () => {
      if (stop) return;
      pump();
      const f = ready;
      if (f) {
        ready = null;
        if (f.w !== curW || f.h !== curH) {
          curW = f.w;
          curH = f.h;
          canvas.width = f.w;
          canvas.height = f.h;
          // 叠加层与画笔垫必须跟着换尺寸：旧坐标对新图没有任何意义
          sizeRef.current = { w: f.w, h: f.h };
          setFrameDim({ w: f.w, h: f.h });
          snap.width = f.w; snap.height = f.h;
          lastOriginal = null;
          pad.resize(f.w, f.h);
          if (overlay) {
            overlay.width = f.w;
            overlay.height = f.h;
          }
          if (mirror) {
            mirror.width = f.w;
            mirror.height = f.h;
          }
          gl.viewport(0, 0, f.w, f.h);
          // 两张纹理都要存好存储，否则 ping-pong 切过去时是空纹理
          for (const t of texs) {
            gl.bindTexture(gl.TEXTURE_2D, t);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, f.w, f.h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
          }
          gl.bindTexture(gl.TEXTURE_2D, texs[texIdx]);
        }
        const t0 = performance.now();
        // pixelLen=0 是宿主对照组：字节根本没跨进程，自然也没得上传
        if (!skipDraw && f.pixelLen > 0) {
          if (upload === "pingpong") {
            // 先换张再上传：正被上一帧合成器读的纹理不写入，避开驱动的同纹理上传串行
            texIdx = 1 - texIdx;
            gl.bindTexture(gl.TEXTURE_2D, texs[texIdx]);
          }
          if (f.bitmap) {
            gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, f.y0, gl.RGBA, gl.UNSIGNED_BYTE, f.bitmap);
            f.bitmap.close(); // 不 close 就是每帧漏一个原生位图，600 帧下来胀得没法看
          } else if (chunks > 1 && f.rows > chunks) {
            // 同字节总量，拆成 chunks 次调用：验证尾部是不是单次超命令缓冲分片造成
            const band = Math.ceil(f.rows / chunks);
            for (let r = 0; r < f.rows; r += band) {
              const hh = Math.min(band, f.rows - r);
              gl.texSubImage2D(
                gl.TEXTURE_2D, 0, 0, f.y0 + r, f.w, hh, gl.RGBA, gl.UNSIGNED_BYTE,
                f.pixels.subarray(r * f.w * 4, (r + hh) * f.w * 4),
              );
            }
          } else {
            gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, f.y0, f.w, f.rows, gl.RGBA, gl.UNSIGNED_BYTE, f.pixels);
          }
          gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
          // 一次 drawImage：把这一帧交给用户实际看到的那张画布；对比模式在这张
          // 2D 画布上叠原图（GL 渲染与测量链路一个字不动）。
          compositionDirty = true;
        } else if (f.bitmap) {
          f.bitmap.close();
        }
        const drawUs = (performance.now() - t0) * 1000;
        drawn += 1;
        // 绘制命令发出的当拍就 ack：pull_to_ack 里不再掺进整整一个帧周期
        frameAcked(f.seq, drawUs).catch(() => undefined);
        presentQueue.push({ seq: f.seq, rafs: 0 });
      }
      // 「上屏」没有可靠事件可用，退而求其次：本帧之后又跑了两个 rAF，
      // 合成器就已经拿它画过一整屏了。这一段仍由原生时钟打点。
      for (const p of presentQueue) p.rafs += 1;
      while (presentQueue.length && presentQueue[0].rafs >= 2) {
        const p = presentQueue.shift()!;
        framePresented(p.seq).catch(() => undefined);
      }
      const now = performance.now();
      const turned = now - fpsWindowStart >= 500;
      if (turned) {
        fps = (drawn * 1000) / (now - fpsWindowStart);
        drawn = 0;
        fpsWindowStart = now;
      }
      // HUD 更新：帧到达就得报，但每帧回调会拖着整个 React 面板做 60 次/秒重渲染
      // （那本身是要测的开销），所以跑帧流时按统计窗口翻转 + 250 ms 节流。
      // 上一版把它整个挂在"翻转那一拍恰好有帧"里，于是**静态图永远不更新**：一张
      // 443×553 的 PNG 导入成功、宿主已送出 4 帧，HUD 却写着「序号 0 · 分辨率 0×0 ·
      // 0.0 fps」——用户拿它判断"图进来了没有"，它就在这里骗人。
      if (f && (turned || now - lastHudAt >= 250)) {
        lastHudAt = now;
        onHudRef.current({ seq: f.seq, w: curW, h: curH, fps, lastError: "" });
      }
      // Wipe/mode changes repaint even when no new engine frame is available.
      if (mctx && curW > 0 && curH > 0) {
        const original = originalRef.current;
        if (original !== lastOriginal) {
          lastOriginal = original;
          compositionDirty = true;
          snap.width = original?.w ?? 0; snap.height = original?.h ?? 0;
          if (original && snapCtx) {
            snapCtx.putImageData(new ImageData(new Uint8ClampedArray(original.pixels), original.w, original.h), 0, 0);
          }
        }
        const mode = compareRef.current;
        if (mode !== lastMode || swipeRef.current !== lastSwipe) compositionDirty = true;
        lastMode = mode; lastSwipe = swipeRef.current;
        if (compositionDirty) {
          if (mirror) {
            const width = comparisonFrameSize(curW, curH, mode).w;
            if (mirror.width !== width) mirror.width = width;
          }
          // Texture storage survives WebGL drawing-buffer presentation. Redraw
          // it for display-only changes; do not copy a second full image per frame.
          if (!f) gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
          if (mode !== "split" || !original) mctx.drawImage(canvas, 0, 0);
          if (original && snap.width === curW && snap.height === curH) {
            if (mode === "split") {
              // Whole photographs on both sides, not unrelated half-image crops.
              mctx.fillStyle = "#16191e"; mctx.fillRect(0, 0, curW * 2, curH);
              mctx.drawImage(snap, 0, 0);
              mctx.drawImage(canvas, curW, 0);
            } else if (mode === "swipe") {
              const x = Math.max(0, Math.min(curW, Math.round(curW * swipeRef.current)));
              mctx.save(); mctx.beginPath(); mctx.rect(0, 0, x, curH); mctx.clip();
              mctx.drawImage(snap, 0, 0); mctx.restore();
              mctx.fillStyle = "rgba(227,193,118,.95)"; mctx.fillRect(x - 1, 0, 2, curH);
            }
          }
          compositionDirty = false;
        }
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);

    return () => {
      stop = true;
      if (overlay) {
        overlay.removeEventListener("pointerdown", onDown);
        overlay.removeEventListener("pointermove", onMove);
        overlay.removeEventListener("pointerup", onUp);
        overlay.removeEventListener("pointercancel", onUp);
      }
      for (const t of texs) gl.deleteTexture(t);
      gl.deleteProgram(prog);
      gl.deleteBuffer(vbo);
      gl.deleteVertexArray(vao);
    };
  }, [active, skipDraw, upload, ctxOpt, chunks, mirrorOn]);

  // P1-9：把画笔叠加层摆到「图像实际显示矩形」上（与 mirror 的 contain 留白 + zoom + 平移
  // 同一口径）。上一版 overlay 靠 CSS inset:0 铺满整个 viewer 盒子，与留白后的图像对不齐，
  // 笔迹既显示错位、toImg 发往引擎的坐标也跟着错。摆到显示矩形后，overlay 缓冲区 w×h 等比
  // 拉伸到 dispW×dispH（保持图像宽高比），与镜像层逐像素对齐。
  const disp = imageDisplayRect({ boxW: box.width, boxH: box.height,
                                  frameW: displayDim.w, frameH: displayDim.h,
                                  zoom: view.zoom, panX: view.x, panY: view.y });
  const overlayStyle: React.CSSProperties = {
    position: "absolute", right: "auto", bottom: "auto",
    left: disp.left, top: disp.top, width: disp.width, height: disp.height,
  };

  return (
    <>
      <div className={"viewer" + (compareMode === "swipe" ? " swipe" : "")}
           ref={boxRef} onWheel={onWheel}
           onPointerDown={(e) => { swipeDown(e); panDown(e); }}
           onPointerMove={(e) => { swipeMove(e); panMove(e); }}
           onPointerUp={(e) => { swipeUp(e); panUp(); }}
           onPointerCancel={(e) => { swipeUp(e); panUp(); }}
           onDoubleClick={() => onView(VIEW_HOME)}
           title="滚轮缩放 · 拖拽平移 · 双击适应窗口">
        {/* GL 画布退成纯渲染源：不参与布局，也不指望它上屏（见上面那段）。 */}
        {/* glVisible 是给"官方开关能不能替掉镜像层"那个对照实验用的：把 GL 画布放回
            可见位，看它自己上不上得了屏。生产路径不依赖它。 */}
        <canvas ref={canvasRef} className={glVisible ? "gl-src visible" : "gl-src"} />
        <canvas ref={overlayRef} className={brushActive ? "overlay on" : "overlay"}
                style={overlayStyle} />
        {compareMode !== "single" && originalFrame && (
          <div className="cmpTags">
            <span>原图</span>
            <span>精修</span>
          </div>
        )}
        {compareMode === "swipe" && <div className="cmpHint">拖动分界线对比</div>}
        {compareMode !== "single" && (brush?.on || pick?.on) &&
          <div className="cmpHint">请切回单视图使用画笔或框选人物</div>}
      </div>
      {/* 显示层：portal 到 document.body 的 fixed 画布，每帧由 GL 画布 drawImage 填进来。
          放在 body 上不是随手试出来的——实测这个子树外的画布才进得了页面合成。 */}
      {createPortal(
        // 裁切层必须是独立的一层：放大后的画布会盖住顶栏与右栏，
        // 只靠 viewer 的 overflow 管不到挂在 body 上的 fixed 画布。
        <div className="mirrorClip"
             // 视口的“当前 Fit 倍率 / 帧尺寸”画在 DOM 上：自动探针（M0_SPEC 的
             // 100% 那一格）与将来任何外部度量都要一个不改 state 就能读到的出处。
             // React 的状态在长命 effect 的闭包里是首帧那份，读它会把 100% 算错。
             data-fit-scale={fitScale.toFixed(4)}
             data-frame={`${frameDim.w}x${frameDim.h}`}
             style={{ left: box.left, top: box.top, width: box.width, height: box.height }}>
          <canvas
            ref={mirrorRef}
            className="mirror"
            style={{ width: "100%", height: "100%",
                     transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`,
                     transformOrigin: "center center" }}
          />
        </div>,
        document.body,
      )}
    </>
  );
}
