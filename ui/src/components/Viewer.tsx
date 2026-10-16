/**
 * WebGL2 视口：rAF 驱动，从宿主取裸帧 → texSubImage2D → 绘制 → 双 rAF 后回执。
 *
 * 这里就是 M0 要量死的那一段：上传+绘制时长由 performance.now() 自测（时长差，
 * 不涉及跨进程时钟基准）；「引擎→上屏」的端到端值由 Rust 侧同基纳秒相减得出。
 */
import { useEffect, useRef } from "react";
import { frameAcked, framePresented, isNoFrame, parseFrameHead, pullFrame, type ParsedFrame } from "../native";
import { BrushPad, type Rle } from "../brush";

/** 消除笔的视口接口：on=false 时叠加层不吃事件，测量回路一个字也不变。 */
export interface BrushProps {
  on: boolean;
  /** 笔刷半径（代理帧像素） */
  radius: number;
  /** 松手时把这一笔的行程编码交出去（引擎只在这时算一次） */
  onStroke: (rle: Rle, pixels: number) => void;
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
  brush,
  onHud,
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
  brush?: BrushProps;
  onHud: (h: Hud) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const onHudRef = useRef(onHud);
  onHudRef.current = onHud;
  // 画笔参数走 ref：把 brush 放进 effect 依赖会让“开关画笔”重建整个 WebGL 测量回路，
  // 那既浪费一次 GL 上下文，也会把 M0 那条测量链拆散
  const brushRef = useRef(brush);
  brushRef.current = brush;
  const sizeRef = useRef({ w: 0, h: 0 });

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const overlay = overlayRef.current;
    const attrs: WebGLContextAttributes = ctxOpt
      ? { antialias: false, depth: false, alpha: false, desynchronized: true, powerPreference: "high-performance" }
      : { antialias: false, depth: false };
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
      if (!overlay) return null;
      const r = overlay.getBoundingClientRect();
      const { w, h } = sizeRef.current;
      if (!w || !h || r.width <= 0 || r.height <= 0) return null;
      // CSS 像素 → 代理帧像素：引擎只认会话尺寸，拿屏幕坐标发过去会画到错的地方，
      // 而且尺寸比不等于 1 时错得看不见
      return { x: ((e.clientX - r.left) / r.width) * w, y: ((e.clientY - r.top) / r.height) * h };
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
    const onDown = (e: PointerEvent) => {
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
      const b = brushRef.current;
      if (!painting || !b?.on) return;
      const p = toImg(e);
      if (!p) return;
      pad.segment(lastPt.x, lastPt.y, p.x, p.y, b.radius);
      lastPt = p;
      repaint();
    };
    const onUp = (e: PointerEvent) => {
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
    let fpsWindowStart = performance.now();

    // 取帧与绘制解耦：早先的写法是在 rAF 里 await pullFrame()，排下一个 rAF 排在
    // await 之后，于是 IPC 往返与垂直同步串成一条链，帧率被系统性低估。
    // 现在每拍最多一个在途请求，响应落在哪一拍就在哪一拍上传。
    let pulling = false;
    let ready: ParsedFrame | null = null;
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
          pad.resize(f.w, f.h);
          if (overlay) {
            overlay.width = f.w;
            overlay.height = f.h;
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
      if (now - fpsWindowStart >= 500) {
        fps = (drawn * 1000) / (now - fpsWindowStart);
        drawn = 0;
        fpsWindowStart = now;
        // HUD 只在统计窗口翻转时更新：每帧回调会拖着整个 React 面板做 60 次/秒
        // 重渲染，而那本身就是要测的那段开销，不能让它留在测量回路里。
        if (f) onHudRef.current({ seq: f.seq, w: curW, h: curH, fps, lastError: "" });
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
  }, [active, skipDraw, upload, ctxOpt, chunks]);

  return (
    <div className="viewer">
      <canvas ref={canvasRef} />
      <canvas ref={overlayRef} className={brush?.on ? "overlay on" : "overlay"} />
    </div>
  );
}
