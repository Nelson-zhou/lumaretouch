#!/usr/bin/env bash
# 开箱即用校验（M5-c）：**装机的包**在一台"只有 deb + 跑过一次运行时引导"的机器上
# 到底能不能用。全程不带任何 LRT_* 开发变量，也不许指回仓库。
#
# 为什么这条必须在真窗口里跑，而不是 pytest：
#   · 裸引擎的协议用例自己会发 hello、自己指定解释器，永远碰不到"壳找不到运行时"
#     这一层——M5-b 那一轮就是靠真窗口才抓出"宿主从没握手"；
#   · "开箱即用"是三件事的合取：包内容对、壳找得到运行时、运行时真能出画面。
#     任何一件只在装机 + 真窗口里才成立，另两件都能在别处验。
#
# M8 起这一轮把 M6/M7 也接进来跑（换底六臂 + 2× 出片），理由不是凑数：装机件里
# "ready 报没报 matting_backends / upscale_backends"与"换底、放大递到落盘那一路对不对"
# 只有裸环境的真窗口能量；开发 env 里跑绿了，说明不了这包在别人机器上一样绿。
# 帧通路也因此是在**挂着换底层**的状态下量的（链尾多一层常驻合成），比关掉再测好看
# 一点更贴近用户现场。
#
# 跑法（顺序即依赖）：
#   packaging/build-deb.sh → packaging/install-deb.sh → packaging/setup-runtime.sh
#   → packaging/m5-release-check.sh
#
# 判据一律"缺了就是不过"，没有"读不到就跳过"这一支：跳过会把这个校验慢慢变成一份假绿。
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
ver=$(cat "$here/VERSION")
log=/tmp/m5-release-check.$$.log
fixture=${LRT_CHECK_IMAGE:-$repo/engine/tests/fixtures/portrait-1024x1280.jpg}
want_prefix="/LumaRetouch/engine/venv/bin/python"
# 出片臂的落盘目录：每轮清干净，校验时拿磁盘上的 IHDR 与引擎报回的尺寸对账
outdir=/tmp/lrt-release-export.$$
want_secs=900                      # 这轮要多跑换底与 2× 出片，预算从 200 s 提到 450 s

