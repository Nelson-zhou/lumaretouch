/** Environment-opted-in acceptance harness, separate from interactive product state.
 * Keep each historical check intact while production App delegates orchestration.
 * This runs in packaged builds too; DEV-only gating would remove acceptance coverage.
 */
import {useEffect,type Dispatch,type SetStateAction} from 'react';
import {getCurrentWindow} from '@tauri-apps/api/window';
import type {View,Hud} from '../components/Viewer';
import {clickRle} from '../brush';
import {benchStart,benchStats,engineStatus,faceStateOf,fetchFilmstrip,loadImage,m0Env,parseFrameHead,peekFrame,quit,report,runBackground,runCrop,runDeform,runEnhance,runExport,runExposure,runFace,runGrade,runHistory,runHsl,runInpaint,runLight,runLut,runPick,runPrecompute,runSession,setStrength,startEngine,
  type BackgroundInfo,type DeformInfo,type DocState,type EngineRuntime,type EngineStatus,type EnhanceInfo,type ExportDone,type GradeInfo,type ImageReady,type InpaintInfo,type LightInfo,type LutInfo,type PickRun,type Precompute,type SessionState,type BenchOptions} from '../native';
const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
let m0Started=false;
/** 解析 "1280x800:600:16.7:copy"。 */
function parseAutoBench(spec: string) {
  const [dims, frames, interval, mode] = spec.split(":");
  const [w, h] = dims.split("x").map(Number);
  if (!w || !h || !frames) return null;
  return { w, h, frames: +frames, intervalMs: +(interval || 16.7), mode: (mode || "copy") as BenchOptions["mode"] };
}

