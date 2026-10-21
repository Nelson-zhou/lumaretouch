/** Optional packaged viewport diagnostics. Never owns production engine startup. */
import {useEffect,type Dispatch,type SetStateAction} from 'react';
import {getCurrentWindow} from '@tauri-apps/api/window';
import {engineStatus,loadImage,m0Env,parseFrameHead,peekFrame,report,setStrength,type EngineStatus} from '../native';
import {t} from '../i18n';
const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
let viewportProbeStarted=false;
export function useViewportProbe(setImgPath:Dispatch<SetStateAction<string>>){
  // 视口自证（M9 裁决3 的取证臂）：静态图导入后静置，读回画布缓冲并量布局矩形。
  // 单独一个 effect，不挂在 M0 跑靶那条链上：那条链的入口是 LRT_AUTO_BENCH，而这里要的
  // 恰恰是"不跑帧流"的静态状态——流在跑时每一帧都在重画，preserveDrawingBuffer 的后果
  // 根本显不出来。历轮跑靶就是这么漏掉黑屏的：帧一直在动，屏上就"看着有东西"。
  useEffect(() => {
    if (viewportProbeStarted) return;
    viewportProbeStarted = true;
    (async () => {
      const env = await m0Env().catch(() => null);
      if (!env?.viewport_probe) return;
      await getCurrentWindow().setFocus().catch(() => undefined);
      // 静态臂不跑 LRT_AUTO_BENCH，所以入图这步得自己做：用的就是用户那条导入命令
      // （onImport 里同一个 loadImage → Rust → 引擎 cmd_load_image），而不是另开一套
      // 测试专用通路——否则这一臂量的就不是用户那一条路。
      let importBtn: { found: boolean; text: string } = { found: false, text: "" };
      if (env.load_image) {
        if (/^manual/.test(env.viewport_probe)) {
          // 手动臂：只把路径填进输入框，然后真的去点「导入」那一个按钮。这一条走的是
          // onImport 全链（trim 校验、setBusy、loadImage、waitImportOutcome、就地红字），
          // 而不是探针直调 loadImage——用户报的那次黑屏发生在按钮这条路上，自动臂的
          // 读数替它不作证：两条路的差别正好可能是缺陷所在。
          setImgPath(env.load_image);
          await sleep(150);                       // 让 React 把 imgPath 提交进去
          const b = Array.from(document.querySelectorAll("button"))
            .find((x) => (x.textContent ?? "").trim() === t("retouch.import"));
          importBtn = { found: !!b, text: (b?.textContent ?? "").trim() };
          b?.click();
        } else {
          await loadImage(env.load_image, { maxPx: env.max_px ?? undefined, strength: 0, precompute: "auto" })
            .catch((e) => report(`M0_ERROR 视口探针导入失败: ${e}`));
        }
      }
      // 必须先等到真有一帧送达。探针在首帧之前跑会读到空缓冲，那种"黑"是这个缺陷的
      // 假阳性，量出来会把自己骗过去
      let st: EngineStatus | null = null;
      for (let i = 0; i < 200; i++) {
        st = await engineStatus().catch(() => null);
        if (st?.image) break;
        await sleep(250);
      }
      if (!st?.image) {
        await report("M0_ERROR 视口探针等不到 image（图没导进来，这一读不作数）");
        return;
      }
      const frameDims: [number, number] = [st.image.w, st.image.h];
      await sleep(800);                       // 静置：给合成器几个 vsync 的机会
      const cv = document.querySelector<HTMLCanvasElement>(".viewer .gl-src");
      const mir = document.querySelector<HTMLCanvasElement>("body > .mirror");
      const gl = cv?.getContext("webgl2");
      const rect = cv?.getBoundingClientRect();
      const hud = document.querySelector(".hud")?.getBoundingClientRect();
      const back: Record<string, number | number[] | string> = {};
      if (cv && gl && gl.drawingBufferWidth > 0) {
        const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
        const px = new Uint8Array(w * h * 4);
        gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
        let sum = 0, sq = 0, nb = 0;
        for (let i = 0; i < w * h; i++) {
          const l = (px[i * 4] + px[i * 4 + 1] + px[i * 4 + 2]) / 3;
          sum += l; sq += l * l; if (l > 4) nb++;
        }
        const mean = sum / (w * h);
        back.readMean = +mean.toFixed(2);
        back.readStd = +Math.sqrt(Math.max(0, sq / (w * h) - mean * mean)).toFixed(2);
        back.readNonBlack = +(nb / (w * h)).toFixed(4);
        // 与 shm 里那一帧逐字节比。不能拿原生顺序直接比：`readPixels` 的原点在
        // **左下**，而 shm 帧从左上起，不翻转就会把“整张垂直倒了”读成“字节对不上”；
        // alpha 也比不了（通路里 alpha 不参与显示）。两个读数都报：不比的是伪证据，
        // 只报一个则看不出差是几何来的还是内容来的。
        back.readDiffVsShm = -1;
        let f = null;
        try { f = parseFrameHead(await peekFrame()); } catch (e) { f = null; }
        if (f && f.w === w && f.h === h && f.pixels.length >= w * h * 4) {
          let raw = 0, flip = 0, row = w * 4;
          for (let r = 0; r < h; r++) {
            const top = r * row;                       // shm：第 r 行从顶上数
            const bot = (h - 1 - r) * row;             // readPixels：原点在左下
            for (let x = 0; x < w; x++) {
              const i = x * 4;
              for (let c = 0; c < 3; c++) {
                if (px[top + i + c] !== f.pixels[top + i + c]) raw++;
                if (px[bot + i + c] !== f.pixels[top + i + c]) flip++;
              }
            }
          }
          back.readDiffVsShm = raw;                    // 不翻转（只当参考）
          back.readDiffFlipRgb = flip;                 // 翻转后的 RGB 差异：这一条该为 0
        }
      }
      // 一刀两断的实验：给 canvas 元素本身刷一个刺眼的 CSS 背景再截图。截图抓不到 GL
      // 后备缓冲（M2-a2 已证），但 CSS 背景是 DOM 绘制、走页面合成那条路。
      //   截图这块变绿 → 页面合成能上屏、GL 内容上不了屏：黑屏是真的，缺陷在 GL→屏幕；
      //   截图仍是黑 → 截图对这个区域完全无效，"截图里黑"不能作为任何主张的证据。
      //
      // 实测落在第二种：绿色 CSS 背景没进截图（WebGL 后备缓冲盖住了元素背景），但
      // canvas 的 8px 品红 outline 进了——同一张图里"DOM 有效、GL 无效"同时成立，于是
      // 用户报的那次黑屏被判定为**截图伪影**，不是缺陷；下面那个 toDataURL→<img> 才是
      // 正面证据：照片清晰、方向正确地显示在页面上。这一臂留着，以后"黑屏"主张一律先
      // 走它，别再拿 readPixels 当"上屏"的证据——那是后备缓冲，它有没有内容和屏幕上
      // 看不看得到是两段路。
      if (/lime/.test(env.viewport_probe) && cv) {
        cv.style.background = "#00ff00";
        cv.style.outline = "8px solid #ff00ff";
        // 最后一击：把 GL 后备缓冲转成 <img> 贴进 DOM。img 走页面合成，截图一定能反映——
        // 于是"屏幕上到底有没有这张照片"就不再依赖任何推断（preserveDrawingBuffer:true
        // 正是为了让 toDataURL 拿得到内容，而不是拿到一张空图）。
        let dump = "";
        try {
          const url = cv.toDataURL("image/png");
          const el = document.createElement("img");
          el.src = url;
          Object.assign(el.style, { position: "fixed", left: "540px", top: "40px", width: "300px", border: "4px solid #ffffff", zIndex: "9999" });
          document.body.appendChild(el);
          dump = url.slice(0, 22) + `…len=${url.length}`;
        } catch (e) { dump = `toDataURL 失败: ${String(e)}`; }
        await report(`M0_LIME ${JSON.stringify({cssBg: getComputedStyle(cv).backgroundColor, rect: [cv.getBoundingClientRect().width, cv.getBoundingClientRect().height], dump})}`);
      }
      // 通路选型实验：2D canvas 的 putImageData 在这台机器上能不能被看见（判据用
      // "X 抓图抓不抓得到"，因为抓得到就等于它进了页面合成，屏幕必然也有）。
      // 抓得到 → 视口可以从 WebGL 换成 2D 通路；抓不到 → 只能退到 <img>。
      if (/twod/.test(env.viewport_probe) && cv && gl) {
        // 不另开一条取帧路（Viewer 的回路会把 pullFrame 那帧抢走），直接把 GL 画布
        // drawImage 镜像到一张 2D 画布——这也正是候选修法本身：每帧一次 drawImage。
        try {
          const c2 = document.createElement("canvas");
          c2.width = cv.width; c2.height = cv.height;
          Object.assign(c2.style, { position: "fixed", left: "540px", top: "60px", width: "300px",
                                    border: "4px solid #ffffff", zIndex: "9999", background: "#000" });
          c2.getContext("2d")!.drawImage(cv, 0, 0);
          document.body.appendChild(c2);
          const t = document.createElement("img");
          t.src = cv.toDataURL("image/png");
          Object.assign(t.style, { position: "fixed", left: "880px", top: "60px", width: "300px", border: "4px solid #ff00ff" });
          document.body.appendChild(t);
          await report(`M0_TWOD ${JSON.stringify({ mirrored: [cv.width, cv.height] })}`);
        } catch (e) { await report(`M0_TWOD_FAIL ${String(e)}`); }
      }
      // 显示层自己的读数：拿 2D getImageData 从 mirror 画布上读，这是"用户实际看到的
      // 那张画布"的内容，与 GL 后备缓冲分开的第二条证据。
      if (mir) {
        const m2 = mir.getContext("2d");
        if (m2 && mir.width > 0) {
          const d = m2.getImageData(0, 0, mir.width, mir.height).data;
          let ms = 0, mn = 0;
          for (let i = 0; i < mir.width * mir.height; i++) {
            const l = (d[i * 4] + d[i * 4 + 1] + d[i * 4 + 2]) / 3;
            ms += l; if (l > 4) mn++;
          }
          const mr = mir.getBoundingClientRect();
          back.mirrorDims = [mir.width, mir.height];
          back.mirrorCss = [+mr.width.toFixed(1), +mr.height.toFixed(1)];
          back.mirrorMean = +(ms / (mir.width * mir.height)).toFixed(2);
          back.mirrorNonBlack = +(mn / (mir.width * mir.height)).toFixed(4);
        } else {
          back.mirrorFail = "no 2d ctx";
        }
      }
      // 对比按钮的真窗口自证：把强度拉到最大（半径也拉大，让差异看得见），然后真的对
      // 那个按钮派发 pointerdown/pointerup——走的是 cmpOn/cmpOff 同一条 React 处理链，
      // 不是另开一条测试通路。外部在 HELD 与 RELEASED 两段各截一张图，比对视口像素：
      // 两张一样就说明按钮没作用，这里必须让它红。
      if (/cmp/.test(env.viewport_probe)) {
        const btn = Array.from(document.querySelectorAll("button"))
          .find((b) => (b.textContent ?? "").trim() === t("retouch.compare")) as HTMLButtonElement | undefined;
        await report(`M0_CMP_ARMED ${JSON.stringify({ found: !!btn, disabled: !!btn?.disabled })}`);
        if (btn) {
          await setStrength(1.0, { radius: 40 }).catch(() => undefined);
          await sleep(600);
          btn.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, pointerId: 7, isPrimary: true }));
          await report("M0_CMP_HELD");            // 外部：这一拍截"原图"
          await sleep(3200);
          btn.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, pointerId: 7, isPrimary: true }));
          await report("M0_CMP_RELEASED");        // 外部：这一拍截"修好的图"
          await sleep(1600);
        }
      }
      const scrollH = document.documentElement.scrollHeight;
      // 反向门（裁决3）：写一个不存在的路径再点「导入」，输入框下方必须出现红字。
      // 这条不是装饰：“错了但不说”就是这次缺陷的本体，门不会关就等于没修。
      let negErrText = "";
      const browseBtns = Array.from(document.querySelectorAll("button"))
        .filter((b) => (b.textContent ?? "").includes("浏览") || (b.textContent ?? "").includes("Browse")).length;
      try {
        setImgPath("/definitely-not-here.jpg");
        await sleep(80);
        const btn = Array.from(document.querySelectorAll("button"))
          .find((b) => (b.textContent ?? "").trim() === t("retouch.import"));
        btn?.click();
        for (let i = 0; i < 40 && !negErrText; i++) {
          await sleep(100);
          negErrText = (document.querySelector(".err")?.textContent ?? "").trim();
        }
        setImgPath("");
      } catch (e) {
        negErrText = `反向门自身异常: ${String(e)}`;   // 异常也要报出来，不许静默吞掉
      }
      await report(`M0_VIEWPORT ${JSON.stringify({
        tag: env.viewport_probe, hasCanvas: !!cv, hasGL: !!gl, importBtn,
        drawingBuffer: [gl?.drawingBufferWidth ?? 0, gl?.drawingBufferHeight ?? 0],
        frameDims, canvasCss: rect ? [Math.round(rect.width), Math.round(rect.height), Math.round(rect.bottom)] : null,
        canvasBottom: rect ? Math.round(rect.bottom) : -1,
        hudBottom: hud ? Math.round(hud.bottom) : -1,
        innerW: window.innerWidth, innerH: window.innerHeight,
        scrollH, overflowing: scrollH > window.innerHeight,
        browseBtns, negErrText,
        ...back,
      })}`);
    })();
  }, []);

}