pass=0; fail=0
ok()   { echo "  ✓ $1"; pass=$((pass + 1)); }
no()   { echo "  × $1"; fail=$((fail + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

echo "── 1. 装机的包：账要对得上刚打的那一份"
if ! have dpkg; then
  no "本机没有 dpkg，这一节整片做不了（不要在有 GPU 的开发机上跳过它）"; echo
else
  pkg=luma-retouch
  inst=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null)
  [ "$inst" = "$ver" ] && ok "已装版本 $inst == packaging/VERSION ($ver)" \
                      || no "已装版本 ${inst:-<没装>} ≠ 仓库的 $ver：先跑 install-deb.sh"
  files=$(dpkg -L "$pkg" 2>/dev/null)
  for need in /usr/bin/lumaretouch \
              /usr/lib/LumaRetouch/engine/src/lumaretouch_engine/server.py \
              /usr/lib/LumaRetouch/engine/setup-runtime.sh \
              /usr/lib/LumaRetouch/engine/runtime/requirements-rocm.txt; do
    if echo "$files" | grep -qx "$need"; then ok "包内文件在位：$need"
    else no "包内缺文件：$need（装机后这条路就是断的）"; fi
  done
  if [ -x /usr/lib/LumaRetouch/engine/setup-runtime.sh ]; then
    ok "运行时引导脚本装机后带执行位"
  else
    no "运行时引导脚本装机后不可执行：$(stat -c '%a' /usr/lib/LumaRetouch/engine/setup-runtime.sh 2>/dev/null || echo 不存在)"
  fi
  junk=$(echo "$files" | grep -E '\.pyc$|__pycache__' | head -3)
  [ -z "$junk" ] && ok "包内零字节码" || no "包内混进字节码：$(echo "$junk" | tr '\n' ' ')"
  # 本机路径：发布物里出现当前用户的 home，等于承认这包只在打它的机器上能用
  leak=$(grep -rl "$HOME" /usr/lib/LumaRetouch/engine/runtime 2>/dev/null | head -2)
  [ -z "$leak" ] && ok "随包清单零本机路径" || no "随包清单写死了本机路径：$leak"
  # Depends：重复项 + 每一项在本机能不能解析（虚拟包由已装包 Provides 也算解析）
  deps=$(dpkg-query -W -f='${Depends}' "$pkg" 2>/dev/null | tr ',' '\n' | sed 's/^ *//; s/ .*//' | grep -v '^$')
  dup=$(echo "$deps" | sort | uniq -d | tr '\n' ' ')
  [ -z "$dup" ] && ok "Depends 无重复项" || no "Depends 里有重复：$dup"
  for d in $deps; do
    if apt-cache policy "$d" 2>/dev/null | grep -qE '^\s+Candidate:\s+[0-9]' \
       || dpkg -s "$d" >/dev/null 2>&1; then
      ok "依赖可解析：$d"
    else
      # t64 过渡期常见的写法：名字不存在，由另一个包 Provides 同名虚拟包
      if dpkg-query -W -f='${Provides}' '*' 2>/dev/null | grep -q "\b$d\b"; then
        ok "依赖由虚拟包满足：$d"
      else
        no "依赖在本机解析不出来：$d —— apt 装这个包会直接失败"
      fi
    fi
  done
fi

echo "── 2. 运行时：候选表要真命中装好的那一份"
rt=${XDG_DATA_HOME:-$HOME/.local/share}/LumaRetouch/engine/venv/bin/python
if [ -x "$rt" ]; then
  ok "用户级运行时在位：$rt"
else
  no "用户级运行时不在：$rt（先跑 setup-runtime.sh，再来验开箱即用）"
fi
if [ -x "$rt" ] && PYTHONPATH=/usr/lib/LumaRetouch/engine/src "$rt" -c \
     "import lumaretouch_engine.server, torch" >/dev/null 2>&1; then
  ok "运行时能 import 引擎真实链条与 torch"
else
  no "运行时 import 引擎链条失败：装机件拿它起不了引擎"
fi
# 这台机器上 torch 真正认的那一块卡——下面真窗口那一臂的设备判据就从这里来，
# 而不是在校色脚本里刻一个 "cuda"。拿错的就是假绿：M8 第一轮抓出来的就是这个形状
#（包里的 torch 是 rocm 版、卡也在，会话却建在 CPU 上，因为宿主把设备默认写死了）。
want_dev=$(PYTHONPATH=/usr/lib/LumaRetouch/engine/src "$rt" -c \
  "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')" 2>/dev/null || echo cpu)
ok "运行时里 torch 认的设备：$want_dev（会话就该建在这一块上）"

echo "── 3. 裸环境真窗口：剔除所有 LRT_* 后启动装机壳"
if [ ! -f "$fixture" ]; then
  no "校验用的照片不在：$fixture（给 LRT_CHECK_IMAGE=<路径>）"
else
  unset_args=()
  while IFS= read -r v; do unset_args+=("-u" "$v"); done < <(compgen -e | grep '^LRT_' || true)
  # 还要带上 XDG_DATA_HOME 的默认化：本机没设它（真实用户也没有），这里显式清一遍
  # 免得某个 shell 把它设成了别处，验的就不是"候选表默认那一档"。
  pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
  sleep 1
  rm -rf "$outdir"; mkdir -p "$outdir"
  env "${unset_args[@]}" -u XDG_DATA_HOME \
      DISPLAY="${DISPLAY:-:0}" XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/.mutter-Xwaylandauth.OJ5EX3}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$fixture" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=mediapipe LRT_PRECOMPUTE_CHANNEL=skin LRT_AUTO_DEFORM=0.35:0.25:0.2 \
      LRT_AUTO_BENCH=672x848:240:16.6:image_stream LRT_AUTO_RELEASE=1 LRT_AUTO_HISTORY=0.85 \
      LRT_AUTO_BG=ff0000:0.18:0.06 LRT_AUTO_EXPORT="$outdir@png@512@2@0.6" \
      /usr/bin/lumaretouch > "$log" 2>&1 &
  win=$!
  got=0
  for _ in $(seq 1 $((want_secs * 2))); do
    sleep 0.5
    # 等到 M0_RELEASE + 一个终局：M0_STATS（跑通了）或 M0_ERROR（引擎没起来/图没解）。
    # 只等 M0_STATS 的话，运行时缺包那一种会白等 200 s 然后报“没跑完”——而那种情形
    # 恰恰最该把详细报账读出来（它是“没装运行时”的用户现场）。
    if grep -aq 'M0_RELEASE' "$log" && { grep -aq 'M0_STATS' "$log" || grep -aq 'M0_ERROR' "$log"; }; then
      got=1; break
    fi
    kill -0 $win 2>/dev/null || { got=2; break; }
  done
  sleep 2
  kill $win 2>/dev/null; wait $win 2>/dev/null
  if [ "$got" != 1 ]; then
    no "真窗口没跑完（$([ "$got" = 2 ] && echo '进程提前退出' || echo "$want_secs s 内没等到 M0_RELEASE/M0_STATS")）；日志尾部："
    tail -12 "$log" | sed 's/^/      /'
  else
  ok "装机壳在裸环境里跑到了报账（日志：$log）"
  python3 - "$log" "$ver" "$want_prefix" "$outdir" "$want_dev" <<'PY'
import json, os, re, struct, sys
log, want_ver, want_prefix, outdir, want_dev = (sys.argv[1], sys.argv[2], sys.argv[3],
                                                sys.argv[4], sys.argv[5])
raw = open(log, "rb").read().decode("utf-8", "replace")
def last(tag):
    # report() 写的 JSON 冒号后没空格，而 Rust 回显时也不重排——按行尾取最后一条。
    hits = re.findall(tag + r' (\{[^\n]*\})', raw)
    return json.loads(hits[-1]) if hits else None
rel, stats = last("M0_RELEASE"), last("M0_STATS")
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
if rel is None:
    chk(False, "日志里没有 M0_RELEASE 那条汇总"); sys.exit(1)
chk(rel["engineVersion"] == want_ver,
    f"引擎自报版本 {rel['engineVersion']!r} == deb 版本 {want_ver!r}")
chk(rel["pythonSource"] == "runtime",
    f"解释器来自候选表（{rel['pythonSource']!r}），不是 env/explicit/fallback")
chk(bool(rel["python"]) and rel["python"].endswith(want_prefix),
    f"解释器就是装好的运行时：{rel['python']!r}")
chk(bool(rel["engineSrc"]) and rel["engineSrc"].startswith("/usr/lib/LumaRetouch"),
    f"引擎源码取自装机资源：{rel['engineSrc']!r}")
chk(rel["engineSrc"] and "/Qoder/" not in rel["engineSrc"], "引擎源码路径没指回仓库")
for pkg in ("numpy", "pillow", "torch", "torchvision"):
    chk(rel["pkgs"].get(pkg), f"运行时里装了 {pkg}：{rel['pkgs'].get(pkg)!r}")
caps = rel["caps"]
chk(caps["presets"] > 0, f"hello 握手生效：预设清单 {caps['presets']} 项")
chk(caps["gradeLimits"] > 0, f"hello 握手生效：grade 上限 {caps['gradeLimits']} 项")
chk(caps["exportCaps"] == 1, f"hello 握手生效：导出能力已到宿主")
chk(caps["editCmds"] >= 6, f"hello 握手生效：历史编辑名单 {caps['editCmds']} 条")
chk(rel["alive"] is True, "自检那一刻引擎进程还活着")
# 真图与帧：M0_RELEASE 是在导任何图之前报的（那里才是“引擎死/运行时缺包”也能报账的
# 位置），所以画面证据从同一次运行的 M0_IMAGE / M0_STATS 里取，不能要求前者包含它。
img = last("M0_IMAGE")
chk(bool(img) and img.get("w", 0) > 0, f"真图已解码上屏：{img and {'w': img.get('w'), 'h': img.get('h')}}")
if stats:
    chk(stats["delivered"] > 0, f"帧真到了画布：emitted {stats['emitted']} / delivered {stats['delivered']}")
    chk(stats["measured_fps"] >= 55, f"裸环境帧率 {stats['measured_fps']} ≥ 55（地板口径同 M5-a）")
else:
    chk(False, "日志里没有 M0_STATS，帧数与帧率无法判定")

# 能力上报的一致性（M8）：换底与放大两档后端清单得由引擎报进宿主。缺一项就是“装机件
# 里 UI 在猜能力”——上一版换底面板把 birefnet 当无条件下拉项就是这个形状。
# 裸环境里没权重（开头把所有 LRT_* 剔干净了），所以装机可用的抠图后端只该有 color_key。
chk(caps.get("mattingCaps") == 1, "ready 的 matting_backends 到了宿主（换底下拉项的唯一出处）")
chk(caps.get("mattingBaseline") == 1,
    f"裸环境里装机即用的抠图后端只该有 color_key：{caps.get('mattingBaseline')} 个")
chk(caps.get("upscaleBackends") == 1, "ready 的 upscale_backends 到了宿主（倍率与后端名单的出处）")

# 换底（M6）在裸环境里的六臂。每一臂都只判"错了就不能叫开箱即用"的那一句：
#   主臂——底色落到角像素；关层臂——逐字节回出厂帧；诚实拒臂——无权重 birefnet 被整条拒
#   且画面不动；重导臂——引擎清 _bg 时宿主也跟着清；重建后重开臂——第二次 set 还得成；
#   存活臂——挂着这一层跑完帧通路后它还在。上面任何一臂读不到就是不过，不“跳过”。
TOLQ = 3
def near(a, want):
    return bool(a) and len(a) == 3 and all(abs(x - w) <= TOLQ for x, w in zip(a, want))
bgm = last("M0_BG")
chk(bgm is not None and "bad" not in (bgm or {}), f"换底主臂跑成了：{bgm and bgm.get('bad')}")
if bgm and "bad" not in bgm:
    chk(bgm.get("backend") == "color_key", f"主臂后端 {bgm.get('backend')!r} 应为 color_key")
    chk(bgm.get("device") == want_dev,
        f"裸环境里会话建在 torch 认的那一块上：device={bgm.get('device')!r} 应为 {want_dev!r}")
    chk(isinstance(bgm.get("frameChanged"), int) and bgm["frameChanged"] > 0,
        f"底色进了用户看见的那一帧：frameChanged={bgm.get('frameChanged')}")
    chk(near(bgm.get("cornerAfter"), bgm.get("wantBg") or []),
        f"角像素落到底色 {bgm.get('wantBg')}：实得 {bgm.get('cornerAfter')}")
    chk(isinstance(bgm.get("fill"), float) and 0.02 < bgm["fill"] < 0.95,
        f"遮罩真分离了主体与背景：fill={bgm.get('fill')}")
clr = last("M0_BG_CLEAR")
chk(clr is not None and clr.get("frameRestoredDiff") == 0,
    f"关掉整层逐字节回出厂帧：restoredDiff={clr and clr.get('frameRestoredDiff')}")
rej = last("M0_BG_REJECT")
chk(rej is not None and rej.get("sawError") is True, "无权重 birefnet 在宿主日志里留下了诚实的拒绝")
if rej:
    chk(rej.get("frameMoved") == 0, f"被拒的一层不该动画面：frameMoved={rej.get('frameMoved')}")
    chk(rej.get("engineAlive") is True, "一次拒绝不能把引擎搞死：engine_alive")
    chk(rej.get("bgStillActive") is not True, "不得静默降级成色键：bgStillActive")
rlg = last("M0_BG_RELOAD")
chk(rlg is not None and rlg.get("hostBgCleared") is True,
    f"重导后宿主不报陈换底层：hostBgCleared={rlg and rlg.get('hostBgCleared')}")
if rlg:
    chk(rlg.get("engineBgActive") is not True, "引擎换图没清 _bg 就是旧遮罩静默带到新图上")
    chk(rlg.get("frameIsHome") == 0, f"重导同一张图逐字节等于出厂帧：frameIsHome={rlg.get('frameIsHome')}")
    chk(rlg.get("proxySame") is True, f"重导后代理档不得漂移：proxy={rlg.get('proxy')}")
rpa = last("M0_BG_REAPPLY")
chk(rpa is not None and rpa.get("active") is True, f"会话重建后重新开底还得成：{rpa and rpa.get('bad')}")
lve = last("M0_BG_LIVE")
chk(lve is not None and lve.get("active") is True and (lve.get("bytesBg") or 0) > 0,
    f"挂着换底层跑完帧通路后层还在：{lve and {'active': lve.get('active'), 'bytesBg': lve.get('bytesBg')}}")

# 面部重塑（DoD §2 的核心主张）在装机件上必须用**真检测器**跑成：权重 2.5MB 是内嵌
# 随包的，所以"裸环境里没权重"这条退路在这台机器上不存在。template 后端给的是网格
# 占位几何，引擎自己也拒它拿来做形变——拿 template 跑这一臂等于什么都没验。
df = last("M0_DEFORM")
chk(df is not None and "bad" not in df, f"形变臂跑成了：{df and df.get('bad')}")
if df and "bad" not in df:
    chk(df.get("backend") == "mediapipe",
        f"关键点是真 FaceMesh 不是模板：landmark_backend={df.get('backend')!r}")
    chk(df.get("built") is True and df.get("lit") is True,
        f"形变层真常驻且点火：built={df.get('built')} lit={df.get('lit')}")
    chk(df.get("amounts", {}).get("slim_face") == 0.35,
        f"滑块值落进引擎：{df.get('amounts')}")
    chk(isinstance(df.get("deformMs"), (int, float)) and df["deformMs"] < 60,
        f"面部重塑是毫秒级：deform_ms={df.get('deformMs')}（>60ms 就不是拖滑块那一档）")
    chk((df.get("bytesDeform") or 0) > 0, f"常驻显存里有那一层：bytes_deform={df.get('bytesDeform')}")
    pk = (df.get("peaks") or {}).get("slim_face")
    chk(isinstance(pk, (int, float)) and pk > 0, f"峰值位移非零（不是假滑块）：peak_px={pk}")
else:
    chk(False, "日志里没有 M0_DEFORM 或它报了 bad：装机件的面部重塑这一臂没跑")

# 放大（M7）在裸环境里要证的不是"图变大了"，而是三处对得上：请求的倍率、引擎报回的
# 倍率、**磁盘上那张的 IHDR**。最后一项是“导出的是满幅不是代理档”与“2× 真落盘”的唯一
# 直接证据——它不拿引擎自己的报数当唯一证人。
exp = last("M0_EXPORT")
if exp is None:
    chk(False, "日志里没有 M0_EXPORT —— 裸环境里 2× 出片那一臂没跑")
else:
    chk(exp.get("wantScale") == 2 and exp.get("gotScale") == 2,
        f"请求 2× 与引擎报回 2× 对得上：want={exp.get('wantScale')} got={exp.get('gotScale')}")
    chk(exp.get("backend") in ("lanczos3", "lanczos3_tiled"),
        f"放大后端由引擎具名报回：{exp.get('backend')!r}")
    chk(exp.get("failed") == 0, f"一批里没失败的图：failed={exp.get('failed')}/{exp.get('total')}")
    rats = exp.get("ratios") or []
    chk(bool(rats) and all(abs(r - 2.0) <= 0.001 for r in rats), f"每张的落盘/源比率都是 2：{rats}")
    chk(all(isinstance(v, (int, float)) and v > 0 for v in (exp.get("upscaleMs") or [0])),
        f"放大那一段有真计时：{exp.get('upscaleMs')}")
    chk(all(isinstance(v, (int, float)) and v > 0 for v in (exp.get("sharpenMs") or [0])),
        f"锐化排在放大后且有真计时：{exp.get('sharpenMs')}")
    files = [f for f in os.listdir(outdir) if f.lower().endswith(".png")] if os.path.isdir(outdir) else []
    chk(len(files) == 1, f"出片目录里应当只有一张（{outdir}）：{files}")
    # 逐图数据在 M0_EXPORT 里是平行的数组（full/srcs/ratios），不是一个对象数组：
    # 拿 exp["images"] 去取得个 None，然后磁盘对账整段默默跳过——那一臂看上去绿了，
    # 其实一个字没验（本仓最不能容的那种假绿）。
    fulls, srcs = exp.get("full") or [], exp.get("srcs") or []
    if not (files and fulls and srcs):
        chk(False, f"磁盘对账材料不齐：files={files} full={fulls} srcs={srcs}")
    else:
        ow, oh = (int(v) for v in str(fulls[0]).split("x"))
        sw, sh = (int(v) for v in str(srcs[0]).split("x"))
        with open(os.path.join(outdir, files[0]), "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            dw, dh = struct.unpack(">II", head[16:24])
            chk((dw, dh) == (ow, oh),
                f"磁盘尺寸 ({dw},{dh}) 与引擎报回 ({ow},{oh}) 一致")
            chk(dw == sw * 2 and dh == sh * 2,
                f"磁盘尺寸是真 2×：{sw}x{sh} → {dw}x{dh}")
            # “导出的是满幅不是代理档”的直接证据：落盘宽不等于屏上那个代理宽。
            # 代理尺寸从 M0_EXPORT.proxy（"400x504"）里拆，不是拿引擎报的另一个数当证人。
            pw = int(str(exp.get("proxy")).split("x")[0] or 0) if exp.get("proxy") else 0
            chk(pw > 0 and dw != pw, f"导出的不是代理档（代理宽 {pw}，落盘宽 {dw}）")
        else:
            chk(False, f"磁盘上那张读不到 PNG 签名：{files[0]}")
sys.exit(1 if fails else 0)
PY
  if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
  # 换底与 2× 出片的逐臂读数都在上面那段里判了；目录每轮重建，不留到下一轮
  rm -rf "$outdir"
  # 撤销/重做也必须在裸环境里绕回来（M5-b 的装机证据是另一轮专门跑的）
  if grep -aq 'M0_HISTORY' "$log"; then
    echo "  · 附带：LRT_AUTO_HISTORY 也在这轮跑了（细节见 $log）"
  fi
  fi
fi

echo "── 4. RAW 那一臂：拖进 DNG 也要即刻解码、重塑、出片"
# 上面那一臂的 jpg 证据对 DNG 没有推论力：RAW 走的是完全另一条通路（CFA → 去马赛克
# → 下采样），而“拖入 DNG 也能用”这句话只能现场量。输入用同一份夹具现场合成的
# DNG（make-test-dng.py 只是**造输入的工具**，被测的引擎仍是 /usr/lib 那一份）。
# 诚实记一笔：这台机器上没有可授权的真人照片，所以“真机人像”那一半仍未验（同
# docs/acceptance/PORTRAIT-002-盲评规程里“待补：真实人像”那一行）——这一臂验的是
# DNG 容器与真解码通路，不含真人皮肤结构。
unset_args=()
while IFS= read -r v; do unset_args+=("-u" "$v"); done < <(compgen -e | grep '^LRT_' || true)
dng=/tmp/lrt-release-$$.dng
doutdir=/tmp/lrt-release-dng.$$
# 尺寸不是我写死的：从生成器自己报的那一行取（本轮就错过一次——拿 900 当期望，
# 而夹具只有 1024 宽，裁出来是 768×600）。三个观察者对账：生成器知道自己写了什么、
# 引擎报它解出什么、磁盘上那张 PNG 的 IHDR 是最终事实。
dgen=$("$rt" "$repo/packaging/make-test-dng.py" --from "$fixture" --out "$dng" --edge 900 2>&1)
if [ ! -x "$rt" ] || [ ! -f "$dng" ]; then
  no "DNG 输入造不出来（运行时 $rt 不可用或生成器非零退出）：$dgen"
elif ! echo "$dgen" | grep -q '×'; then
  no "DNG 生成器没报出尺寸：$dgen"
else
  dsize=$(echo "$dgen" | sed -n 's/.*：\([0-9]\+×[0-9]\+\).*/\1/p' | head -1)
  dwidth=${dsize%×*}; dheight=${dsize#*×}
  dsha=$(sha256sum "$dng" | cut -c1-64)
  dlog=/tmp/m5-release-dng.$$.log
  pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
  sleep 1
  rm -rf "$doutdir"; mkdir -p "$doutdir"
  env "${unset_args[@]}" -u XDG_DATA_HOME \
      DISPLAY="${DISPLAY:-:0}" XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/.mutter-Xwaylandauth.OJ5EX3}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$dng" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=mediapipe LRT_PRECOMPUTE_CHANNEL=skin LRT_AUTO_DEFORM=0.3:0.2:0.1 \
      LRT_AUTO_BENCH=672x848:120:16.6:image_stream LRT_AUTO_RELEASE=1 \
      LRT_AUTO_EXPORT="$doutdir@png@512" \
      /usr/bin/lumaretouch > "$dlog" 2>&1 &
  dwin=$!
  dgot=0
  for _ in $(seq 1 $((want_secs * 2))); do
    sleep 0.5
    if grep -aq 'M0_RELEASE' "$dlog" && { grep -aq 'M0_EXPORT' "$dlog" || grep -aq 'M0_ERROR' "$dlog"; }; then
      dgot=1; break
    fi
    kill -0 $dwin 2>/dev/null || { dgot=2; break; }
  done
  sleep 2
  kill $dwin 2>/dev/null; wait $dwin 2>/dev/null
  if [ "$dgot" != 1 ]; then
    no "DNG 真窗口没跑完（$([ "$dgot" = 2 ] && echo '进程提前退出' || echo '超时')）；日志尾部："
    tail -10 "$dlog" | sed 's/^/      /'
    else
      ok "装机壳跑通了 DNG 那一臂（日志：$dlog，源幅 ${dwidth}×${dheight}）"
      python3 - "$dlog" "$ver" "$want_prefix" "$doutdir" "$dng" "$dsha" "$dwidth" "$dheight" <<'PY'
import hashlib, json, os, re, struct, sys
log, want_ver, want_prefix, outdir, dng, dsha, dw_s, dh_s = sys.argv[1:9]
dw_w, dh_w = int(dw_s), int(dh_s)
raw = open(log, "rb").read().decode("utf-8", "replace")
def last(tag):
    hits = re.findall(tag + r' (\{[^\n]*\})', raw)
    return json.loads(hits[-1]) if hits else None
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)

rel, img = last("M0_RELEASE"), last("M0_IMAGE")
chk(rel is not None and rel.get("engineVersion") == want_ver,
    f"DNG 那一臂跑的是装机引擎 {rel and rel.get('engineVersion')!r} == {want_ver!r}")
chk(rel is not None and (rel.get("python") or "").endswith(want_prefix),
    f"解释器仍是装好的运行时：{rel and rel.get('python')!r}")
chk(bool(img) and int(img.get("w", 0)) > 0, f"DNG 解码并上屏：{img and {'w': img.get('w'), 'h': img.get('h')}}")
# 代理档不得超过预算（“秒开”靠的是下采样而不是调小预算）
if img:
    chk(int(img.get("w", 0)) * int(img.get("h", 0)) <= 207360,
        f"代理档在预算内：{img.get('w')}×{img.get('h')}")
    sw, sh = img.get("src_w"), img.get("src_h")
    if sw and sh:
        chk((int(sw), int(sh)) == (dw_w, dh_w),
            f"源幅报回的是 DNG 的真尺寸：{(int(sw), int(sh))} 应为 {(dw_w, dh_w)}")

df = last("M0_DEFORM")
if df is None:
    chk(False, "日志里没有 M0_DEFORM：DNG 会话上形变那一臂没跑")
elif "bad" in df:
    chk(False, f"DNG 上做面部重塑被拒：{df.get('bad')}")
else:
    chk(True, "DNG 上也能做面部重塑")
if df and "bad" not in df:
    chk(df.get("backend") == "mediapipe", f"关键点是真 FaceMesh：{df.get('backend')!r}")
    chk(df.get("built") is True and df.get("lit") is True, "DNG 会话里形变层真常驻并点火")

exp = last("M0_EXPORT")
if exp is None:
    # 文案要跟着判据的方向走：上一版这里写死一句“日志里没有 M0_EXPORT”，过与不过
    # 都打同一句话——于是报告上出现“✓ 日志里没有 M0_EXPORT”这种自相矛盾的行。
    chk(False, "日志里没有 M0_EXPORT：DNG 出片那一臂没跑")
else:
    chk(True, "M0_EXPORT 在日志里：DNG 出片那一臂跑了")
    full = (exp.get("full") or [""])[0]
    m = re.fullmatch(r"(\d+)x(\d+)", full or "")
    chk(m is not None, f"引擎报回的导出尺寸形状不对（{full!r}，要 WxH）" if m is None
        else f"引擎报回导出尺寸 {full}")
    if m:
        ow, oh = int(m.group(1)), int(m.group(2))
        chk((ow, oh) == (dw_w, dh_w),
            f"DNG 直通导出的是满幅真解码：引擎报 {ow}×{oh}，期望 {dw_w}×{dh_w}")
    files = [os.path.join(outdir, f) for f in sorted(os.listdir(outdir))] if os.path.isdir(outdir) else []
    chk(bool(files), f"磁盘上真有产物：{files[:1]}")
    if files:
        with open(files[0], "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            pdw, pdh = struct.unpack(">II", head[16:24])
            chk((pdw, pdh) == (dw_w, dh_w),
                f"磁盘 IHDR ({pdw},{pdh}) 与满幅 ({dw_w},{dh_w}) 一致（不拿引擎报数当唯一证人）")
            pw = int(str(exp.get("proxy")).split("x")[0] or 0) if exp.get("proxy") else 0
            chk(pw > 0 and pdw != pw, f"导出的不是代理档（代理宽 {pw}，落盘宽 {pdw}）")
        else:
            chk(False, f"磁盘上那张读不到 PNG 签名：{files[0]}")

# 原片只读：导完一遍再算一次哈希，与导入前那一次逐字符比
now = hashlib.sha256(open(dng, "rb").read()).hexdigest()
chk(now == dsha, f"导出没动 RAW 原片：导入前后哈希同为 {now[:12]}…")
sys.exit(1 if fails else 0)
PY
      if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
      rm -rf "$doutdir" "$dng"
    fi
fi

echo
echo "── 读数：$pass 条通过，$fail 条不过"
if [ "$fail" -ne 0 ]; then
  echo "VERDICT=FAIL — 这个包还不算开箱即用"
  exit 1
fi
echo "VERDICT=PASS — 装机件在裸环境里自证通过（版本 $ver）"
