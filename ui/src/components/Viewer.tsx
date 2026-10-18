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
  mirrorOn = true,
  glVisible = false,
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
  /** 显示层开关：GL 画布每帧镜像到一张 2D 画布（这台机器上 GL surface 不进页面合成，
   *  关掉它就回到"后备缓冲有内容、屏幕上看不见"的那个形状）。LRT_NO_MIRROR=1 可关。 */
  mirrorOn?: boolean;
  /** 对照实验用：把 GL 画布重新摆回可见位（LRT_GL_VISIBLE=1）。 */
  glVisible?: boolean;
  brush?: BrushProps;
  onHud: (h: Hud) => void;
}) {
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
  brushRef.current = brush;
  const sizeRef = useRef({ w: 0, h: 0 });

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
    let lastHudAt = 0;   // HUD 节流的上一次时刻（见 loop 末尾那段）
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
          // 一次 drawImage：把这一帧交给用户实际看到的那张画布。
          if (mctx) mctx.drawImage(canvas, 0, 0);
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

  return (
    <>
      <div className="viewer" ref={boxRef}>
        {/* GL 画布退成纯渲染源：不参与布局，也不指望它上屏（见上面那段）。 */}
        {/* glVisible 是给"官方开关能不能替掉镜像层"那个对照实验用的：把 GL 画布放回
            可见位，看它自己上不上得了屏。生产路径不依赖它。 */}
        <canvas ref={canvasRef} className={glVisible ? "gl-src visible" : "gl-src"} />
        <canvas ref={overlayRef} className={brush?.on ? "overlay on" : "overlay"} />
      </div>
      {/* 显示层：portal 到 document.body 的 fixed 画布，每帧由 GL 画布 drawImage 填进来。
          放在 body 上不是随手试出来的——实测这个子树外的画布才进得了页面合成。 */}
      {createPortal(
        <canvas
          ref={mirrorRef}
          className="mirror"
          style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
        />,
        document.body,
      )}
    </>
  );
}