type Setter<T>=Dispatch<SetStateAction<T>>;
export interface BenchmarkContext {
  setUpload:Setter<'raw'|'bitmap'|'pingpong'>;
  setCtxOpt:Setter<boolean>;setMirrorOn:Setter<boolean>;setGlVisible:Setter<boolean>;
  setSkipDraw:Setter<boolean>;setOneToOne:Setter<boolean>;
  setChunks:Setter<number>;setTierLabel:Setter<string>;setPid:Setter<number|null>;
  setView:Setter<View>;
  strengthRef:Readonly<{current:number}>;
  applied:Readonly<{current:{strength:number;from:string}|null}>;
  hudRef:Readonly<{current:Hud}>;
  refreshStatus:()=>Promise<EngineStatus|undefined>;
}
export function useBenchmarkAutomation({setUpload,setCtxOpt,setMirrorOn,setGlVisible,setChunks,setSkipDraw,setTierLabel,setPid,setOneToOne,setView,strengthRef,refreshStatus,applied,hudRef}:BenchmarkContext){
  // M0 自动跑靶通道
  useEffect(() => {
    if (m0Started) return;
    m0Started = true;
    (async () => {
      const env = await m0Env().catch(() => null);
      if (!env) return;
      // 渲染/显示配置与"跑不跑靶"无关，必须先读、再管 spec。原来这整段挂在
      // `if (!env || !spec) return` 之后，于是静态探针臂里 LRT_NO_CTX / LRT_NO_MIRROR /
      // LRT_GL_VISIBLE **全是死的**：我拿"两臂读数完全一致"当成 desynchronized 假设被
      // 证伪，而实际上那两臂根本没换过配置。开关不生效比开关不存在更危险——它会产出
      // 一份看起来像对照实验、其实什么都没有做的结论。
      const known = ["raw", "bitmap", "pingpong"] as const;
      if ((known as readonly string[]).includes(env.upload)) {
        setUpload(env.upload as (typeof known)[number]);
      }
      // ctx 属性无可复现收益（两轮背靠背：1/5 vs 3/5 vs 3/5 撞帧，均在 ±3fps 噪声内），
      // 故默认关；保留 LRT_NO_CTX / 开关只做后续对照实验用。
      setCtxOpt(env.no_ctx === "0");
      setMirrorOn(env.no_mirror !== "1");
      setGlVisible(env.gl_visible === "1");
      setChunks(env.chunks > 1 ? env.chunks : 1);
      const spec = env.auto_bench;
      if (!spec) {
        // 门还是那道门（起靶必须先于任何臂），但**过不了门要自己报**。1.6.0 那一轮
        // 第 7 臂就是撞在这里：脚本忘传 LRT_AUTO_BENCH，整条自动序列一声不响地
        // return，外面只能等满 900 s 拿到一句"没跑完"——静默的失败比失败更坏。
        const wanted = (["auto_pick", "auto_filmstrip", "auto_face", "auto_history",
          "auto_export", "auto_background", "auto_local_color", "auto_grade",
          "auto_manual"] as const)
          .filter((k) => !!(env as unknown as Record<string, string>)[k]);
        if (wanted.length) {
          await report("M0_ERROR 自动序列没起跑：这些臂挂了，但整段序列要求 LRT_AUTO_BENCH "
            + "先过门（缺它=静默 return）：" + wanted.join(","));
        }
        return;
      }
      // WebKit 会节流不可见/未聚焦窗口的 rAF，跑靶前必须把窗口拉到前台
      await getCurrentWindow().setFocus().catch(() => undefined);
      const skipPixels = env.skip_pixels === "1";
      // tier0 连像素都不传，上传/绘制自然没得做
      setSkipDraw(env.skip_draw === "1" || skipPixels);
      setTierLabel(skipPixels ? "tier0" : env.skip_draw === "1" ? "tier1" : "tier2");
      const bench = parseAutoBench(spec);
      if (!bench) {
        await report(`M0_ERROR 无法解析 LRT_AUTO_BENCH=${spec}`);
        return;
      }
      try {
        const r = await startEngine(env.engine_py, env.engine_src);
        setPid(r.pid);
      } catch (e) {
        await report(`M0_ERROR 引擎启动失败: ${e}`);
        return;
      }
      // 发布自检（M5-c 开箱即用）自动通道：LRT_AUTO_RELEASE=1。
      // 装机件在**没有任何开发 env** 的机器上，必须能一句话说清："引擎跑在哪个
      // 解释器、它是从候选表哪一档来的、版本与包账单对不对、hello 报的能力到没到"。
      // 这几件事错了都不崩，只是让"开箱即用"实际变成"在这台开发机上碰巧能跑"。
      // 位置要紧：这一条紧跟 startEngine、在导任何图**之前**。运行时缺包时引擎
      // 当场就死，后面那句 "load_image 未就绪" 会整段 return——把自检放在那之后，
      // 最需要它报账的那一种情形就永远不报，剩下的只有"没跑完"这种模糊读数。
      if (env.auto_release) {
        let st = await engineStatus().catch(() => null);
        for (let i = 0; i < 50; i++) {
          const rt0 = st?.engine_runtime ?? {};
          // ready 到了才会有包账单（packages 一层）里的 torch 键；引擎已经死了也立刻收工
          if (rt0.packages?.torch !== undefined || st?.engine_alive === false) break;
          await sleep(100);
          st = await engineStatus().catch(() => null);
        }
        const rt: EngineRuntime = st?.engine_runtime ?? {};
        await report(`M0_RELEASE ${JSON.stringify({
          engineVersion: st?.engine_version ?? null,
          alive: st?.engine_alive ?? null,
          python: rt.python ?? null,
          // runtime = 候选表命中了装好的运行时；env/explicit = 开发覆盖；
          // fallback = 连候选表都没中，落到了 python3（几乎必然缺 torch）
          pythonSource: rt.python_source ?? null,
          pythonVersion: rt.python_version ?? null,
          engineSrc: rt.engine_src ?? null,
          pkgs: { numpy: rt.packages?.numpy ?? null, pillow: rt.packages?.pillow ?? null,
                  torch: rt.packages?.torch ?? null,
                  torchvision: rt.packages?.torchvision ?? null },
          caps: { presets: st?.presets?.length ?? -1,
                  gradeLimits: st?.grade_limits?.length ?? -1,
                  exportCaps: st?.export_caps ? 1 : 0,
                  editCmds: st?.history_edit_cmds?.length ?? -1,
                  // 能力上报的一致性（M8）：换底/放大两档后端清单必须由引擎自己报，
                  // 缺一项就是“装机件里 UI 在猜能力”——裸环境跑这一臂才能区分。
                  mattingCaps: st?.matting_backends ? 1 : 0,
                  mattingBaseline: st?.matting_backends?.baseline?.length ?? -1,
                  upscaleBackends: st?.export_caps?.upscale_backends ? 1 : 0 },
          hasShm: !!st?.has_shm,
        })}`);
      }
      let image: ImageReady | null = null;
      let pre: Precompute | null = null;
      if (env.load_image) {
        // 代理档尺寸由引擎决定（按像素预算+长宽比），跑靶得跟着它走，不能拿 spec 里的尺寸硬跑
        const wantPre = !!env.precompute && env.precompute !== "0";
        await loadImage(env.load_image, {
          maxPx: env.max_px ?? undefined,
          strength: 0,
          precompute: wantPre ? env.precompute : undefined,
          channel: env.precompute_channel || undefined,
        });
        // 轮询得同时等预计算：precompute_ready 就在 image_ready 后面几十毫秒，
        // 只盯 image 会在它到达前就 break 掉，报表上变成“导了图但没算掩膜”
        for (let i = 0; i < 300; i++) {
          await sleep(100);
          const st = await engineStatus().catch(() => null);
          image = st?.image ?? null;
          pre = st?.precompute ?? null;
          if (image && (!wantPre || pre)) break;
        }
        if (!image) {
          await report(`M0_ERROR load_image 30s 内未就绪: ${env.load_image}`);
          return;
        }
        if (wantPre && !pre) {
          // 预计算没就绪不能默默当“没这一步”：要么报错要么报缺，绝不给一份假的绿
          await report(`M0_ERROR precompute 30s 内未就绪（backend=${env.precompute}）`);
          return;
        }
        await report(`M0_IMAGE ${JSON.stringify(image)}`);
        if (pre) await report(`M0_PRECOMPUTE ${JSON.stringify(pre)}`);
        bench.w = image.w;
        bench.h = image.h;
      }
      // 消除笔自动通道（$LRT_AUTO_INPAINT="fx:fy:r,…"）：走的是与真人点击完全同一条链
      // ——brush.ts 的 toRle → runInpaint → Rust → 引擎 → inpaint_done。只有真窗口里
      // 跑通，才能说“图层常驻 + 拖拽期零重算”不是只在 pytest 的子进程里成立。
      if (env.auto_inpaint) {
        if (!image) {
          await report("M0_ERROR LRT_AUTO_INPAINT 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const w = image.w;
          const h = image.h;
          const waitInpaint = async (pred: (v: InpaintInfo) => boolean) => {
            for (let k = 0; k < 300; k++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.inpaint && pred(st.inpaint)) return st.inpaint;
            }
            return null;
          };
          const strokes = env.auto_inpaint.split(",").map((s) => s.trim()).filter(Boolean);
          let bad = "";
          let lastAdd: InpaintInfo | null = null;
          for (let i = 0; i < strokes.length; i++) {
            const [fx, fy, r] = strokes[i].split(":").map(Number);
            if (![fx, fy, r].every(Number.isFinite)) {
              bad = `第 ${i + 1} 段“${strokes[i]}”不是 fx:fy:r`;
              break;
            }
            await runInpaint("add", { rle: clickRle(w, h, fx * w, fy * h, r), feather: 2 });
            lastAdd = await waitInpaint((v) => v.action === "add" && v.ops === i + 1);
            if (!lastAdd) {
              bad = `第 ${i + 1} 笔 30s 内没等到 inpaint_done`;
              break;
            }
          }
          if (bad) {
            await report(`M0_ERROR 消除笔自动通道：${bad}`);
          } else {
            // undo/redo 各走一次：“只存输入”的重放在真窗口里逐笔可回退
            await runInpaint("undo");
            const u = await waitInpaint((v) => v.action === "undo" && v.ops === strokes.length - 1);
            await runInpaint("redo");
            const rd = await waitInpaint((v) => v.action === "redo" && v.ops === strokes.length);
            await report(`M0_INPAINT ${JSON.stringify(lastAdd)}`);
            await report(`M0_INPAINT_STACK ${JSON.stringify({
              strokes: strokes.length, undoOps: u?.ops ?? -1, redoOps: rd?.ops ?? -1,
              // filter_cached 由执行路径给出：重做后那一帧真的重算了滤波。
              // 不叫 cached：引擎侧那两个名字（本层重算/滤波命中）同名会互相覆盖
              filterCached: rd?.filter_cached ?? null,
              layerRecomputed: rd?.layer_recomputed ?? null,
              repairMs: rd?.repair_ms ?? null,
              totalMs: rd?.total_ms ?? null, paintedPx: lastAdd?.painted_px ?? null,
            })}`);
          }
        }
      }
      // 三条带增益自动通道（$LRT_AUTO_SKIN="mid:broad:detail"）：走的是与真人松手完全
      // 同一条链 —— setStrength → Rust set_strength → 引擎 params_set。引擎那条回显由
      // Rust 打到 stdout（M0_ENGINE …），跑靶脚本据此核对参数真的过了宿主这一层：
      // 命令签名改了而 TS 侧名字对不上时，Tauri 会静默丢掉那个参数，一个错也不报。
      if (env.auto_skin) {
        const nums = env.auto_skin.split(":").map(Number);
        if (nums.length !== 3 || !nums.every(Number.isFinite)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_SKIN=${env.auto_skin}（要 mid:broad:detail）`);
        } else {
          const [midGain, broadGain, detailGain] = nums;
          await setStrength(strengthRef.current, { midGain, broadGain, detailGain })
            .catch((e) => report(`M0_ERROR 带增益提交失败: ${e}`));
          await report(`M0_SKIN ${JSON.stringify({ midGain, broadGain, detailGain,
                                                   strength: strengthRef.current })}`);
          await sleep(600);        // 等引擎的 params_set 回显落进 stdout
        }
      }
      // 修容自动通道（$LRT_AUTO_LIGHT="fx:fy:r:sign,…"）：与自动消除笔同一条链。
      // 只有真窗口能证明 runLight → Rust light → 引擎 light_done 这条命令签名对得上：
      // Tauri 对不上名字时会静默丢参，屏上不动而一个错也不报。
      if (env.auto_light) {
        // 坐标必须落在**代理帧**坐标系里。这里踩过一个坑：外层还有个 `const [w, h] =
        // SIZES[sizeKey]`（合成跑靶档 1024×1280），它和引擎会话 672×848 不是一个系，
        // 拿它算笔印会编出 x=672 这种越界行程码、被引擎整条拒掉。消除笔那一臂一开始就用
        // image.w/h，修容这一臂必须跟着它，不能靠外层那个同名变量。
        if (!image) {
          await report("M0_ERROR LRT_AUTO_LIGHT 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const pw = image.w;
          const ph = image.h;
          const strokes = env.auto_light.split(",").map((s) => s.trim()).filter(Boolean);
          const waitLight = async (pred: (v: LightInfo) => boolean) => {
            // 轮询预算只给 12 s：命令被引擎整条拒绝时（越界 RLE、参数非法）这一层永远
            // 等不到，长时间空轮询会把 UI 线程冻住，把一次“脚本写错参数”变成
            // 一个看着像产品退化的 fps 数字（实测 45.5 fps / emit_to_pull.max 12.7 s）。
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.light && pred(st.light)) return st.light;
            }
            return null;
          };
          let lit: LightInfo | null = null;
          let bad = "";
          for (let i = 0; i < strokes.length; i++) {
            const [fx, fy, r, sign] = strokes[i].split(":").map(Number);
            if (![fx, fy, r, sign].every(Number.isFinite)) { bad = `第 ${i + 1} 条码无法解析`; break; }
            try {
              await runLight("add", { rle: clickRle(pw, ph, fx * pw, fy * ph, r), feather: 2, sign });
            } catch (e) { bad = String(e); break; }
            lit = await waitLight((v) => v.action === "add" && v.ops === i + 1);
            if (!lit) { bad = `第 ${i + 1} 笔 12s 内没等到 light_done（r=${r} 是像素半径，越界会被引擎拒绝）`; break; }
          }
          await report(`M0_LIGHT ${JSON.stringify(bad ? { bad, strokes: strokes.length } : {
            strokes: strokes.length, ops: lit?.ops ?? -1, lit: lit?.lit ?? null,
            exposure: lit?.exposure ?? null, radius: lit?.radius ?? null,
            fieldPeak: lit?.field_peak ?? null, lightMs: lit?.light_ms ?? null,
            bandsMs: lit?.bands_ms ?? null, bytesLight: lit?.bytes_light ?? null,
          })}`);
        }
      }
      // 形变自动通道（$LRT_AUTO_DEFORM="slim:eye:chin"）：与修容同一条理由，只有
      // 真窗口能证明 runDeform → Rust deform → 引擎 deform_done 这条签名对得上。
      if (env.auto_deform) {
        const nums = env.auto_deform.split(":").map((s) => Number(s.trim()));
        if (nums.length !== 3 || !nums.every(Number.isFinite)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_DEFORM=${env.auto_deform}（要 slim:eye:chin）`);
        } else {
          const amounts = { slim_face: nums[0], big_eye: nums[1], small_chin: nums[2] };
          const waitDeform = async () => {
            // 轮询预算 12 s：被引擎整条拒（没 precompute、synthetic 关键点）时
            // 这一层永远等不到，长时空轮询会冻住 UI 线程、污染 fps。
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.deform && st.deform.amounts.slim_face === amounts.slim_face) return st.deform;
            }
            return null;
          };
          let got: DeformInfo | null = null;
          try {
            await runDeform("set", amounts);
            got = await waitDeform();
          } catch (e) {
            await report(`M0_ERROR runDeform 失败: ${e}`);
          }
          await report(`M0_DEFORM ${JSON.stringify(got ? {
            amounts, lit: got.lit, built: got.built, backend: got.landmark_backend,
            deformMs: got.deform_ms, bytesDeform: got.bytes_deform, renderMs: got.render_ms,
            buildMs: got.build?.deform_build_ms ?? null,
            peaks: got.build ? Object.fromEntries(Object.entries(got.build.kinds).map(
              ([k, v]) => [k, v.peak_px])) : null,
            merged: got.build ? Object.fromEntries(Object.entries(got.build.kinds).map(
              ([k, v]) => [k, v.merged])) : null,
          } : { bad: "12s 内没等到 deform_done（没 precompute 或后端被拒）", amounts })}`);
        }
      }
      // 调色自动通道（$LRT_AUTO_LUT="amount@/tmp/x.cube"）：与形变同一条理由，只有
      // 真窗口能证明 runLut → Rust lut → 引擎 lut_done 这条命令签名对得上。
      // 只按**第一个** @ 切分：前半段是个数字，不可能含 @，而路径里什么都可能。
      if (env.auto_lut) {
        const at = env.auto_lut.indexOf("@");
        const amt = Number(at >= 0 ? env.auto_lut.slice(0, at) : "1");
        const src = (at >= 0 ? env.auto_lut.slice(at + 1) : env.auto_lut).trim();
        if (!Number.isFinite(amt) || !src) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_LUT=${env.auto_lut}（要 amount@<路径>）`);
        } else {
          const preset = src.startsWith("preset:") ? src.slice(7) : "";
          const opts = preset ? { preset, amount: amt } : { path: src, amount: amt };
          const waitLut = async () => {
            // 轮询预算 12 s：被引擎整条拒（文件不存在、表非法）时这一层永远等不到，
            // 长时空轮询会冻住 UI 线程、污染 fps。
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.lut && st.lut.action === "set" && st.lut.lut_amount === amt) return st.lut;
            }
            return null;
          };
          let got: LutInfo | null = null;
          try {
            await runLut("set", opts);
            got = await waitLut();
          } catch (e) {
            await report(`M0_ERROR runLut 失败: ${e}`);
          }
          await report(`M0_LUT ${JSON.stringify(got ? {
            source: got.lut_source, size: got.lut_size, amount: got.lut_amount,
            lit: got.lut_lit, neutral: got.lut_neutral, clipped: got.lut_clipped,
            notes: got.lut_notes, lutMs: got.lut_ms, mountMs: got.lut_mount_ms,
            bytesLut: got.bytes_lut, filterCached: got.filter_cached, bandsMs: got.bands_ms,
            renderMs: got.render_ms,
          } : { bad: "12s 内没等到 lut_done（文件不存在或表被引擎拒绝）", opts })}`);
        }
      }
      // 肤色定向自动通道（$LRT_AUTO_GRADE="dh:ds:dv:amount"）：与上面几条同一条理由——
      // 只有真窗口能证明 runGrade → Rust grade → 引擎 grade_done 这条命令签名对得上。
      if (env.auto_grade) {
        const parts = env.auto_grade.split(":").map((x) => Number(x));
        if (parts.length !== 4 || parts.some((x) => !Number.isFinite(x))) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_GRADE=${env.auto_grade}（要 dh:ds:dv:amount）`);
        } else {
          const [dh, ds, dv, amount] = parts;
          const waitGrade = async () => {
            // 与调色同一条 12 s 轮询预算：被引擎整条拒（越界、跑靶中）时永远等不到
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.grade && st.grade.action === "set" && st.grade.grade_dh === dh) return st.grade;
            }
            return null;
          };
          let got: GradeInfo | null = null;
          try {
            await runGrade("set", { dh, ds, dv, amount });
            got = await waitGrade();
          } catch (e) {
            await report(`M0_ERROR runGrade 失败: ${e}`);
          }
          await report(`M0_GRADE ${JSON.stringify(got ? {
            dh: got.grade_dh, ds: got.grade_ds, dv: got.grade_dv, amount: got.grade_amount,
            lit: got.grade_lit, gradeMs: got.grade_ms, lutMs: got.lut_ms,
            bytesGrade: got.bytes_grade, filterCached: got.filter_cached,
            // COLOR-004：作用域与区域格数也进这一行——真窗口那一臂要能看见“落笔之后
            // 引擎自己把 scope 切成了 brush”，而不是只看见画面动了。
            scope: got.grade_scope, scopes: got.grade_scopes, maskPx: got.mask_px,
            limits: got.grade_limits, renderMs: got.render_ms,
          } : { bad: "12s 内没等到 grade_done（参数越界或跑靶进行中）", dh, ds, dv, amount })}`);
        }
      }
      // 帧快照与字节差：底片条（M5-a）与撤销/重做（M5-b）两条自动通道共用。
      // 比的是"用户看见的那一帧"，不是引擎上报的那个数字。
      const peek = async () => {
        try {
          return parseFrameHead(await peekFrame());
        } catch (e) {
          await report(`M0_ERROR peekFrame 失败: ${e}`);
          return null;
        }
      };
      // 返回 -1 表示"两份快照不是一块画布"（尺寸不同）。这不等于"画面没变"：
      // 切到不同幅面那张时代理档就从 400×504 变成 552×368，画布都换了，
      // 拿字节数比是比不出东西的——上一版就是在这里把它判成"没变"，一条
      // 假红灯把 mixed 那一档整条带崩
      const diffBytes = (a: Uint8Array | null, b: Uint8Array | null) => {
        if (!a || !b) return -2;
        if (a.length !== b.length) return -1;
        let n = 0;
        for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) n++;
        return n;
      };
      // 换底自动通道（$LRT_AUTO_BG="rrggbb:tol:softness[:backend]"）。
      // 真窗口要证的不是合成本身（test_matting 已钉数值保真），而是三层签名对得上、
      // 且画面真的随之而动：runBackground → Rust background → 引擎 cmd_background →
      // bg_done → engine_status。Tauri 参数名错一个，命令会被静默丢掉（屏上不动而
      // 一个错也不报）——只有真窗口抓得到这一类。
      //
      // 三臂一次跑完，因为它们是同一个里程碑的三半边：
      //   set   → frameChanged > 0（合成写进了用户看见的那一帧）
      //   clear → frameChanged = 0（关掉整层要逐字节回出厂帧，"能开不能关"是缺陷）
      //   birefnet 无权重 → 引擎整条拒、画面不动、宿主还活着（静默降级是最坏答案）
      if (env.auto_background) {
        const parts = env.auto_background.split(":");
        const hex = (parts[0] || "").replace("#", "");
        const tol = Number(parts[1] ?? 0.12), soft = Number(parts[2] ?? 0.10);
        const backend = parts[3] || "color_key";
        if (hex.length !== 6 || !Number.isFinite(tol) || !Number.isFinite(soft)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_BG=${env.auto_background}（要 rrggbb:tol:softness[:backend]）`);
        } else {
          const bg = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
          // 角落像素直采：frameChanged > 0 只说"动了"，不说"动成了什么"。底色是纯色，
          // 左上角 8×8 均值就该是那个色（±1 量化）——这一条比字节差硬。
          // 字节序是 RGBA（取证：给纯红 ff0000 时 p[0]=255、p[2]=0，而画布用的 ImageData
          // 本就是 RGBA；当成 BGRA 读会得到反的三元组，上一轮 m6bg 真窗口就报过 [0,0,255]）。
          const cornerRgb = (p: Uint8Array | null, w: number) => {
            if (!p || w <= 0) return null;
            let b = 0, g = 0, r = 0, n = 0;
            for (let y = 0; y < 8; y++) {
              for (let x = 0; x < 8; x++) {
                const i = (y * w + x) * 4;
                if (i + 3 >= p.length) return null;
                r += p[i]; g += p[i + 1]; b += p[i + 2]; n++;
              }
            }
            return [Math.round(r / n), Math.round(g / n), Math.round(b / n)];
          };
          const before = await peek();
          const homePix = before?.pixels ?? null;
          // 轮询等一条 bg_done：等 action 而不是等"有 background"，clear 与 set 共用
          // 同一个槽位，不分辨就会把上一条的余温当成这一条的答复
          const waitBg = async (want: "set" | "clear", ms = 12000) => {
            for (let i = 0; i < ms / 100; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.background && st.background.action === want &&
                  (want !== "set" || st.background.bg_active)) return st.background;
            }
            return null;
          };
          let got: BackgroundInfo | null = null;
          try {
            await runBackground("set", { backend, bg, tol, softness: soft });
            got = await waitBg("set");
          } catch (e) {
            await report(`M0_ERROR runBackground 失败: ${e}`);
          }
          const after = await peek();
          const diff = diffBytes(homePix, after?.pixels ?? null);
          await report(`M0_BG ${JSON.stringify(got ? {
            active: got.bg_active, backend: got.backend, fill: got.matte_fill_fg,
            bytesBg: got.bytes_bg, bgMs: got.bg_ms, frameChanged: diff, device: got.device,
            wantBg: bg, cornerBefore: cornerRgb(homePix, before?.w ?? 0),
            cornerAfter: cornerRgb(after?.pixels ?? null, after?.w ?? 0),
          } : { bad: "12s 内没等到 bg_done", bg, tol, soft, backend, frameChanged: diff })}`);

          if (got) {
            // 关掉整层：这一臂的判据是"逐字节回到出厂帧"，不是"变了另一个样"
            let cleared: BackgroundInfo | null = null;
            try {
              await runBackground("clear");
              cleared = await waitBg("clear");
            } catch (e) {
              await report(`M0_ERROR runBackground(clear) 失败: ${e}`);
            }
            const back = await peek();
            await report(`M0_BG_CLEAR ${JSON.stringify(cleared ? {
              active: cleared.bg_active, bytesBg: cleared.bytes_bg,
              frameRestoredDiff: diffBytes(homePix, back?.pixels ?? null),
              cornerRestored: cornerRgb(back?.pixels ?? null, back?.w ?? 0),
              bgMs: cleared.bg_ms,
            } : { bad: "12s 内没等到 clear 的 bg_done" })}`);
          } else {
            // 主臂就没成，后面两臂没有判的余地——但 birefnet 那一臂仍然要试：
            // 它本来就不该成，主臂塌了它该照塌（引擎没被主臂的失败搞死）
            await report("M0_BG_SKIP 主臂未就绪，跳过 clear 臂");
          }

          // birefnet 无权重臂：色键臂能成就说明引擎活着，这一臂要的正是"整条拒 +
          // 画面一个字不动 + 引擎还能应答"。拒的话 bg_done 永不到，这里不等它，
          // 等的是宿主轮询还能拿到状态 + 日志里那条诚实的拒绝。
          if (backend !== "birefnet") {
            const pixBeforeReject = (await peek())?.pixels ?? null;
            let rejectNote = "";
            try {
              await runBackground("set", { backend: "birefnet", bg, tol, softness: soft });
              for (let i = 0; i < 60 && !rejectNote; i++) {
                await sleep(100);
                const st = await engineStatus().catch(() => null);
                const hit = (st?.logs ?? []).find((l) => /birefnet|BiRefNet|权重/.test(l));
                if (hit) rejectNote = hit.slice(0, 220);
              }
            } catch (e) {
              rejectNote = `invoke 抛错: ${e}`;
            }
            const stAfter = await engineStatus().catch(() => null);
            const pixAfterReject = (await peek())?.pixels ?? null;
            await report(`M0_BG_REJECT ${JSON.stringify({
              sawError: !!rejectNote, note: rejectNote,
              frameMoved: diffBytes(pixBeforeReject, pixAfterReject),
              engineAlive: !!stAfter?.engine_alive,
              bgStillActive: stAfter?.background?.bg_active ?? null,
            })}`);

            // 换图即清臂（M8 补的缺陷）：引擎在 cmd_load_image 里把 _bg 整层清回
            // 出厂态（_fresh_doc_state），宿主那一侧的 background 槽位若不跟着清，
            // 就会报“换底还开着”而屏幕上根本没有——同一行还驱动着“关掉换底”按钮的
            // 灰与不灰、常驻 MiB 的读数。裸引擎的协议用例碰不到宿主这一侧，只有真窗
            // 口拿得到这一条。
            if (env.load_image) {
              const pixBeforeReload = (await peek())?.pixels ?? null;
              try {
                await loadImage(env.load_image, { maxPx: env.max_px ?? undefined, strength: 0 });
              } catch (e) {
                await report(`M0_ERROR loadImage（重导）失败: ${e}`);
              }
              let rst: EngineStatus | null = null;
              for (let i = 0; i < 300; i++) {
                await sleep(100);
                rst = await engineStatus().catch(() => null);
                if (rst?.image) break;
              }
              const rl = await peek();
              await report(`M0_BG_RELOAD ${JSON.stringify({
                hostBgCleared: rst?.background == null,
                engineBgActive: rst?.background?.bg_active ?? null,
                // 重导同一张图（同一 maxPx）逐字节等于出厂帧：解码确定、代理档同幅。
                // 不为 0 就是“旧图层没清干净”或“代理档跳了”，两者都不是换底该有的行为。
                frameIsHome: diffBytes(homePix, rl?.pixels ?? null),
                frameMovedVsBefore: diffBytes(pixBeforeReload, rl?.pixels ?? null),
                corner: cornerRgb(rl?.pixels ?? null, rl?.w ?? 0),
                proxy: rst?.image ? `${rst.image.w}x${rst.image.h}` : "-",
                proxySame: !!rst?.image && !!before && `${rst.image.w}x${rst.image.h}` === `${before.w}x${before.h}`,
              })}`);
              // 后面的臂跟着新的代理档走（旧 w/h 驱一个刚重建的会话只会量到陈尺寸）
              if (rst?.image) image = rst.image;
            } else {
              // 不能默默当这一臂过了：没得验就报没得验
              await report("M0_BG_SKIP 无 LRT_LOAD_IMAGE，跳过换图即清臂");
            }

            // 重挂臂：把底色再开回去，并且**开着进接下来的跑靶**。两个理由：
            //   • 换底不是一次性动作——同一会话里第二次 set 也得成（第一次把状态
            //     写坏、第二次静默不动是这类分层最容易犯的错）；
            //   • 后面的 bench 就在"链尾挂着一层常驻合成"的真实状态下量帧通路，
            //     而不是把层关掉再测一个好看的数。
            // M8 起这一臂还多一层意思：它跑在**重导之后**，所以量的是“会话重建后
            // 再开一次”而不只是“同一会话里连着按”。
            await runBackground("set", { backend, bg, tol, softness: soft });
            const again = await waitBg("set");
            const re = await peek();
            await report(`M0_BG_REAPPLY ${JSON.stringify(again ? {
              active: again.bg_active, backend: again.backend, bytesBg: again.bytes_bg,
              corner: cornerRgb(re?.pixels ?? null, re?.w ?? 0),
              frameChangedVsHome: diffBytes(homePix, re?.pixels ?? null),
            } : { bad: "第二次 set 没等到 bg_done" })}`);
          }
        }
      }
      // 局部调色（COLOR-004）自动通道（$LRT_AUTO_LOCAL_COLOR="fx:fy:r:dh:ds:dv"）。
      // 真窗口这一臂要同时证三件事：runGrade 的 mask/set 两个新 action 在 Tauri 签名上
      // 递得到（错一个名字会被静默丢掉，屏不动而一个错也不报）；引擎落笔就把作用域切成
      // brush；而**区域外那一圈逐字节没动**。最后一条只能拿用户看见的那一帧量——屏上
      // 没有第二块画布可比，而“局部调色静默变成全图调色”恰恰是画面在变、人分不出来的那种错。
      if (env.auto_local_color) {
        const nums = env.auto_local_color.split(":").map(Number);
        if (nums.length !== 6 || !nums.every(Number.isFinite)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_LOCAL_COLOR=${env.auto_local_color}（要 fx:fy:r:dh:ds:dv）`);
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_LOCAL_COLOR 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const [fx, fy, r, dh, ds, dv] = nums;
          const pw = image.w;
          const ph = image.h;
          const waitGrade = async (pred: (v: GradeInfo) => boolean) => {
            // 轮询预算 12 s：与修容那臂同一条理由——被拒时长时间空轮询会冻住 UI 线程，
            // 把“脚本写错参数”变成一个看着像产品退化的 fps 数字
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.grade && pred(st.grade)) return st.grade;
            }
            return null;
          };
          const before = await peek();
          let bad = "";
          let lit: GradeInfo | null = null;
          try {
            await runGrade("mask", { rle: clickRle(pw, ph, fx * pw, fy * ph, r),
                                     feather: 2, mode: "replace" });
            lit = await waitGrade((v) => v.grade_scope === "brush" && v.mask_px > 0);
            if (!lit) bad = "落笔后 12s 内没等到作用域为 brush 的 grade_done";
            if (!bad) {
              await runGrade("set", { dh, ds, dv, amount: 1 });
              lit = await waitGrade((v) => v.grade_lit === true) ?? lit;
            }
          } catch (e) { bad = String(e); }
          const after = await peek();
          // 两份快照得是同一块完整画布才能逐格比：脏矩形只送顶部几行，拿它比字节
          // 比出来的是“没送到”而不是“没变”（上一轮切文档那一臂就报过 -1）
          const full = (f: typeof before) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          let insideChanged = -1;
          let outsideChanged = -1;
          if (!bad && before && after && full(before) && full(after)
            && before.w === after.w && before.h === after.h) {
            const cx = Math.round(fx * after.w);
            const cy = Math.round(fy * after.h);
            const band = Math.round(r) + 6;   // 笔迹半径 + 羽化支撑 + 插值余量
            insideChanged = 0; outsideChanged = 0;
            for (let y = 0; y < after.h; y++) {
              for (let x = 0; x < after.w; x++) {
                const i = (y * after.w + x) * 4;
                if (after.pixels[i] === before.pixels[i]
                  && after.pixels[i + 1] === before.pixels[i + 1]
                  && after.pixels[i + 2] === before.pixels[i + 2]) continue;
                if (Math.abs(x - cx) <= band && Math.abs(y - cy) <= band) insideChanged++;
                else outsideChanged++;
              }
            }
          } else if (!bad) {
            bad = "两份快照不是同一块完整画布（脏矩形或尺寸变了），区域外逐字节那条没法量";
          }
          await report(`M0_LOCAL_COLOR ${JSON.stringify(bad ? { bad, maskPx: lit?.mask_px ?? 0 } : {
            scope: lit?.grade_scope ?? "", scopes: lit?.grade_scopes ?? [],
            maskPx: lit?.mask_px ?? 0, lit: lit?.grade_lit ?? null,
            bytesGrade: lit?.bytes_grade ?? 0, gradeMs: lit?.grade_ms ?? 0,
            canvas: `${after?.w ?? 0}x${after?.h ?? 0}`,
            insideChanged, outsideChanged,
          })}`);
        }
      }
      // 眼牙增强（LNX-PORTRAIT-009）自动通道（$LRT_AUTO_ENHANCE="sclera:iris:teeth"）。
      // 真窗口这一臂证四件事，缺一条就不叫"开箱即用"：①runEnhance → Rust enhance →
      // 引擎 enhance_done 四层签名对得上（错一个字段名会被静默丢掉，屏不动而一个错也不报，
      // 第 7 臂 auto_pick 那一记就是这么漏的）；②点火后画面按掩膜动（insideChanged>0，
      // 不是假滑块）；③**窗口外那一圈逐字节没动**（outsideChanged=0——"局部增强悄悄变成
      // 全图提亮"正是画面在变而人分不出来的那种错）；④clear 之后回到 before 逐字节
      // （backHomeBytes=0，且引擎报 bytes_enhance=0：常驻场真的放掉了，不是留着没人看）。
      if (env.auto_enhance) {
        const nums = env.auto_enhance.split(":").map(Number);
        if (nums.length !== 3 || !nums.every((n) => Number.isFinite(n) && n >= 0 && n <= 1)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_ENHANCE=${env.auto_enhance}`
            + "（要 sclera:iris:teeth，每个 [0,1]）");
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_ENHANCE 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const [sclera, iris, teeth] = nums;
          const waitEnh = async (pred: (v: EnhanceInfo) => boolean) => {
            // 12 s 预算与局部调色那臂同一条理由：被拒时长空轮询会冻住 UI 线程，
            // 把"脚本少传一个参数"变成一个看着像产品退化的 fps 数字
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.enhance && pred(st.enhance)) return st.enhance;
            }
            return null;
          };
          const before = await peek();
          const homePix = before?.pixels ?? null;
          let bad = "";
          let lit: EnhanceInfo | null = null;
          try {
            await runEnhance("set", { sclera, iris, teeth });
            lit = await waitEnh((v) => v.lit === true);
            if (!lit) bad = "点火后 12s 内没等到 lit=true 的 enhance_done";
            else {
              // 命中事件那一格可能正好在两次渲染之间（`enhance_ms` 量的是"最近一次渲染里
              // 这一层的耗时"，读到 0 不等于"不要钱"，等于没量到）。等一小段再取一次，
              // 拿到的才是用户在拖滑块时真付的那一份代价。
              await sleep(250);
              const st2 = await engineStatus().catch(() => null);
              if (st2?.enhance?.lit === true) lit = st2.enhance;
            }
          } catch (e) { bad = String(e); }
          const after = await peek();
          // 两份快照得是同一块完整画布才能逐格比：脏矩形只送顶部几行
          const full = (f: typeof before) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          let insideChanged = -1;
          let outsideChanged = -1;
          if (!bad && before && after && full(before) && full(after)
            && before.w === after.w && before.h === after.h) {
            // 窗口取引擎报的那一片画布坐标 (y0,x0,fh,fw)，不是脚本自己按脸盒估的框：
            // "这一层只在自己那只窗口里逐点乘加"这条承诺的实现就是这个数
            const win = lit?.enhance_window ?? null;
            if (!win) {
              bad = "enhance_window 为 null：场没挂上，窗口内外两条没法量";
            } else {
              const wy = Math.round(win[0]), wx = Math.round(win[1]);
              const wh = Math.round(win[2]), ww = Math.round(win[3]);
              insideChanged = 0; outsideChanged = 0;
              for (let y = 0; y < after.h; y++) {
                for (let x = 0; x < after.w; x++) {
                  const i = (y * after.w + x) * 4;
                  if (after.pixels[i] === before.pixels[i]
                    && after.pixels[i + 1] === before.pixels[i + 1]
                    && after.pixels[i + 2] === before.pixels[i + 2]) continue;
                  if (y >= wy && y < wy + wh && x >= wx && x < wx + ww) insideChanged++;
                  else outsideChanged++;
                }
              }
            }
          } else if (!bad) {
            bad = "两份快照不是同一块完整画布（脏矩形或尺寸变了），窗口外逐字节那条没法量";
          }
          // 关掉那层：回到 before 逐字节。这一条只在①②③都量完之后才跑，因为它会把
          // 场放掉——先取完账再放，反过来就只能拿到一份空账
          let backHomeBytes = -2;
          if (!bad) {
            try {
              await runEnhance("clear");
              const off = await waitEnh((v) => v.lit === false && v.bytes_enhance === 0);
              if (!off) {
                bad = "clear 后 12s 内没等到「enhance_lit=false 且 bytes_enhance=0」那一格";
              } else {
                const home2 = await peek();
                backHomeBytes = (home2 && full(home2) && home2.w === before!.w && home2.h === before!.h)
                  ? diffBytes(homePix, home2.pixels) : -1;
              }
            } catch (e) { bad = `clear 那一臂炸了：${e}`; }
          }
          await report(`M0_ENHANCE ${JSON.stringify(bad ? {
            bad, gatedPx: lit?.gated_px ?? {}, window: lit?.enhance_window ?? null,
          } : {
            amounts: lit?.amounts ?? {}, lit: lit?.lit ?? null,
            gatedPx: lit?.gated_px ?? {}, geomPx: lit?.enhance_geom_px ?? {},
            reason: lit?.enhance_reason ?? {}, window: lit?.enhance_window ?? [],
            device: lit?.device ?? "", bytesEnhance: lit?.bytes_enhance ?? 0,
            enhanceMs: lit?.enhance_ms ?? 0, buildMs: lit?.enhance_build_ms ?? 0,
            mouthOpenness: (lit?.enhance_mouth ?? {}).openness ?? null,
            canvas: `${after?.w ?? 0}x${after?.h ?? 0}`,
            insideChanged, outsideChanged, backHomeBytes,
          })}`);
        }
      }
      // 人工纠正优先（LNX-PORTRAIT-006）自动通道（$LRT_AUTO_MANUAL=<要关掉的 index>）。
      // 库里那 20 条与端到端那两条连的是裸引擎；这一臂证的是同一份账走完
      // 视口 → Rust `face` → 引擎 → 宿主 `status.face` 这四层之后**仍是那一条账**，
      // 并且"关掉的那一位在重检测后的那一帧上不得重新出现"能在用户看见的那一帧上量出来
      // ——屏幕上没有第二块画布可比，这一条只能真窗口量。
      if (env.auto_manual) {
        const want = Number(env.auto_manual);
        if (!Number.isInteger(want) || want < 0) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_MANUAL=${env.auto_manual}（要一个非负整数 index）`);
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_MANUAL 需要 LRT_LOAD_IMAGE + LRT_PRECOMPUTE"
            + "（多人夹具：名单只能来自真实分析）");
        } else {
          const pw = image.w;
          const ph = image.h;
          const full = (f: any) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          const waitFace = async (pred: (v: NonNullable<ReturnType<typeof faceStateOf>>) => boolean) => {
            // 12 s 预算与眼牙那一臂同一条理由：长空轮询会冻住 UI 线程，把"脚本少传一个
            // 参数"变成一个看着像产品退化的 fps 数字
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              const v = faceStateOf(st, st?.doc_report?.doc_state ?? null);
              if (v && pred(v)) return v;
            }
            return null;
          };
          /** 那一圈脸盒内芯（缩 25%）里有多少格被改动：逐字节判据的计数方式与端到端同源 */
          const changedIn = (a: Uint8Array | null, b: Uint8Array | null, box: number[] | null) => {
            if (!a || !b || !box || a.length !== b.length) return -1;
            const [x0, y0, x1, y1] = box;
            const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
            const hx = (x1 - x0) / 2 * 0.75, hy = (y1 - y0) / 2 * 0.75;
            let n = 0;
            for (let y = 0; y < ph; y++) {
              for (let x = 0; x < pw; x++) {
                if (Math.abs(x / pw - cx) > hx || Math.abs(y / ph - cy) > hy) continue;
                const i = (y * pw + x) * 4;
                if (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2]) n++;
              }
            }
            return n;
          };
          let bad = "";
          let f1: ReturnType<typeof faceStateOf> = null;
          let f2: ReturnType<typeof faceStateOf> = null;
          let f3: ReturnType<typeof faceStateOf> = null;
          let roster0 = 0, other = -1, dfLit: boolean | null = null;
          let keptCore = -1, redetectCore = -1, errRefused = "";
          let rectTakenByEngine = false, rectErrText = "";
          try {
            const st0 = await engineStatus().catch(() => null);
            const f0 = faceStateOf(st0, st0?.doc_report?.doc_state ?? null);
            roster0 = f0?.faces.length ?? 0;
            other = f0?.faces.find((x) => x.index !== want)?.index ?? -1;
            if (!f0 || roster0 <= want || other < 0) {
              bad = `名单里只有 ${roster0} 个人：这一臂要的是多人夹具（要能关掉一位、留下另一位）`;
            }
            if (!bad) {
              await runFace("select", other);
              if (!(await waitFace((v) => v.explicit === true && v.index === other))) {
                bad = `选定人物 ${other} 之后 12s 内没等到 explicit 的 face 状态`;
              }
            }
            if (!bad) {
              await runDeform("set", { slim_face: 0.6 });
              for (let i = 0; i < 90; i++) {
                await sleep(100);
                const st = await engineStatus().catch(() => null);
                if (st?.deform?.lit === true) { dfLit = true; break; }
                dfLit = st?.deform?.lit ?? null;
              }
              if (!dfLit) bad = "推了留下那一位的形变而 9s 内没等到 lit=true";
            }
            if (!bad) {
              const errBefore = (await engineStatus().catch(() => null))?.last_error ?? "";
              const before = await peek();
              await runFace("disable", want);
              f1 = await waitFace((v) => (v.manual?.disabled?.length ?? 0) >= 1);
              if (!f1) bad = "关掉那一只之后 12s 内没等到带人工禁用账的 face 状态";
              else {
                const flags = f1.faces.filter((x) => x.index === want).map((x) => !!x.disabled);
                if (!flags.length || !flags[0]) bad = `被关那一只没标 disabled：${JSON.stringify(f1.faces)}`;
                if (f1.enabled?.includes(want)) bad = "被关那一只仍出现在可编辑名单里";
                // 人工账不许把"这一轮分析是多人图"这个原始事实抹掉（SCOPE-001 的 P0 判据读它）
                if (f1.scope_block !== "multi_face") bad = `禁用抹掉了多人事实：${f1.scope_block}`;
                const after = await peek();
                if (before && after && full(before) && full(after)) {
                  const box = f1.faces.find((x) => x.index === want)?.box ?? null;
                  keptCore = changedIn(before.pixels, after.pixels, box);
                  if (keptCore !== 0) bad = `关掉那一只改动了画面（${keptCore} 格）：选人与账不该动像素`;
                } else bad = "关掉前后不是同一块完整画布，逐格判据没法量";
              }
              // 明拒那一条：被禁的那一只不许再被选定，而拒绝必须走得到宿主（error 事件）
              await runFace("select", want);
              for (let i = 0; i < 40 && !errRefused; i++) {
                await sleep(100);
                const st = await engineStatus().catch(() => null);
                const e = st?.last_error ?? "";
                if (e && e !== errBefore && e.includes("已被人工禁用")) errRefused = e;
              }
              if (!errRefused) bad = bad || "选定被禁那一只没等到『已被人工禁用』的拒绝到达宿主";
              // 后台重检测：账要在、画面里那一圈不许出现他的东西
              const preRedetect = await peek();
              await runPrecompute({ backend: "mediapipe" });
              f2 = await waitFace((v) => (v.manual?.disabled?.length ?? 0) >= 1
                && v.faces.some((x) => x.index === want && x.disabled));
              if (!f2) bad = bad || "重检测后没等到「那一只仍是关着的」那份状态：静默恢复";
              const postRedetect = await peek();
              if (f2 && preRedetect && postRedetect && full(preRedetect) && full(postRedetect)) {
                const box = f2.faces.find((x) => x.index === want)?.box ?? null;
                redetectCore = changedIn(preRedetect.pixels, postRedetect.pixels, box);
                if (redetectCore !== 0) {
                  bad = `重检测后被禁那一只的内芯动了 ${redetectCore} 格：那层的几何悄悄活了回来`;
                }
              } else if (f2) bad = bad || "重检测前后不是同一块完整画布：逐格判据落不了地";
              // 恢复：账清空才算"人工判断可以被人推翻"
              await runFace("enable", want);
              f3 = await waitFace((v) => (v.manual?.disabled?.length ?? 0) === 0);
              if (!f3) bad = bad || "恢复那一只之后 12s 内账没清空";
              // rect 这一格必须在装机壳里也走得通：视口 → Rust `face`(rect) → 引擎。上一轮
              // auto_pick 就是漏在桥那一格（TS 发了，Rust 的签名里没这一项，引擎收到的永远是
              // 空的）。判据用**两条拒绝文案的差别**，不必再造一张漏检夹具：rect 被桥丢了，引擎
              // 说的是「face add 要给归一化矩形」；rect 到了而框里已有人，说的是「这一框里已经
              // 有脸了」。差一句话，正好把丢参数这件事量出来。
              const errBeforeAdd = (await engineStatus().catch(() => null))?.last_error ?? "";
              const boxProbe = f3?.faces.find((x) => x.index === other)?.box ?? null;
              if (!boxProbe) {
                bad = bad || "补框那一臂没拿到可发的 rect（名单里没有留下那一位的脸盒）";
              } else {
                await runFace("add", undefined, boxProbe);
                for (let i = 0; i < 40 && !rectTakenByEngine; i++) {
                  await sleep(100);
                  const e = (await engineStatus().catch(() => null))?.last_error ?? "";
                  if (e && e !== errBeforeAdd) {
                    rectErrText = e.slice(0, 140);
                    rectTakenByEngine = e.includes("已经有脸了");
                  }
                }
                if (!rectTakenByEngine) {
                  bad = bad || `face add 的 rect 没走到引擎（宿主收到的是「${rectErrText}」）`;
                }
              }
            }
          } catch (e) { bad = `臂内异常：${e}`; }
          await report(`M0_MANUAL ${JSON.stringify(bad ? {
            bad, roster: roster0, keptCore, redetectCore, errRefused: !!errRefused,
            rectReachedEngine: rectTakenByEngine, rectErr: rectErrText,
            disabledLedger: f1?.manual?.disabled?.length ?? -1,
          } : {
            roster: roster0, kept: other, refused: want,
            disabledLedger: f3?.manual?.disabled?.length ?? -1,
            enabledAfterEnable: f3?.enabled?.length ?? -1,
            scopeBlock: f1?.scope_block ?? null, preview: f1?.manual?.preview ?? "",
            keptCore, redetectCore, refusedReachedHost: !!errRefused,
            rectReachedEngine: rectTakenByEngine, rectErr: rectErrText,
            deformLit: dfLit, canvas: `${pw}x${ph}`,
          })}`);
        }
      }
      // 1.12 规格工作台（$LRT_AUTO_SPEC=<JSON>）：用户那四条验收动作一次跑完。
      // 这一臂量的是**宿主桥 + 引擎 + 屏幕**三层同时成立：runExposure/runHsl/
      // setStrength/runDeform/runCrop 走的就是面板滑块那条链（中间隔着 Rust 的
      // 命令签名，Tauri 对不上名字时静默丢参），而 100% 视口与裁剪后的画面尺寸
      // 只能拿用户看见的那一帧算。报告里的 toneDiff 是“命令全对而画面没动”的
      // 照妖镜：像素差为 0 就说明这一轮白跑。
      if (env.auto_spec) {
        type SpecTour = {
          exposure?: { ev?: number; temperature_shift?: number; tint_shift?: number;
                       contrast?: number; highlights?: number; shadows?: number;
                       saturation?: number };
          hsl?: { band: number; dh?: number; ds?: number; dl?: number };
          skin?: number;
          deform?: Record<string, number>;
          crop?: { rect: number[]; rotation?: number };
          view?: "100" | "fit";
        };
        let tour: SpecTour | null = null;
        try {
          tour = JSON.parse(env.auto_spec) as SpecTour;
        } catch (e) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_SPEC=${env.auto_spec}（要 JSON）：${e}`);
        }
        if (tour) {
          const bads: string[] = [];
          const got: Record<string, unknown> = {};
          // 文档状态的“最新一份”只随 image_ready / session_state / history_state
          // 到达。命令本身带的新状态盖不到 status 槽位，所以核对前先问一次
          // history state（只读命令，不进撤销栈），再按 source 认这一条答复。
          const refreshDoc = async (): Promise<DocState | null> => {
            // 宿主的 doc_report 会一直留着上一条 history_state；只认 source 的话
            // 第二次刷新会当场读到**上一笔**的 doc_state（4K 上裁剪那一臂撞过：
            // 历史已经 5 步，crop 还是恒等）。doc_rev 是宿主每收一条状态就加的
            // 序号，必须等它真的往前走。
            const before = (await engineStatus().catch(() => null))?.doc_rev ?? 0;
            try { await runHistory("state"); }
            catch (e) { bads.push(`history state 失败：${e}`); return null; }
            for (let i = 0; i < 60; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if ((st?.doc_rev ?? 0) > before
                  && st?.doc_report?.source === "history_state") {
                return st.doc_report.doc_state;
              }
            }
            return null;
          };
          const home = await peek();
          const homePix = home?.pixels ?? null;
          if (!image) bads.push("LRT_AUTO_SPEC 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
          const wantExp = tour.exposure;
          if (wantExp) {
            try { await runExposure("set", wantExp); }
            catch (e) { bads.push(`exposure 命令失败：${e}`); }
          }
          if (tour.hsl) {
            const { band, ...v } = tour.hsl;
            try { await runHsl("set", band, v); }
            catch (e) { bads.push(`hsl 命令失败：${e}`); }
          }
          if (tour.skin !== undefined) {
            try { await setStrength(tour.skin); }
            catch (e) { bads.push(`set_strength 失败：${e}`); }
          }
          if (tour.deform) {
            try { await runDeform("set", tour.deform); }
            catch (e) { bads.push(`deform 命令失败：${e}`); }
          }
          const d1 = await refreshDoc();
          if (!d1) bads.push("刷新文档状态失败（history_state 没回来）");
          if (d1 && wantExp) {
            const bad = Object.entries(wantExp).filter(([k, v]) =>
              Math.abs(Number((d1.exposure as unknown as Record<string, number>)[k])
                - Number(v)) > 1e-9).map(([k]) => k);
            if (bad.length) bads.push(`曝光/影调这几位没到引擎：${bad.join(",")}`);
            got.exposure = d1.exposure;
          }
          if (d1 && tour.hsl) {
            const { band } = tour.hsl;
            const b = d1.hsl?.bands ?? [];
            const v = tour.hsl;
            const okHsl = (v.dh === undefined || Math.abs(b[band * 3] - v.dh) < 1e-9)
              && (v.ds === undefined || Math.abs(b[band * 3 + 1] - v.ds) < 1e-9)
              && (v.dl === undefined || Math.abs(b[band * 3 + 2] - v.dl) < 1e-9);
            if (!okHsl) bads.push(`八色 HSL 第 ${band + 1} 段没到引擎：${JSON.stringify(b.slice(band * 3, band * 3 + 3))}`);
            got.hsl = { band, bands: b, lit: d1.hsl?.lit ?? null };
          }
          if (d1 && tour.skin !== undefined) {
            if (Math.abs(d1.strength - tour.skin) > 1e-9) {
              bads.push(`磨皮强度没到引擎：${d1.strength} != ${tour.skin}`);
            }
            got.skin = d1.strength;
          }
          if (d1 && tour.deform) {
            const bad = Object.entries(tour.deform).filter(([k, v]) =>
              Math.abs((d1.deform.amounts[k] ?? 0) - Number(v)) > 1e-9).map(([k]) => k);
            if (bad.length) bads.push(`形变这几位没到引擎：${bad.join(",")}（没预计算？）`);
            got.deform = d1.deform.amounts;
          }
          // 像素差：上面四层若真上屏，画面必须与导入时不同（裁剪之前量）
          const tone = await peek();
          let frameNow = tone;          // 视口 100% 要按**当前**帧宽算（裁剪后幅面变了）
          const toneDiff = diffBytes(homePix, tone?.pixels ?? null);
          got.toneDiff = toneDiff;
          got.canvasBefore = home ? `${home.w}x${home.h}` : "";
          got.canvasTone = tone ? `${tone.w}x${tone.h}` : "";
          if (homePix && tone?.pixels && toneDiff === 0) {
            bads.push("曝光/HSL/磨皮/瘦脸全报成功，但画面逐字节没变");
          }
          // 裁剪 + 旋转（cmd_crop）：状态必须原样落到引擎
          if (tour.crop) {
            const errPre = (await engineStatus().catch(() => null))?.last_error ?? "";
            try { await runCrop("set", tour.crop.rect, tour.crop.rotation ?? 0); }
            catch (e) { bads.push(`crop 命令失败：${e}`); }
            // 命令回执只说明“发出去了”。引擎整条拒（跑靶互斥、量程、渲染失败）
            // 会写 last_error 而不抛异常——把那一句原样带进报告，别让失败只剩
            // “crop 还是恒等”这种二手读数。
            const errPost = (await engineStatus().catch(() => null))?.last_error ?? "";
            if (errPost && errPost !== errPre) got.cropErr = errPost;
            const d2 = await refreshDoc();
            if (d2) {
              const bad = (d2.crop.rect ?? []).some((r, i) =>
                Math.abs(r - tour.crop!.rect[i]) > 1e-6);
              if (bad || Math.abs((d2.crop.rotation_degrees ?? 0)
                - (tour.crop.rotation ?? 0)) > 1e-6) {
                bads.push(`裁剪/旋转没到引擎：${JSON.stringify(d2.crop.rect)}@${d2.crop.rotation_degrees}`
                  + (got.cropErr ? `（引擎：${String(got.cropErr).slice(0, 160)}）` : "（引擎没报错）"));
              }
              got.crop = { rect: d2.crop.rect, rot: d2.crop.rotation_degrees,
                           out: d2.crop.crop_out ?? null, outFull: d2.crop.out_full ?? null };
            }
            await sleep(400);
            const cropped = await peek();
            frameNow = cropped;
            got.canvasCrop = cropped ? `${cropped.w}x${cropped.h}` : "";
          }
          // 100% 视口：视口把 fitScale 画在自己的 DOM 上（data-fit-scale），
          // 探针按它反推真 1:1，而不是等一个 React state（这个 effect 的闭包是
          // 首帧那份，读到的 fitScale 永远是 1）。
          if (tour.view === "100" && image) {
            const clip = document.querySelector<HTMLElement>(".mirrorClip");
            const fit = Number(clip?.getAttribute("data-fit-scale") ?? 0);
            const fw = Number((clip?.getAttribute("data-frame") ?? "").split("x")[0]
              || frameNow?.w || image.w);
            const dpr = window.devicePixelRatio || 1;
            if (!(fit > 0) || !(fw > 0)) bads.push("视口没报 fitScale/frame：算不出 100%");
            else { setOneToOne(true);
                   setView({ zoom: 1 / Math.max(1e-6, dpr * fit), x: 0, y: 0, fit: false }); }
            await sleep(600);
            got.zoom = (document.querySelector(".zoomRead")?.textContent ?? "").trim();
            got.fitScale = +fit.toFixed(4);
            got.frameW = fw;
            if (!/^10[0-2]%$/.test(String(got.zoom))) {
              bads.push(`100% 视口没落到读数上：${String(got.zoom)}`);
            }
          }
          // 画质：任何画布/图片都不许挂 pixelated（马赛克那条的现场证据）
          got.pixelated = Array.from(document.querySelectorAll<HTMLElement>("canvas,img"))
            .filter((el) => getComputedStyle(el).imageRendering === "pixelated").length;
          if (got.pixelated) bads.push(`有 ${got.pixelated} 个画布在 pixelated 重采样`);
          // 面板事实：39 族 / 805 项 / 八色 chips / 真滑块数
          got.families = document.querySelectorAll("[data-spec-family]").length;
          got.specControls = Number(document.querySelector("[data-spec-controls]")
            ?.getAttribute("data-spec-controls") ?? 0);
          got.hslChips = document.querySelectorAll(".hslChips .hslChip").length;
          got.sliders = document.querySelectorAll("aside .pslider input[type=range]").length;
          await report(`M0_SPEC ${JSON.stringify({ bads, ...got })}`);
        }
      }
      // 分人编辑（LNX-PORTRAIT-003）自动通道（$LRT_AUTO_FACE=<要选的 index>）。
      // 库里那九段判据连的是裸引擎，中间隔着 Rust 的 face 命令与宿主的状态搬运——那两层
      // 只有真窗口能证明。这一臂量四件事：①未选定就推形变，引擎整条拒（SCOPE-001）而画面
      // 一格没动（不许留半截状态）；②runFace → face_selected → status.face 落回宿主；
      // ③选定本身不改画面（选人不等于调图）；④推完形变之后**没被选中的那一圈逐字节没动**。
      // 第④条只能拿用户看见的那一帧量：屏幕上没有第二块画布可比。
      if (env.auto_face) {
        const want = Number(env.auto_face);
        if (!Number.isInteger(want) || want < 0) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_FACE=${env.auto_face}（要一个非负整数 index）`);
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_FACE 需要 LRT_LOAD_IMAGE + LRT_PRECOMPUTE"
            + "（多人夹具：先解图再分析，名单只能来自真实分析）");
        } else {
          const pw = image.w;
          const ph = image.h;
          const full = (f: any) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          let bad = "";
          let numFaces = 0;
          let blockedBefore: boolean | null = null;
          let pickSource = "";
          let changedBySelect = -1;
          let insideChanged = -1;
          let outsideChanged = -1;
          let df: DeformInfo | null = null;
          const st0 = await engineStatus().catch(() => null);
          const f0 = faceStateOf(st0, st0?.doc_report?.doc_state ?? null);
          numFaces = f0?.faces.length ?? 0;
          blockedBefore = f0?.blocked ?? null;
          const errBefore = st0?.last_error ?? "";
          const base = await peek();
          // ① 未选定就推形变：期待一条引擎的拒绝，而画面一格不许动
          try {
            await runDeform("set", { slim_face: 0.6, big_eye: 0.3, small_chin: 0 });
          } catch (e) { bad = `runDeform 抛错（未选定那一臂）: ${e}`; }
          let errAfter = "";
          for (let i = 0; i < 120 && !bad; i++) {
            await sleep(100);
            const st = await engineStatus().catch(() => null);
            const e = st?.last_error ?? "";
            if (e && e !== errBefore) { errAfter = e; break; }
          }
          if (!bad && !errAfter) bad = "12s 内没等到引擎拒绝未选定时的形变（SCOPE-001 那条没落）";
          if (!bad && !errAfter.includes("face select")) {
            bad = `拒绝没给出路（文案里该有 face select）：${errAfter.slice(0, 120)}`;
          }
          const afterReject = await peek();
          const rejectDiff = (base && afterReject && full(base) && full(afterReject)
            && base.w === afterReject.w && base.h === afterReject.h)
            ? diffBytes(base.pixels, afterReject.pixels) : -1;
          if (!bad && rejectDiff !== 0) {
            bad = `被拒之后画面还动了 ${rejectDiff} 字节（或快照不可比）：拒绝不许留半截状态`;
          }
          // ② 用户点选那一张：答复要落进宿主那一个槽位
          if (!bad) {
            try {
              await runFace("select", want);
            } catch (e) { bad = `runFace 抛错: ${e}`; }
            for (let i = 0; i < 200 && !bad; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.face?.source === "face_selected" && st.face.face.explicit
                && st.face.face.index === want) { pickSource = st.face.source; break; }
            }
            if (!bad && !pickSource) bad = `20s 内 face_selected 没落进宿主的 status.face（want=${want}）`;
          }
          // ③ 选定不改画面：选人是「换个服务对象」，不是「调了一次图」
          const afterSelect = bad ? null : await peek();
          if (!bad) {
            changedBySelect = (afterReject && afterSelect && full(afterReject) && full(afterSelect))
              ? diffBytes(afterReject.pixels, afterSelect.pixels) : -1;
            if (changedBySelect !== 0) {
              bad = `点选人物就改了画面 ${changedBySelect} 字节：选人不等于调图`;
            }
          }
          // ④ 选定之后再推同样的三个数：这一回要建层、要出帧
          if (!bad) {
            try {
              await runDeform("set", { slim_face: 0.6, big_eye: 0.3, small_chin: 0 });
            } catch (e) { bad = `runDeform 抛错（已选定那一臂）: ${e}`; }
            for (let i = 0; i < 200 && !bad; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.deform && st.deform.lit && st.deform.action === "set") { df = st.deform; break; }
            }
            if (!bad && !df) bad = "选定后 20s 内没等到点火的 deform_done";
          }
          const after = bad ? null : await peek();
          const stF = await engineStatus().catch(() => null);
          const fF = faceStateOf(stF, null);
          const box = fF?.faces.find((x) => x.index === want)?.box ?? null;
          if (!bad && after && afterReject && full(after) && full(afterReject)
            && after.w === afterReject.w && after.h === afterReject.h && box && box.length === 4) {
            // 与 ADR-0009 同一个口径：TPS 是紧支撑窗，实测最远变化落在 1.58× 脸半对角，
            // 所以「没被选中的那一圈」取 1.6R 之外——那里必须一格不动。
            const cx = ((box[0] + box[2]) / 2) * after.w;
            const cy = ((box[1] + box[3]) / 2) * after.h;
            const r = 0.5 * Math.hypot((box[2] - box[0]) * after.w, (box[3] - box[1]) * after.h);
            const lim = 1.6 * r;
            insideChanged = 0; outsideChanged = 0;
            for (let y = 0; y < after.h; y++) {
              for (let x = 0; x < after.w; x++) {
                const i = (y * after.w + x) * 4;
                if (after.pixels[i] === afterReject.pixels[i]
                  && after.pixels[i + 1] === afterReject.pixels[i + 1]
                  && after.pixels[i + 2] === afterReject.pixels[i + 2]) continue;
                if (Math.hypot(x - cx, y - cy) <= lim) insideChanged++; else outsideChanged++;
              }
            }
          } else if (!bad) {
            bad = "两份快照不是同一块完整画布或缺脸盒：另一张脸那一圈没法量";
          }
          await report(`M0_FACE ${JSON.stringify(bad ? { bad, numFaces, want } : {
            numFaces, want, blockedBefore, pickSource, changedBySelect,
            canvas: `${after?.w ?? 0}x${after?.h ?? 0}`, proxy: `${pw}x${ph}`,
            backend: df?.landmark_backend ?? "", built: df?.built ?? null,
            bytesDeform: df?.bytes_deform ?? 0, deformMs: df?.deform_ms ?? 0,
            supportShare: df?.support_share ?? 0, insideChanged, outsideChanged,
          })}`);
        }
      }
      // 层级覆盖与继承（LNX-PORTRAIT-004）自动通道：跟着 LRT_AUTO_FACE 一起点火。
      // 库里那八段判据连的是裸引擎；这一段证的是 runDeform(…, scope) → Rust deform
      // 的第三个参数 → 引擎 deform_done 的 scope/overrides 那几格 → 宿主轮询状态 →
      // 用户看见的那一帧。中间每一层都只有真窗口能证明。
      // 前置：上面那一臂已在这张多人图上选定 want 号，并把全人物默认落成 {0.6, 0.3, 0}。
      if (env.auto_face) {
        const wantL = Number(env.auto_face);
        const fullL = (f: any) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
        let lbad = "";
        let personDone: DeformInfo | null = null;
        let defaultDone: DeformInfo | null = null;
        let inheritDone: DeformInfo | null = null;
        let insideChangedL = -1;
        let otherChangedL = -1;
        let sameLayerBytes = -1;
        // 等一条符合判据的 deform_done：不能只看 action，"覆盖了没"只有层级那几格说得出
        const waitDeform = async (ok: (d: DeformInfo | null) => boolean, why: string) => {
          for (let i = 0; i < 200; i++) {
            await sleep(100);
            const st = await engineStatus().catch(() => null);
            if (st && ok(st.deform ?? null)) return st.deform;
          }
          lbad = `20s 内没等到${why}`;
          return null;
        };
        // ① a) 先把默认改成 slim 0.2（此时还没有任何覆盖）→ 这一幅就是"纯默认"的参照
        if (!lbad) {
          try { await runDeform("set", { slim_face: 0.2 }, "all"); }
          catch (e) { lbad = `runDeform(scope=all) 抛错: ${e}`; }
        }
        const fDefault = lbad ? null : await waitDeform(
          (d) => !!d && d.action === "set" && d.scope === "all"
            && Math.abs((d.amounts?.slim_face ?? 9) - 0.2) < 1e-6,
          "到 scope=all 的默认变更");
        const base = lbad ? null : await peek();
        // ① b) 只给这一张挂覆盖（big_eye 0.9）：引擎必须报出 scope=person 与那一格名单
        if (!lbad) {
          try { await runDeform("set", { big_eye: 0.9 }, "person"); }
          catch (e) { lbad = `runDeform(scope=person) 抛错: ${e}`; }
        }
        if (!lbad) {
          personDone = await waitDeform(
            (d) => !!d && d.action === "set" && d.scope === "person"
              && (d.overridden_kinds ?? []).includes("big_eye") && d.inherited === false,
            "scope=person 的覆盖账（overridden_kinds/inherited）");
        }
        const litL = lbad ? null : await peek();
        if (!lbad && !personDone) lbad = lbad || "没等到 scope=person 那一笔的帧";
        // ② 挂覆盖只许动被选中那一张：与 ADR-0009 同一个口径（1.6× 脸半对角之外必须不动）
        if (!lbad && base && litL && fullL(base) && fullL(litL)
          && base.w === litL.w && base.h === litL.h) {
          const stF = await engineStatus().catch(() => null);
          const fF = faceStateOf(stF, null);
          const box = fF?.faces.find((x) => x.index === wantL)?.box ?? null;
          if (box && box.length === 4) {
            const cx = ((box[0] + box[2]) / 2) * litL.w;
            const cy = ((box[1] + box[3]) / 2) * litL.h;
            const r = 0.5 * Math.hypot((box[2] - box[0]) * litL.w, (box[3] - box[1]) * litL.h);
            const lim = 1.6 * r;
            insideChangedL = 0; otherChangedL = 0;
            for (let y = 0; y < litL.h; y++) {
              for (let x = 0; x < litL.w; x++) {
                const i = (y * litL.w + x) * 4;
                if (litL.pixels[i] === base.pixels[i] && litL.pixels[i + 1] === base.pixels[i + 1]
                  && litL.pixels[i + 2] === base.pixels[i + 2]) continue;
                if (Math.hypot(x - cx, y - cy) <= lim) insideChangedL++; else otherChangedL++;
              }
            }
          } else {
            lbad = `选定那一张没有脸盒（index=${wantL}）：作用面没法量`;
          }
        }
        // ③ 再改默认（slim 0.2→0.6）：覆盖那一格必须继续是 0.9，未覆盖那格跟到 0.6
        if (!lbad) {
          try { await runDeform("set", { slim_face: 0.6 }, "all"); }
          catch (e) { lbad = `runDeform(改默认) 抛错: ${e}`; }
        }
        if (!lbad) {
          defaultDone = await waitDeform(
            (d) => !!d && d.action === "set" && d.scope === "all"
              && Math.abs((d.amounts?.big_eye ?? 9) - 0.9) < 1e-6
              && Math.abs((d.amounts?.slim_face ?? 9) - 0.6) < 1e-6,
            "覆盖项继续生效而默认那格跟随（big_eye 0.9 / slim 0.6）");
        }
        // ④ 恢复继承：合成必须落回默认，且画面逐字节等于"两条路径走到同一个层级状态"的另一幅
        if (!lbad) {
          try { await runDeform("inherit"); }
          catch (e) { lbad = `runDeform(inherit) 抛错: ${e}`; }
        }
        if (!lbad) {
          inheritDone = await waitDeform(
            (d) => !!d && d.action === "inherit" && (d.overridden_kinds ?? []).length === 0
              && d.inherited === true && Math.abs((d.amounts?.big_eye ?? 9) - 0.3) < 1e-6,
            "恢复继承后全按层级合成（覆盖名单空、big_eye 回到默认 0.3）");
        }
        const fInherit = lbad ? null : await peek();
        // 另一条路径回到同一个层级状态：再挂一次覆盖（同值）然后再次 inherit。
        // 同一组默认 + 同一份"没有覆盖" → 像素必须逐字节相同，否则合成不是单一出处
        if (!lbad) {
          try { await runDeform("set", { big_eye: 0.95 }, "person"); }
          catch (e) { lbad = `runDeform(第二次覆盖) 抛错: ${e}`; }
        }
        if (!lbad) {
          const again = await waitDeform(
            (d) => !!d && d.scope === "person" && (d.overridden_kinds ?? []).includes("big_eye"),
            "第二次覆盖的账");
          if (again) {
            try { await runDeform("inherit"); }
            catch (e) { lbad = `runDeform(第二次 inherit) 抛错: ${e}`; }
          }
        }
        if (!lbad) {
          await waitDeform((d) => !!d && d.action === "inherit" && d.inherited === true,
            "第二次恢复继承");
        }
        const fAgain = lbad ? null : await peek();
        if (!lbad && fInherit && fAgain && fullL(fInherit) && fullL(fAgain)
          && fInherit.w === fAgain.w && fInherit.h === fAgain.h) {
          sameLayerBytes = diffBytes(fInherit.pixels, fAgain.pixels);
        }
        await report(`M0_LAYER ${JSON.stringify(lbad ? { bad: lbad, want: wantL } : {
          want: wantL,
          defaultFirst: fDefault?.amounts ?? {},
          personScope: personDone?.scope ?? "",
          overriddenKinds: personDone?.overridden_kinds ?? [],
          inheritedBeforeOverride: personDone?.inherited ?? null,
          defaultAmounts: personDone?.default ?? {},
          overrideAmounts: personDone?.amounts ?? {},
          keptAfterDefaultChange: defaultDone?.amounts ?? {},
          inheritAmounts: inheritDone?.amounts ?? {},
          inheritOverrideCount: (inheritDone?.overrides ?? []).length,
          insideChanged: insideChangedL, otherChanged: otherChangedL,
          sameLayerBytes,
        })}`);
      }
      // 等宿主把下一条 history_state 搬进轮询状态：撤销的答复是异步的，
      // 而它的 doc_state 就是"引擎认为现在该摆哪些滑块"的唯一出处
      const waitHistory = async (rev: number, ms = 20000) => {
        for (let i = 0; i < ms / 100; i++) {
          await sleep(100);
          const st = await engineStatus().catch(() => null);
          if (st && st.history_rev !== rev && st.history) return st.history;
        }
        return null;
      };
      // 批量出片（M4）自动通道："<目录>[@<格式>[@<tile>[@<scale>[@<锐量>]]]]"。
      // 这一条与上面几条同一个身份：只有真窗口能证明 runExport → Rust export →
      // 引擎 export_done 对得上；而且落盘尺寸是"导出的是满幅不是代理档"的唯一直接
      // 证据，所以它与 image_ready 的代理档尺寸一起报出去（proxy vs out）。
      // M7 在它后面接上 scale/锐量：同一个口子，证的还是"参数一路递到了落盘那一帧"。
      if (env.auto_export) {
        const [dir, fmt, tileStr, scaleStr, sharpStr] = env.auto_export.split("@");
        if (!dir) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_EXPORT=${env.auto_export}（要 目录[@格式[@tile[@倍率[@锐量]]]]）`);
        } else {
          const proxy = image ? `${image.w}x${image.h}` : "-";
          const scale = scaleStr ? Number(scaleStr) : undefined;
          const sharpen = sharpStr ? Number(sharpStr) : undefined;
          try {
            await runExport(dir, {
              format: fmt || undefined,
              tile: tileStr ? Number(tileStr) : undefined,
              scale: scale && Number.isFinite(scale) && scale > 1 ? scale : undefined,
              sharpen: sharpen && Number.isFinite(sharpen) && sharpen > 0 ? sharpen : undefined,
            });
          } catch (e) {
            await report(`M0_ERROR runExport 失败: ${e}`);
          }
          let got: ExportDone | null = null;
          for (let i = 0; i < 600 && !got; i++) {
            await sleep(200);
            const st = await engineStatus().catch(() => null);
            if (st?.export) got = st.export;
          }
          await report(`M0_EXPORT ${JSON.stringify(got ? {
            dir, proxy, full: got.images.map((x) => (x.error ? `ERR:${x.stage}` : `${x.w}x${x.h}`)),
            tiles: got.images.map((x) => x.tiles ?? 0),
            margin: got.images.map((x) => x.margin_px ?? 0),
            bytes: got.images.map((x) => x.bytes ?? 0),
            failed: got.failed, total: got.total, totalMs: got.total_ms,
            seg: got.images.map((x) => x.seg_ms ?? {}),
            skipped: got.images.map((x) => x.skipped ?? []),
            // 放大（M7）要的直接证据：请求的倍率 vs 引擎报回的倍率 vs 落盘尺寸/源尺寸。
            // 只看"w×h 变大了"分不出"真做了 2×"与"源图本来就大"，所以 ratio 单独算。
            wantScale: scale ?? 1, gotScale: got.scale ?? 1,
            backend: got.upscale_backend ?? null, sharpen: got.sharpen ?? 0,
            srcs: got.images.map((x) => `${x.src_w ?? 0}x${x.src_h ?? 0}`),
            ratios: got.images.map((x) => (x.src_w ? +(x.w! / x.src_w).toFixed(3) : 0)),
            upscaleMs: got.images.map((x) => x.upscale_ms ?? 0),
            sharpenMs: got.images.map((x) => x.sharpen_ms ?? 0),
          } : { bad: "120s 内没等到 export_done", dir, proxy })}`);
        }
      }
      // 底片条（M5-a）自动通道："<目录>[@<切到第几张>[@<长边>]]"。
      // 这一条要证的是签名与数字：TS runSession → Rust session → 引擎 session_state
      // 对得上，而且切走再切回来时引擎报回来的 doc_state 与走时是同一份。
      // 画面像素这里也量（peek_frame 取三次快照比字节）：先前打算只让协议用例
      // （test_switching_documents_returns_the_exact_same_frame）逐字节钉画面，理由是
      // "装机件里那条路是同一份引擎代码"。但那份用例连的是裸引擎，中间隔着 Rust 的
      // session/filmstrip 两条命令与宿主的状态搬运——那两层恰恰只有真窗口能证明。
      // 所以这里量的是"用户看见的那一帧"，不是"引擎算出来的那一帧"。
      if (env.auto_filmstrip) {
        const [dir, pickStr, edgeStr] = env.auto_filmstrip.split("@");
        if (!dir) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_FILMSTRIP=${env.auto_filmstrip}（要 目录[@第几张[@长边]]）`);
        } else {
          const pick = Number(pickStr ?? "1");
          const edge = Number(edgeStr ?? "0");
          const st0 = await engineStatus().catch(() => null);
          const home = st0?.image?.doc ?? null;
          const homeIdx0 = st0?.image?.session_index ?? -1;
          try {
            await runSession("scan", { dir, thumbs: true, ...(edge >= 32 ? { edge } : {}) });
          } catch (e) {
            await report(`M0_ERROR runSession(scan) 失败: ${e}`);
          }
          let sess: SessionState | null = null;
          for (let i = 0; i < 300; i++) {
            await sleep(200);
            const st = await engineStatus().catch(() => null);
            if (st?.session) sess = st.session;
            if (sess && !sess.thumbs_running && sess.count > 0
              && sess.docs.every((d) => d.thumb || d.thumb_error)) break;
          }
          // 基线现取一次：上一条 session_state 可能是开图那一刻发的，中间那几档
          // 自动调参（lut/grade/deform）都不在它里面
          await runSession("state").catch(() => undefined);
          await sleep(400);
          const stB = await engineStatus().catch(() => null);
          sess = stB?.session ?? sess;
          const before = sess?.doc_state ?? null;
          const docs = sess?.docs ?? [];
          // 当前那一格的 index 必须在扫描之后重取：扫进来的那一批会整条替换底片条，
          // 原来那张被挪到列表末尾（引擎只保证"当前那张不会被放下"）。拿扫描前的 0
          // 去"切回"，切到的其实是新列表的第 0 格——引擎完全照办，日志上一个错都
          // 看不出来，而这条通道想证的"绕回原样"当场就变成假的。所以这里以引擎报的
          // index 为准，并且核对 current 还是不是那张
          const homeIdx = sess?.index ?? -1;
          if (sess && home && sess.current !== home) {
            await report(`M0_ERROR 扫描后当前文档换了：${sess.current} ≠ ${home}（不能拿它当基线）`);
          }
          let away: DocState | null = null;
          let back: DocState | null = null;
          let awayPath = "";
          let backPath = "";
          let switchMs = -1;
          const idx = pick >= 0 && pick < docs.length ? pick : -1;
          let pixHome = "", pixAway = "", pixBack = "";
          let seqHome = -1, seqAway = -1, seqBack = -1;
          let diffAway = -1, diffBack = -1;
          // 引擎在 image_ready 里报的代理档尺寸：拿它核对"这次快照取的到底是哪张的帧"。
          // 换到不同幅面的那张时 shm 会整块重建（seq 从 1 重来），只看 seq 递增就会
          // 在那一档判错，而只看字节又证明不了取到的是新帧不是陈旧帧
          let awayReady = "", backReady = "";
          if (idx >= 0 && homeIdx >= 0) {
            const f0 = await peek();
            pixHome = f0 ? `${f0.w}x${f0.h}` : "";
            seqHome = f0?.seq ?? -1;
            const homePix = f0?.pixels ?? null;
            await runSession("select", { index: idx }).catch((e) => report(`M0_ERROR select 失败: ${e}`));
            for (let i = 0; i < 200; i++) {
              await sleep(150);
              const st = await engineStatus().catch(() => null);
              if (st?.image && st.image.doc !== home) {
                away = st.image.doc_state; awayPath = st.image.doc; switchMs = st.image.import_ms;
                awayReady = `${st.image.w}x${st.image.h}`; break;
              }
            }
            {
              const f1 = await peek();
              pixAway = f1 ? `${f1.w}x${f1.h}` : "";
              seqAway = f1?.seq ?? -1;
              diffAway = diffBytes(homePix, f1?.pixels ?? null);
            }
            await runSession("select", { index: homeIdx }).catch((e) => report(`M0_ERROR 切回失败: ${e}`));
            for (let i = 0; i < 200; i++) {
              await sleep(150);
              const st = await engineStatus().catch(() => null);
              if (st?.image && st.image.switched && st.image.doc === home) {
                back = st.image.doc_state; backPath = st.image.doc;
                backReady = `${st.image.w}x${st.image.h}`; break;
              }
            }
            const f2 = await peek();
            pixBack = f2 ? `${f2.w}x${f2.h}` : "";
            seqBack = f2?.seq ?? -1;
            diffBack = diffBytes(homePix, f2?.pixels ?? null);
          }
          // DOM 证据（M9-d）：GL 表面抓不到图，但底片条是 DOM——角标在不在、写的
          // 是什么，可以直接问 DOM。“引擎报了 preview”与“用户看得见这件事”是两层，
          // 差的恰恰是这一层，只看引擎上报抓不到它丢没丢。
          await sleep(150);
          const pvBadges = Array.from(document.querySelectorAll(".strip .cell .badge.pv"))
            .map((el) => (el.textContent ?? "").trim());
          await report(`M0_FILMSTRIP ${JSON.stringify({
            dir, count: sess?.count ?? 0, index: sess?.index ?? -1, home, homeIdx, homeIdx0,
            names: docs.map((d) => d.name),
            thumbCount: docs.filter((d) => d.thumb).length,
            thumbBytes: docs.reduce((a, d) => a + (d.thumb?.bytes ?? 0), 0),
            // RAW 格与“来路是相机内嵌预览”的格分开报：底片条能不能把 DNG 画出来是一回事，
            // 有没有如实告诉用户画的是预览是另一回事。后者只能从这里看得到。
            previewCells: docs.filter((d) => d.thumb?.preview).length,
            pvBadges,
            formats: Array.from(new Set(docs.map((d) => d.thumb?.format).filter(Boolean))),
            longestEdge: Math.max(0, ...docs.map((d) => (d.thumb ? Math.max(d.thumb.w, d.thumb.h) : 0))),
            failed: docs.filter((d) => d.thumb_error).map((d) => `${d.name}:${d.thumb_error}`),
            awayPath, backPath, switchMs,
            before, away, back,
            kept: !!before && !!back && JSON.stringify(before) === JSON.stringify(back),
            // 切过去那张必须干干净净：home 的笔迹漏进新文档，就是"上一张的工刷到
            // 这一张上"。先前这条写的是 away.counts.repair > 0（把漏了当成通过），
            // 方向反了——名字也跟着反，所以一并改成 awayClean
            awayClean: !!away && away.counts.repair === 0 && away.counts.light === 0
              && away.counts.repair_redo === 0 && away.counts.light_redo === 0,
            // 画面这一对才是"切回来还是不是那张"的直接证据：绕回必须 0 字节不同，
            // 而切走那一步必须**有**不同（否则这一对判据是空的——两张图长得一样时
            // "0 字节不同"说明不了任何事）
            frames: `${pixHome}/${pixAway}/${pixBack}`,
            seqs: [seqHome, seqAway, seqBack],
            readyDims: [awayReady, backReady],
            diffAwayBytes: diffAway,
            diffBackBytes: diffBack,
            pixelKept: diffBack === 0,
            // "切走了"的直接证据有两个：画布换了（不同幅面那张）或同一块画布上的
            // 字节真的不同（同幅面那张）。两个都不成立才是没换
            pixelLeft: pixAway !== pixHome || diffAway > 0,
            canvasChanged: pixAway !== pixHome,
          })}`);
        }
      }
      // 挑图建议（LNX-PICK-001）自动通道：LRT_AUTO_PICK="<重复>/<清晰>/<曝光>/<眼睛>"。
      // 引擎那半的判据已由 test_pick + 端到端用例逐条钉住；这一条要证的是宿主这四层签名
      // （runPick → Rust pick → 引擎 pick_* → status.pick），再加上只有真窗口能给的最后一层：
      // 徽章确实出现在用户看得见的 DOM 里、原因里带着数值与阈值、并且没有一处写着"删"。
      if (env.auto_pick) {
        const arms = env.auto_pick.split("/");
        if (arms.length !== 4) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_PICK=${env.auto_pick}`
            + "（要 重复/清晰/曝光/眼睛 四档名）");
        } else {
          const sens = { duplicate: arms[0], blur: arms[1], exposure: arms[2], eyes: arms[3] };
          const names0 = ((await fetchFilmstrip().catch(() => null))?.session?.docs ?? [])
            .map((d) => d.name).sort();
          await runPick("analyze", { ...sens, force: true });
          let run: PickRun | null = null;
          let err: string | null = null;
          for (let i = 0; i < 900; i++) {
            await sleep(200);
            const st = await engineStatus().catch(() => null);
            if (st?.last_error) { err = st.last_error; break; }
            if (st?.pick && (st.pick.event === "pick_done" || st.pick.event === "pick_state")) {
              run = st.pick;
              break;
            }
          }
          await sleep(300);
          const st2 = await engineStatus().catch(() => null);
          const fs = await fetchFilmstrip().catch(() => null);
          const docs = fs?.session?.docs ?? [];
          const withPick = docs.filter((d) => d.pick);
          const labelCount: Record<string, number> = {};
          for (const d of withPick) {
            for (const l of d.pick?.labels ?? []) labelCount[l] = (labelCount[l] ?? 0) + 1;
          }
          const badges = Array.from(document.querySelectorAll(".strip .cell .badge.pk"))
            .map((el) => (el.textContent ?? "").trim());
          await report(`M0_PICK_RESULT ${JSON.stringify({
            sens, event: run?.event ?? null, err,
            targets: run?.targets ?? null, measured: run?.measured ?? null,
            failed: run?.failed ?? null, stopped: run?.stopped ?? null,
            groupSizes: (run?.groups ?? []).map((g) => g.size),
            fingerprint: run?.fingerprint ?? null, algo: run?.algo ?? null,
            // 两条独立通道来自装机引擎自己：握手 ready 里那份判据指纹与这次事件里那份。
            // 不相等就是"跑靶读到的判据不是壳握手时承诺的那一版"（发布自证要的就是这一句）
            readyFingerprint: st2?.ready_caps?.pick_fingerprint ?? null,
            readyAlgo: st2?.ready_caps?.pick_algo ?? null,
            readyArms: st2?.ready_caps?.pick_sensitivities ?? null,
            eyesBackend: run?.eyes_backend ?? null, eyesError: run?.eyes_error ?? null,
            batchMedian: run?.batch_median_ratio ?? null, edge: run?.edge ?? null,
            measureMs: run?.measure_ms ?? null, totalMs: run?.total_ms ?? null,
            pickItems: st2?.pick_items ?? -1, cells: docs.length, withPick: withPick.length,
            names0, namesNow: docs.map((d) => d.name).sort(), labels: labelCount,
            badges,
            // 冻结件那两句在宿主这一层的形状：可覆盖 / 不自动删除（引擎恒假，UI 不许改写）
            overridableAll: withPick.every((d) => d.pick?.overridable === true),
            autoDeleteAny: withPick.some((d) => d.pick?.auto_deleted === true
              || d.pick?.auto_trashed === true),
            overridden: withPick.filter((d) => d.pick?.overridden_by_user === true).length,
            reasonsArmed: withPick.every((d) => (d.pick?.reasons ?? []).length === 0
              || (d.pick?.reasons ?? []).every((r) => !!r.method
                && r.value !== undefined && r.threshold !== undefined)),
            deleteWord: withPick.some((d) => (d.pick?.reasons ?? [])
              .some((r) => (r.text ?? "").includes("删"))),
          })}`);
        }
      }
      // 撤销/重做（M5-b）自动通道：LRT_AUTO_HISTORY=<强度值>。
      // 引擎那条链已有协议用例逐字节对拍（test_undo_walks_back_through_every_layer），
      // 而那份用例连的是裸引擎。这一条要证的是宿主这四层：
      //   ① runHistory → Rust history → 引擎 history_state 的签名对得上；
      //   ② 画面真的逐字节退回去/回来（peek_frame 从装机件的 shm 里取）；
      //   ③ 宿主按引擎那份 doc_state 重摆了滑块（applied 是唯一直接证据——滑块没跟着
      //      退而画面退了，用户在 UI 上看到的还是 0.9）；
      //   ④ 引擎在 ready 里报的能力名单真的送到了宿主（historyEditCmds）：这一条
      //      上一轮报的是 0，抓出的正是"宿主从没发过 hello"那个缺陷。
      // 基线一律现问引擎（askHistory("state")），不许拿轮询里那份 doc_report：
      // 编辑命令不带 doc_state，拿它就是拿开图那一刻的账来比现在的动作。
      if (env.auto_history) {
        const v = Number(env.auto_history);
        if (!Number.isFinite(v) || v < 0 || v > 1) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_HISTORY=${env.auto_history}（要一个 0–1 的强度值）`);
        } else {
          const askHistory = async (action: "undo" | "redo" | "state" | "clear") => {
            const before = (await engineStatus().catch(() => null))?.history_rev ?? -1;
            await runHistory(action).catch((e) => report(`M0_ERROR runHistory(${action}) 失败: ${e}`));
            const got = await waitHistory(before);
            if (!got) await report(`M0_ERROR 没等到 history ${action} 的答复`);
            return got;
          };
          const st0 = await engineStatus().catch(() => null);
          const editCmds = st0?.history_edit_cmds?.length ?? -1;
          const q0 = await askHistory("state");
          const steps0 = q0?.undo_steps ?? -1;
          const strength0 = q0?.doc_state?.strength ?? -1;
          const base = await peek();
          const homePix = base?.pixels ?? null;
          // 一次手势：两条 set_strength 都只带 value → 同组、窗口内 → 应当只占一步。
          // 第二跳的落点按"离基线强度足够远"来选（不是 v*0.6 那种固定比例）：
          // 挂满图层那一臂的基线强度本来就是 0.5，v=0.85 的 0.6 倍正好 0.51，画面
          // 只差 5515 字节——"撤回去 0 字节"在这种薄鉴别力下几乎不构成证据。
          const target = (q0?.doc_state?.strength ?? 0) <= 0.5 ? 0.95 : 0.05;
          await setStrength(v).catch((e) => report(`M0_ERROR setStrength 失败: ${e}`));
          await sleep(200);
          await setStrength(target).catch((e) => report(`M0_ERROR setStrength 失败: ${e}`));
          await sleep(500);
          const strong = await peek();
          const q1 = await askHistory("state");
          const steps1 = q1?.undo_steps ?? -1;
          const strengthEdit = q1?.doc_state?.strength ?? -1;
          const appliedBefore = applied.current;
          // 撤销：像素必须逐字节等于基线，滑块的 echo 必须回到基线那一刻的值
          const u = await askHistory("undo");
          await refreshStatus();
          const appliedUndo = applied.current;
          const afterUndo = await peek();
          // 重做：必须回到强版本
          const r = await askHistory("redo");
          await refreshStatus();
          const appliedRedo = applied.current;
          const afterRedo = await peek();
          await report(`M0_HISTORY ${JSON.stringify({
            value: v, editCmds, steps0, steps1,
            undoSteps: u?.undo_steps ?? -1, redoSteps: u?.redo_steps ?? -1,
            undoSteps2: r?.undo_steps ?? -1, redoSteps2: r?.redo_steps ?? -1,
            undoMs: u?.history_ms ?? -1, redoMs: r?.history_ms ?? -1,
            renderMs: u?.render_ms ?? -1,
            strength0, strengthEdit,
            strengthUndo: u?.doc_state?.strength ?? -1,
            strengthRedo: r?.doc_state?.strength ?? -1,
            seqs: [base?.seq ?? -1, strong?.seq ?? -1, afterUndo?.seq ?? -1, afterRedo?.seq ?? -1],
            // 鉴别力：上了强度画面必须变（否则下面那两条"相等"是空的）
            changed: diffBytes(homePix, strong?.pixels ?? null),
            // 保真：撤销 == 基线帧、重做 == 撤销前，都是逐字节
            undoDiff: diffBytes(homePix, afterUndo?.pixels ?? null),
            redoDiff: diffBytes(strong?.pixels ?? null, afterRedo?.pixels ?? null),
            // 宿主重摆：applied 由 applyDocState 写，from 说的是哪一条事件摆的
            applied: [appliedBefore?.from ?? "", appliedUndo?.from ?? "", appliedRedo?.from ?? ""],
            appliedStrength: [appliedBefore?.strength ?? -1, appliedUndo?.strength ?? -1,
                              appliedRedo?.strength ?? -1],
            stepsMerged: steps0 >= 0 && steps1 === steps0 + 1,
          })}`);
        }
      }
      for (let i = 0; i < 100; i++) {
        const st = await engineStatus().catch(() => null);
        if (st?.has_shm) break;
        await sleep(100);
      }
      try {
        await benchStart(bench);
      } catch (e) {
        // 启动被拒就必须收场：继续往下只会空轮询 400×500 ms，最后被 timeout 掐掉，
        // 日志里连“为什么没数据”都不留
        await report(`M0_ERROR bench 启动失败: ${e}`);
        await quit().catch(() => undefined);
        return;
      }
      for (let i = 0; i < 400; i++) {
        await sleep(500);
        const s = await benchStats().catch(() => null);
        if (s?.bench_done) {
          await sleep(1500); // 等在途帧的 ack 收尾
          const final = await benchStats().catch(() => null);
          await report(
            `M0_STATS ${JSON.stringify({ ...final, ...bench, device: env.device, tier: env.skip_pixels === "1" ? 0 : env.skip_draw === "1" ? 1 : 2, upload: env.upload, chunks: env.chunks, ctx: env.no_ctx !== "1", dirtyFrac: env.dirty_frac, hz: +(1000 / bench.intervalMs).toFixed(1), ...(image ? { decodeMs: image.decode_ms, importMs: image.import_ms, scaleMs: image.scale_ms, shmMs: image.shm_ms, attachMs: image.attach_ms, firstFrameMs: image.first_frame_ms, draft: image.draft, draftSize: image.draft_size, pipeDevice: image.device, bytesPerFrame: image.bytes_per_frame, proxy: `${image.w}x${image.h}` } : {}), ...(pre ? { pcBackend: pre.backend, pcInferMs: pre.infer_ms, pcAttachMs: pre.attach_ms, pcTotalMs: pre.total_ms, maskBytes: pre.mask_bytes, channels: pre.mask_channels, residentDevice: pre.resident_device, activeChannel: pre.active_channel } : {}) })}`,
          );
          break;
        }
      }
      // 换底层在整个跑靶（几百帧）之后还在不在：这一条是"常驻合成不是只能
      // 一次性点亮"的直接证据。只看 M0_BG_REAPPLY 不够——那是 bench **开始前**的
      // 状态；300 帧里被谁摸了一下、重连时 _attach_pipeline 没重挂上，只有此处能发现。
      if (env.auto_background) {
        const stLive = await engineStatus().catch(() => null);
        await report(`M0_BG_LIVE ${JSON.stringify({
          active: stLive?.background?.bg_active ?? false,
          action: stLive?.background?.action ?? null,
          bytesBg: stLive?.background?.bytes_bg ?? 0,
          emitted: stLive?.emitted ?? 0, delivered: stLive?.delivered ?? 0,
        })}`);
      }
      await report(`M0_HUD ${JSON.stringify({ ...hudRef.current, active: true })}`);
      if (env.keep_open === "1") {
        // 取证臂：自动序列已经跑完，窗口留着给截图/人工核对。
        await report("M0_KEEP_OPEN 1");
        return;
      }
      await sleep(300);
      await quit().catch(() => undefined);
    })();
  }, []);

}
