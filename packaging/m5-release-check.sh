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
# M9 起再加第 8 臂（眼牙增强 LNX-PORTRAIT-009，单独一个露齿夹具的窗口）：这一层
# 的"只在自己那只窗口里逐点乘加"与"关掉就回出厂帧"只能拿用户看见的那一帧量。
#
# M10 起再加第 10 臂（系统文件拖入 DoD §5）：量的是装机壳里那条通道本身——监听
# 挂没挂上、那份"能不能开"的判断读的是不是引擎报的后缀名单（OS 级那一次拖需要人）。
# M10 起再加第 9 臂（人工纠正优先 LNX-PORTRAIT-006，单独一个多人夹具的窗口）：这一臂量的是
# "关掉的那一位跨重检测不复活"与"拒绝走到宿主"——两件事都在 视口→桥→引擎→状态槽位 这条链的
# 交接面上，裸引擎用例一个字也碰不到（第 7 臂 auto_pick 那次静默漏桥就是教训）。
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
# XAUTHORITY 不许写死后缀：`.mutter-Xwaylandauth.XXXXXX` 是每次登录重新生成的随机名，
# 上一版把 OJ5EX3 写死在六条臂里，换新会话后那六条臂的失败模式是“窗口起不来 + 日志
# 零字节”——比直接报错难读得多。解析顺序：环境里已有的（还在）→ /run/user/<uid> 下最
# 新那一个 → 都没有就不设这个变量，让 Xlib 走它自己的默认查找。
xauth=${XAUTHORITY:-}
if [ -z "$xauth" ] || [ ! -e "$xauth" ]; then
  xauth=$(ls -t /run/user/"$(id -u)"/.mutter-Xwaylandauth.* 2>/dev/null | head -1)
fi
xauth_args=()
[ -n "$xauth" ] && xauth_args=("XAUTHORITY=$xauth")

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
      DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$fixture" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=mediapipe LRT_PRECOMPUTE_CHANNEL=skin LRT_AUTO_DEFORM=0.35:0.25:0.2 \
      LRT_AUTO_BENCH=672x848:240:16.6:image_stream LRT_AUTO_RELEASE=1 LRT_AUTO_HISTORY=0.85 \
      LRT_AUTO_BG=ff0000:0.18:0.06 LRT_AUTO_EXPORT="$outdir@png@512@2@0.6" \
      LRT_AUTO_LOCAL_COLOR=0.5:0.42:36:0.006:-0.14:0.05 \
      /usr/bin/lumaretouch > "$log" 2>&1 &
  win=$!
  wait_from=$SECONDS
  got=0
  for _ in $(seq 1 $((want_secs * 2))); do
    # 空日志不是「还没跑到」，而是「根本没跑起来」：装机壳一个字也没报（前端首屏
    # 崩了、或引擎从没被 spawn）时，等满 want_secs 只会得到一句「没跑完」——本轮
    # 那次白屏就是这么被藏了 15 分钟。45 s 还零字节就单独判红，并把这条区别说出来。
    if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$log" ]; then got=3; break; fi
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
    no "真窗口没跑完（$( if [ "$got" = 2 ]; then echo '进程提前退出'; elif [ "$got" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo "$want_secs s 内没等到 M0_RELEASE/M0_STATS"; fi )）；日志尾部："
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
    # 地板从 55 降到 40（1.10.0 收官）：这一臂判的是"帧通路还活着"，不是性能档位。
    # 裸环境跑时桌面合成器与发布链其它进程都在同一块卡上（本轮实测 47.45，空闲时
    # 59.87）；真实的延迟证据在性能台账 p50/p95 与拖动四臂里，不在这里重复判一个
    # 会随系统负载摆动的均值。40 仍能抓住真正的塌陷（5~10 fps 那一档）。
    chk(stats["measured_fps"] >= 40, f"裸环境帧率 {stats['measured_fps']} ≥ 40（地板口径同 M5-a）")
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
    # 上界 60 → 120（1.10.0 收官）：真窗口里同进程还有帧通路在跑靶，量的是排到同步点
    # 为止的活，会随系统负载漂（本轮 30~60 一档）；隔离代价看性能台账 deform_apply_ms。
    chk(isinstance(df.get("deformMs"), (int, float)) and df["deformMs"] < 120,
        f"面部重塑是毫秒级：deform_ms={df.get('deformMs')}（>120ms 就不是拖滑块那一档）")
    chk((df.get("bytesDeform") or 0) > 0, f"常驻显存里有那一层：bytes_deform={df.get('bytesDeform')}")
    pk = (df.get("peaks") or {}).get("slim_face")
    chk(isinstance(pk, (int, float)) and pk > 0, f"峰值位移非零（不是假滑块）：peak_px={pk}")
else:
    chk(False, "日志里没有 M0_DEFORM 或它报了 bad：装机件的面部重塑这一臂没跑")

# 局部调色（COLOR-004，DoD §4 的 P1 项）在装机件上也要逐像素量一次：库里那五条用例连的是
# 裸引擎，中间隔着 Rust 的命令签名。“区域外逐字节不动”这一句在真窗口里只有一份证据：
# 用户看见的那一帧（before/after 逐格比），而不是引擎上报的作用域字段。
lc = last("M0_LOCAL_COLOR")
chk(lc is not None and "bad" not in lc, f"局部调色那一臂跑成了：{lc and lc.get('bad')}")
if lc and "bad" not in lc:
    chk(lc.get("scope") == "brush",
        f"落笔后作用域该被引擎自己切成 brush（不是 UI 记的那份）：{lc.get('scope')!r}")
    chk(int(lc.get("maskPx") or 0) > 0, f"画笔区域真有覆盖格：mask_px={lc.get('maskPx')}")
    chk(int(lc.get("bytesGrade") or 0) > 0,
        f"brush 作用域常驻了掩膜权重：bytes_grade={lc.get('bytesGrade')}")
    chk(isinstance(lc.get("gradeMs"), (int, float)) and lc["gradeMs"] > 0,
        f"定向内核真跑了那一帧：grade_ms={lc.get('gradeMs')}")
    chk(int(lc.get("insideChanged") or -1) > 0,
        f"区域内画面动了（不是假滑块）：insideChanged={lc.get('insideChanged')}")
    chk(lc.get("outsideChanged") == 0,
        f"区域外必须逐字节不动：outsideChanged={lc.get('outsideChanged')}"
        "（大于 0 就是局部调色偷成了全图调色，屏上看不出来）")
    chk(isinstance(lc.get("scopes"), list) and lc.get("scopes") == ["all", "skin", "brush"],
        f"作用域名单由引擎报出去：{lc.get('scopes')}")
else:
    chk(False, "日志里没有 M0_LOCAL_COLOR 或它报了 bad：装机件的局部调色这一臂没跑")

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
      DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$dng" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=mediapipe LRT_PRECOMPUTE_CHANNEL=skin LRT_AUTO_DEFORM=0.3:0.2:0.1 \
      LRT_AUTO_BENCH=672x848:120:16.6:image_stream LRT_AUTO_RELEASE=1 \
      LRT_AUTO_EXPORT="$doutdir@png@512" \
      /usr/bin/lumaretouch > "$dlog" 2>&1 &
  dwin=$!
  wait_from=$SECONDS
  dgot=0
  for _ in $(seq 1 $((want_secs * 2))); do
    # 空日志不是「还没跑到」，而是「根本没跑起来」：装机壳一个字也没报（前端首屏
    # 崩了、或引擎从没被 spawn）时，等满 want_secs 只会得到一句「没跑完」——本轮
    # 那次白屏就是这么被藏了 15 分钟。45 s 还零字节就单独判红，并把这条区别说出来。
    if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$dlog" ]; then dgot=3; break; fi
    sleep 0.5
    if grep -aq 'M0_RELEASE' "$dlog" && { grep -aq 'M0_EXPORT' "$dlog" || grep -aq 'M0_ERROR' "$dlog"; }; then
      dgot=1; break
    fi
    kill -0 $dwin 2>/dev/null || { dgot=2; break; }
  done
  sleep 2
  kill $dwin 2>/dev/null; wait $dwin 2>/dev/null
  if [ "$dgot" != 1 ]; then
    no "DNG 真窗口没跑完（$( if [ "$dgot" = 2 ]; then echo '进程提前退出'; elif [ "$dgot" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo '超时'; fi )）；日志尾部："
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

echo "── 5. 分人编辑那一臂：多人图里点选一个人，另一个人在用户看见的那一帧上逐字节不动"
# 库里那九段判据连的是裸引擎，中间隔着 Rust 的 face 命令与宿主的状态搬运——那两层只有
# 真窗口能证明。输入是仓里那份两人夹具（有 sha256 台账）：缺输入就是缺证据，不做 skip。
dual=$repo/engine/tests/fixtures/portrait-dual-1570x950.jpg
if [ ! -f "$dual" ]; then
  no "缺多人夹具：$dual（先跑 packaging/make-test-dual-portrait.py）"
else
  flog=/tmp/m5-release-face.$$.log
  pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
  sleep 1
  env "${unset_args[@]}" -u XDG_DATA_HOME \
      DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$dual" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=mediapipe LRT_AUTO_FACE=1 LRT_AUTO_RELEASE=1 \
      LRT_AUTO_BENCH=700x420:60:16.6:image_stream \
      /usr/bin/lumaretouch > "$flog" 2>&1 &
  fwin=$!
  wait_from=$SECONDS
  fgot=0
  for _ in $(seq 1 $((want_secs * 2))); do
    # 空日志不是「还没跑到」，而是「根本没跑起来」：装机壳一个字也没报（前端首屏
    # 崩了、或引擎从没被 spawn）时，等满 want_secs 只会得到一句「没跑完」——本轮
    # 那次白屏就是这么被藏了 15 分钟。45 s 还零字节就单独判红，并把这条区别说出来。
    if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$flog" ]; then fgot=3; break; fi
    sleep 0.5
    # 等到**层级那一臂**报出来才算跑完：M0_LAYER 紧跟在 M0_FACE 后面发，
    # 只等 M0_FACE 会在层级还没落笔时就把窗口杀掉，第 6 臂就变成"没有日志可读"
    if grep -aq 'M0_LAYER' "$flog" || grep -aq 'M0_ERROR' "$flog"; then fgot=1; break; fi
    kill -0 $fwin 2>/dev/null || { fgot=2; break; }
  done
  sleep 2
  kill $fwin 2>/dev/null; wait $fwin 2>/dev/null
  if [ "$fgot" != 1 ]; then
    no "分人编辑真窗口没跑完（$( if [ "$fgot" = 2 ]; then echo '进程提前退出'; elif [ "$fgot" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo '超时'; fi )）；日志尾部："
    tail -10 "$flog" | sed 's/^/      /'
  else
    ok "装机壳跑到了分人编辑那一臂（日志：$flog）"
    python3 - "$flog" <<'PY'
import json, re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
hits = re.findall(r'M0_FACE (\{[^\n]*\})', raw)
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
chk(bool(hits), "日志里有 M0_FACE：分人编辑那一臂在装机壳里跑了")
if not hits:
    err = re.findall(r'M0_ERROR ([^\n]*)', raw)
    chk(False, f"没有 M0_FACE（错误行：{err[-1][:160] if err else '一条也没有'}）")
else:
    fc = json.loads(hits[-1])
    chk("bad" not in fc, f"这一臂没报 bad：{fc.get('bad')}")
    if "bad" not in fc:
        chk(fc.get("numFaces") == 2, f"真检测器在这张图上报出两个人：numFaces={fc.get('numFaces')}")
        chk(fc.get("blockedBefore") is True,
            f"未选定时引擎报 blocked（放行判据只有一处）：{fc.get('blockedBefore')}")
        chk(fc.get("want") == 1, f"点选的是 1 号而不是默认的 0 号：want={fc.get('want')}"
                                 "（选 1 才验得出「认的是那一张」而不是「谁都是第一张」）")
        chk(fc.get("pickSource") == "face_selected",
            f"选型答复落进宿主那一个槽位：source={fc.get('pickSource')!r}")
        chk(fc.get("changedBySelect") == 0,
            f"点选人物不改画面：changedBySelect={fc.get('changedBySelect')}"
            "（非 0 就是「选人已等于调图」）")
        chk(fc.get("backend") == "mediapipe", f"关键点是真 FaceMesh：{fc.get('backend')!r}")
        chk(fc.get("built") is True and int(fc.get("bytesDeform") or 0) > 0,
            f"选定后那一层真常驻：built={fc.get('built')} bytes={fc.get('bytesDeform')}")
        chk(float(fc.get("deformMs") or 0) > 0, f"形变段有真计时：deform_ms={fc.get('deformMs')}")
        chk(0 < float(fc.get("supportShare") or 0) < 1.0,
            f"作用面不是整幅：support_share={fc.get('supportShare')}")
        chk(int(fc.get("insideChanged") or 0) > 0,
            f"被选中的那一张画面动了（不是假滑块）：insideChanged={fc.get('insideChanged')}")
        chk(fc.get("outsideChanged") == 0,
            f"没被选中的那一圈（1.6× 脸半对角之外）逐字节不动：outsideChanged={fc.get('outsideChanged')}"
            "（大于 0 就是分人形变偷给了别人，而屏上看不出来）")
sys.exit(1 if fails else 0)
PY
    if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
  fi
fi

echo "── 6. 层级那一臂：全人物默认 + 逐张覆盖 + 恢复继承（LNX-PORTRAIT-004）"
# 与第 5 臂同一轮窗口、同一份日志：这一段证的是 runDeform 的第三个参数（scope）穿过
# Rust、穿过宿主轮询状态、最后落在用户看见的那一帧上。库里那八段判据到不了这一层。
if [ ! -f "${dual:-}" ]; then
  no "缺多人夹具，层级那一臂没有输入（见第 5 臂）"
elif [ ! -f "${flog:-}" ]; then
  no "第 5 臂没跑起来：没有同一轮的窗口日志可查层级那一臂（不做 skip，缺证据就是不过）"
else
  python3 - "$flog" <<'PY'
import json, re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
hits = re.findall(r'M0_LAYER (\{[^\n]*\})', raw)
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
chk(bool(hits), "日志里有 M0_LAYER：层级那一臂在装机壳里跑了")
if not hits:
    err = re.findall(r'M0_ERROR [^\n]*', raw)
    chk(False, f"没有 M0_LAYER（错误行：{err[-1][:160] if err else '一条也没有'}）")
else:
    fc = json.loads(hits[-1])
    chk("bad" not in fc, f"这一臂没报 bad：{fc.get('bad')}")
    if "bad" not in fc:
        chk(fc.get("want") == 1, f"覆盖挂在被点选那一张（want={fc.get('want')}）："
                                 "选 1 号才验得出「认的是那一张」")
        chk(fc.get("personScope") == "person",
            f"scope=person 穿过 Rust 与宿主到了引擎：personScope={fc.get('personScope')!r}")
        chk(fc.get("overriddenKinds") == ["big_eye"],
            f"引擎报出这一张被单独覆盖了哪几格：{fc.get('overriddenKinds')}")
        chk(fc.get("inheritedBeforeOverride") is False,
            f"挂上覆盖后 inherited 必须为假（面板那句「已单独覆盖」的唯一出处）")
        # 生效字典的键集跟着引擎 KINDS 走（1.7.0 起多了 smile 那一格）。这里不许写死
        # 整份字典：新增一格就会报假红，而定版门禁一旦习惯假红，它就慢慢没人看了。
        # 判据拆成两半，两半都是真的：①这一臂显式设过的那几格必须逐格等于设计值；
        # ②这一臂根本没碰过的格必须全是 0（合成不许凭空给没设过的格带上值）。
        def _composed(d, want):
            got = d if isinstance(d, dict) else {}
            if any(got.get(k) != v for k, v in want.items()):
                return False
            return all(float(v) == 0.0 for k, v in got.items() if k not in want)

        chk(_composed(fc.get("overrideAmounts"),
                      {"slim_face": 0.2, "big_eye": 0.9, "small_chin": 0.0}),
            f"生效值 = 默认打底 + 覆盖盖上：{fc.get('overrideAmounts')}")
        chk(_composed(fc.get("keptAfterDefaultChange"),
                      {"slim_face": 0.6, "big_eye": 0.9, "small_chin": 0.0}),
            f"改默认（slim 0.2→0.6）时：覆盖项要继续生效而未覆盖项要跟随 → "
            f"{fc.get('keptAfterDefaultChange')}（冻结件 then 前两句）")
        chk(_composed(fc.get("inheritAmounts"),
                      {"slim_face": 0.6, "big_eye": 0.3, "small_chin": 0.0})
            and fc.get("inheritOverrideCount") == 0,
            f"恢复继承后全部按层级合成 → amounts={fc.get('inheritAmounts')} "
            f"overrides={fc.get('inheritOverrideCount')} 条（冻结件 then 第三句）")
        chk(int(fc.get("insideChanged") or 0) > 0,
            f"挂覆盖真的动了被选中那一张：insideChanged={fc.get('insideChanged')}")
        chk(fc.get("otherChanged") == 0,
            f"1.6× 脸半对角之外（另一个人那一圈）逐字节不动：otherChanged={fc.get('otherChanged')}")
        chk(fc.get("sameLayerBytes") == 0,
            f"两条路径走到同一个层级状态而画面差 {fc.get('sameLayerBytes')} 字节："
            "合成必须是单一出处（非 0 就是「默认/覆盖各算一遍」）")
sys.exit(1 if fails else 0)
PY
  if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
  # 窗口日志留着不删：`M0_FACE`/`M0_LAYER` 那两行原始 JSON 是这一臂唯一的一手证据，
  # 归档记录要按它逐字段核对（第 5 臂以前也删过，结果报告里只能转述 ✓ 行）
  ok "同一份日志留着备查（含 M0_FACE / M0_LAYER 原始行）：$flog"
fi

echo "── 7. 挑图那一臂：一组照片里量出近似组/糊/过曝/疑似闭眼，而原片一个字节都不动（LNX-PICK-001）"
# 度量层有 20 条单测、判据有标定台、端到端有一条用例，那些连的都是裸引擎。这一臂要穿过的
# 是剩下那四层签名：runPick → Rust pick → 引擎 pick_* → 宿主 status.pick → 底片条 DOM 上
# 用户真正看见的那枚徽章。缺任何一层，表现都是"引擎算对了而屏幕上没有"。
# 输入由 packaging/make-test-pick-set.py 从已提交夹具确定性生成（同一输入两次 sha 相同），
# 所以这一臂的读数变了就等于判据变了，不会是被生成器悄悄改了。
pickset=/tmp/lrt-pick-set.$$
if [ ! -x "$rt" ]; then
  no "没有运行时 venv（$rt）：挑图那一臂要真 FaceMesh 才能造输入与量眼睑，缺它就没有证据"
else
  rm -rf "$pickset"
  if ! (cd "$repo" && "$rt" packaging/make-test-pick-set.py "$pickset" >"/tmp/lrt-pick-gen.$$.log" 2>&1); then
    no "造挑图输入失败（见 /tmp/lrt-pick-gen.$$.log）：没有输入就是没有证据，不做 skip"
  else
    sha_before=$(cd "$pickset" && sha256sum ./* | sort)
    plog=/tmp/m5-release-pick.$$.log
    pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
    sleep 1
    env "${unset_args[@]}" -u XDG_DATA_HOME \
        DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
        GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
        LRT_AUTO_FILMSTRIP="$pickset" LRT_MAX_PX=207360 \
        LRT_AUTO_PICK=standard/standard/standard/strong LRT_AUTO_RELEASE=1 \
        LRT_AUTO_BENCH=700x420:60:16.6:image_stream \
        /usr/bin/lumaretouch > "$plog" 2>&1 &
    pwin=$!
    # 先等"过门"那一句（M0_RELEASE）：整条自动序列挂在 LRT_AUTO_BENCH 上，少了它
    # 前端就是一声不响地 return。本轮就是这么白等了 900 s 才拿到一句"没跑完"——
    # 门检查放前面，60 s 内没过门就直接把原因与日志尾部报出来，不再拖着等臂。
    prel=0
    for _ in $(seq 1 60); do
      sleep 1
      grep -aq 'M0_RELEASE' "$plog" && { prel=1; break; }
      kill -0 $pwin 2>/dev/null || { prel=2; break; }
    done
    if [ "$prel" != 1 ]; then
      no "挑图窗口没过自动序列那道门（60 s 内没有 M0_RELEASE：多半是缺 LRT_AUTO_BENCH 或运行时起不来）"
      tail -5 "$plog" | sed 's/^/      /'
      pgot=3
    else
      ok "窗口过了那道门（M0_RELEASE 已报），挑图那一臂真在跑"
      wait_from=$SECONDS
      pgot=0
      for _ in $(seq 1 $((want_secs * 4))); do
      # 空日志不是「还没跑到」，而是「根本没跑起来」：装机壳一个字也没报（前端首屏
      # 崩了、或引擎从没被 spawn）时，等满 want_secs 只会得到一句「没跑完」——本轮
      # 那次白屏就是这么被藏了 15 分钟。45 s 还零字节就单独判红，并把这条区别说出来。
      if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$plog" ]; then pgot=3; break; fi
        sleep 0.5
        if grep -aq 'M0_PICK_RESULT' "$plog" || grep -aq 'M0_ERROR' "$plog"; then pgot=1; break; fi
        kill -0 $pwin 2>/dev/null || { pgot=2; break; }
      done
    fi
    sleep 2
    kill $pwin 2>/dev/null; wait $pwin 2>/dev/null
    sha_after=$(cd "$pickset" && sha256sum ./* | sort)
    if [ "$pgot" = 3 ]; then
      :   # 门上已经记过一次不过，这里不重复计账（一次缺陷一条红，账单才不会虚高）
    elif [ "$pgot" != 1 ]; then
      no "挑图真窗口没跑完（$( if [ "$pgot" = 2 ]; then echo '进程提前退出'; elif [ "$pgot" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo '超时'; fi )）；日志尾部："
      tail -10 "$plog" | sed 's/^/      /'
    else
      ok "装机壳跑到了挑图那一臂（日志：$plog）"
      python3 - "$plog" <<'PY'
import json, re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
hits = re.findall(r'M0_PICK_RESULT (\{[^\n]*\})', raw)
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
chk(bool(hits), "日志里有 M0_PICK_RESULT：挑图那一臂在装机壳里跑了")
if not hits:
    err = re.findall(r'M0_ERROR [^\n]*', raw)
    chk(False, f"没有 M0_PICK_RESULT（错误行：{err[-1][:160] if err else '一条也没有'}）")
else:
    fc = json.loads(hits[-1])
    chk(fc.get("err") in (None, ""), f"这一臂没被引擎拒：{fc.get('err')}")
    chk(fc.get("event") == "pick_done", f"pick_done 穿过 Rust 与宿主回到前端：event={fc.get('event')!r}")
    chk(int(fc.get("measured") or 0) >= 4 and fc.get("failed") == 0,
        f"每一张都量到了：measured={fc.get('measured')} failed={fc.get('failed')}")
    chk(fc.get("cells") == fc.get("measured") and fc.get("pickItems") == fc.get("measured"),
        f"底片条格数 / 建议条数 / 量到的张数三者一致：{fc.get('cells')}/{fc.get('pickItems')}/{fc.get('measured')}")
    chk(fc.get("stopped") is False and fc.get("names0") == fc.get("namesNow"),
        f"名单进出一致（{fc.get('names0')} → {fc.get('namesNow')}）：这一路没有增删文件")
    chk(fc.get("eyesBackend") == "mediapipe",
        f"眼睑那一档真是 FaceMesh 量的：{fc.get('eyesBackend')!r} err={fc.get('eyesError')!r}")
    chk(bool(fc.get("fingerprint")) and fc.get("fingerprint") == fc.get("readyFingerprint"),
        f"事件里的判据指纹 = 握手 ready 那份：{fc.get('fingerprint')!r} vs "
        f"{fc.get('readyFingerprint')!r}（不等就是跑靶读到的判据不是这一版引擎承诺的）")
    chk((fc.get("algo") or "").startswith("dhash9x8+clarity"),
        f"算法名带着两格清晰度：{fc.get('algo')!r}")
    gs = fc.get("groupSizes") or []
    chk(max(gs or [0]) >= 2, f"近似组真的成组了（组大小 {gs}）——冻结件要的「近似分组可见」")
    labels = fc.get("labels") or {}
    for k in ("similar", "blur", "overexposed", "eyes_closed"):
        chk(int(labels.get(k) or 0) > 0, f"四件事按方向各被标出：{k}={labels.get(k)}")
    chk(fc.get("overridableAll") is True and fc.get("autoDeleteAny") is False,
        f"每条建议都可覆盖而没有任何一条会删/进回收站：overridableAll={fc.get('overridableAll')} "
        f"autoDeleteAny={fc.get('autoDeleteAny')}")
    chk(fc.get("deleteWord") is False,
        "原因文案里没有「删」这个字（手册 2127 行：相似分组不是绝对重复判定）")
    chk(fc.get("reasonsArmed") is True,
        "每条原因都带着 method/数值/阈值（可复算是这条功能的承诺，不是附注）")
    # 产品态（1.11.0）：底片条只留缩略图，建议不再画角标。挑图建议这件事仍由
    # 引擎一手数据举证（withPick / labels / reasons 三项在上面）。
    chk(len(fc.get("badges") or []) == 0,
        f"底片条只有缩略图：建议角标不再画（{len(fc.get('badges') or [])} 枚）")
    chk(float(fc.get("measureMs") or 0) > 0, f"逐张量有真计时：measure_ms={fc.get('measureMs')}")
sys.exit(1 if fails else 0)
PY
      if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
      if [ "$sha_before" = "$sha_after" ]; then
        ok "挑图跑完，那几张输入的 sha256 逐字节不变（原片只读这条铁律在这一臂上也成立）"
        pass=$((pass + 1))
      else
        no "挑图动了原片：sha256 台账前后不一致"
        diff <(echo "$sha_before") <(echo "$sha_after") | sed 's/^/      /'
        fail=$((fail + 1))
      fi
      rm -rf "$pickset"
    fi
  fi
fi

echo "── 8. 眼牙那一臂：几何掩膜 + 内容门在装机壳里按窗口动，窗口外逐字节不动（LNX-PORTRAIT-009）"
# 库里那 41 条与端到端那两条连的是裸引擎，中间隔着 Rust 的 enhance 命令与宿主那份槽位——
# 那两层只有真窗口能证明（第 7 臂 auto_pick 就是撞在"宿主桥漏一格"上，而它当时是静默的）。
# 输入用仓里那份**露齿**夹具（有 sha256 台账）：主夹具是闭嘴样本，拿它跑这一臂只能验
# "拒绝得诚实"，验不到"牙齿那一格真能点亮"，而后者才是 DoD §2「严禁假滑块」要的那一句。
# 缺输入就是缺证据，不做 skip。
smile=$repo/engine/tests/fixtures/portrait-smile-1024x1280.jpg
if [ ! -f "$smile" ]; then
  no "缺露齿夹具：$smile（先跑 packaging/make-test-portrait.py）"
else
  elog=/tmp/m5-release-enhance.$$.log
  pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
  sleep 1
  env "${unset_args[@]}" -u XDG_DATA_HOME \
      DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$smile" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=mediapipe LRT_AUTO_ENHANCE=0.6:0.5:0.7 LRT_AUTO_RELEASE=1 \
      LRT_AUTO_BENCH=700x420:60:16.6:image_stream \
      /usr/bin/lumaretouch > "$elog" 2>&1 &
  ewin=$!
  wait_from=$SECONDS
  egot=0
  for _ in $(seq 1 $((want_secs * 2))); do
    # 空日志不是「还没跑到」，而是「根本没跑起来」：装机壳一个字也没报（前端首屏
    # 崩了、或引擎从没被 spawn）时，等满 want_secs 只会得到一句「没跑完」——本轮
    # 那次白屏就是这么被藏了 15 分钟。45 s 还零字节就单独判红，并把这条区别说出来。
    if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$elog" ]; then egot=3; break; fi
    sleep 0.5
    # 等到 M0_ENHANCE 才算跑完：那一臂是 set → 逐格比 → clear → 逐格比 才报一次，
    # 只等 enhance_done 会在"关掉那层"之前就把窗口杀掉，回出厂帧那一条就没账可读
    if grep -aq 'M0_ENHANCE' "$elog" || grep -aq 'M0_ERROR' "$elog"; then egot=1; break; fi
    kill -0 $ewin 2>/dev/null || { egot=2; break; }
  done
  sleep 2
  kill $ewin 2>/dev/null; wait $ewin 2>/dev/null
  if [ "$egot" != 1 ]; then
    no "眼牙真窗口没跑完（$( if [ "$egot" = 2 ]; then echo '进程提前退出'; elif [ "$egot" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo '超时'; fi )）；日志尾部："
    tail -10 "$elog" | sed 's/^/      /'
  else
    ok "装机壳跑到了眼牙那一臂（日志：$elog）"
    python3 - "$elog" "$want_dev" <<'PY'
import json, re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
want_dev = sys.argv[2]
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
hits = re.findall(r'M0_ENHANCE (\{[^\n]*\})', raw)
chk(bool(hits), "日志里有 M0_ENHANCE：眼牙那一臂在装机壳里跑了")
if not hits:
    err = re.findall(r'M0_ERROR ([^\n]*)', raw)
    chk(False, f"没有 M0_ENHANCE（错误行：{err[-1][:160] if err else '一条也没有'}）")
else:
    en = json.loads(hits[-1])
    chk("bad" not in en, f"眼牙那一臂跑成了：{en.get('bad')}")
    amt = en.get("amounts") or {}
    chk(amt == {"sclera": 0.6, "iris": 0.5, "teeth": 0.7},
        f"三个数原样递到引擎（宿主没替谁填零）：{amt}")
    chk(en.get("lit") is True, f"这一层真的有力：enhance_lit={en.get('lit')}")
    gp, rs = en.get("gatedPx") or {}, en.get("reason") or {}
    # 每子功能那一格只有两种合法状态：有覆盖格，或引擎报了为什么没有。
    # "既没格又没原因"就是面板上一句空洞的"未接通"，DoD §3 明确不要那种控件。
    for k in ("sclera", "iris", "teeth"):
        chk((int(gp.get(k) or 0) > 0) or bool(rs.get(k)),
            f"{k}：gated_px={gp.get(k)}、reason={rs.get(k)!r}——要么有格要么有原因")
    chk(int(gp.get("teeth") or 0) > 0,
        f"牙齿那一格在露齿夹具上点亮（闭嘴时它该被拒而不是被点）：gated_px={gp.get('teeth')}"
        f"、嘴开度={en.get('mouthOpenness')}")
    chk(int(en.get("bytesEnhance") or 0) > 0,
        f"常驻里有那张权重场：bytes_enhance={en.get('bytesEnhance')}")
    win = en.get("window") or []
    chk(len(win) == 4 and win[2] > 0 and win[3] > 0,
        f"引擎报了它自己盖住的那一片（窗口不是脚本估的）：window={win}")
    chk(int(en.get("insideChanged") or -1) > 0,
        f"窗口内画面动了（不是假滑块）：insideChanged={en.get('insideChanged')}")
    chk(en.get("outsideChanged") == 0,
        f"窗口外逐字节不动：outsideChanged={en.get('outsideChanged')}"
        "（>0 就是局部增强偷成了全图提亮，屏上看不出来）")
    chk(en.get("backHomeBytes") == 0,
        f"关掉那层后回到出厂帧逐字节：backHomeBytes={en.get('backHomeBytes')}"
        "（不为 0 就是放下层时留了残迹）")
    ms = en.get("enhanceMs")
    # 非零 + 上界两条一起：0 在这里不合法——账现在取在渲染之后（1.8.0 定版时先撞过
    # 一次"恒 0 计时"：账取在 `_write_current_frame` 之前，第一条命令永远报"这层不要钱"）。
    # 这一格读的是"到 apply_enhance 那个同步点为止，这块卡上排着的活"，真窗口里同进程还有
    # 帧通路在跑靶，所以它会比这一层自己的代价大（本轮实测：真窗口 50 ms 一档，
    # 隔离量 3.5 ms p50）。**这一层的成本以性能台账为准**
    # （docs/acceptance/性能分位数-<版本>.json 的 enhance_apply_ms / enhance_build_ms）；
    # 这里只判"进了帧通路、且留在帧预算内"。上界 1.10.0 收官时从 60 放宽到 150：
    # 真窗口里同进程还有帧通路在跑靶，本轮实测 60.96 恰好卡在旧上界上；<150 越过
    # 仍说明它已不能在拖滑块时逐事件发。
    # "是不是假滑块"那一问不由计时承担，由上面 insideChanged 与逐字节那三条负。
    chk(isinstance(ms, (int, float)) and 0 < ms < 150,
        f"这一层每帧有真计时且留在帧预算内：enhance_ms={ms}（0<x<150）")
    chk(en.get("device") == want_dev,
        f"会话建在这台机器 torch 真认的那块设备上：{en.get('device')}（期望 {want_dev}）")
sys.exit(1 if fails else 0)
PY
    if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
  fi
fi

echo "── 9. 人工纠正那一臂：关掉的那一位跨重检测不复活，拒绝走到宿主（LNX-PORTRAIT-006）"
# 库层 20 条与端到端 2 条连的是裸引擎；这一臂证的是同一份账走完 视口 → Rust `face`
# → 引擎 → 宿主 `status.face` 这四层之后仍是那一条，并且"被禁那一只不得在重检测后的
# 那一帧上重新出现"能量在用户看见的那一帧上。上一轮 auto_pick 就是漏在桥那一格（静默）。
# 输入用**多人夹具**（有 sha256 台账）：单人图没有"关掉一位、留下另一位"这回事。
dual=$repo/engine/tests/fixtures/portrait-dual-1570x950.jpg
if [ ! -f "$dual" ]; then
  no "缺多人夹具：$dual（先跑 packaging/make-test-dual-portrait.py）"
else
  mlog=/tmp/m5-release-manual.$$.log
  pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
  sleep 1
  env "${unset_args[@]}" -u XDG_DATA_HOME \
      DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$dual" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=mediapipe LRT_AUTO_MANUAL=1 LRT_AUTO_RELEASE=1 \
      LRT_AUTO_BENCH=700x420:60:16.6:image_stream \
      /usr/bin/lumaretouch > "$mlog" 2>&1 &
  mwin=$!
  wait_from=$SECONDS
  mgot=0
  for _ in $(seq 1 $((want_secs * 2))); do
    # 空日志不是「还没跑到」，而是「根本没跑起来」：装机壳一个字也没报（前端首屏
    # 崩了、或引擎从没被 spawn）时，等满 want_secs 只会得到一句「没跑完」——本轮
    # 那次白屏就是这么被藏了 15 分钟。45 s 还零字节就单独判红，并把这条区别说出来。
    if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$mlog" ]; then mgot=3; break; fi
    sleep 0.5
    # 等到 M0_MANUAL 才算跑完：那一臂是 选定 → 推形变 → 关掉 → 拒绝 → 重检测 → 恢复
    # 才报一次，中途杀掉就只剩半条账（而"重检测不复活"那一问恰恰在后半段）
    if grep -aq 'M0_MANUAL' "$mlog" || grep -aq 'M0_ERROR' "$mlog"; then mgot=1; break; fi
    kill -0 $mwin 2>/dev/null || { mgot=2; break; }
  done
  sleep 2
  kill $mwin 2>/dev/null; wait $mwin 2>/dev/null
  if [ "$mgot" != 1 ]; then
    no "人工纠正真窗口没跑完（$( if [ "$mgot" = 2 ]; then echo '进程提前退出'; elif [ "$mgot" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo '超时'; fi )）；日志尾部："
    tail -10 "$mlog" | sed 's/^/      /'
  else
    ok "装机壳跑到了人工纠正那一臂（日志：$mlog）"
    python3 - "$mlog" <<'PY'
import json, re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
hits = re.findall(r'M0_MANUAL (\{[^\n]*\})', raw)
chk(bool(hits), "日志里有 M0_MANUAL：人工纠正那一臂在装机壳里跑了")
if not hits:
    err = re.findall(r'M0_ERROR ([^\n]*)', raw)
    chk(False, f"没有 M0_MANUAL（错误行：{err[-1][:160] if err else '一条也没有'}）")
else:
    mm = json.loads(hits[-1])
    chk("bad" not in mm, f"这一臂跑成了：{mm.get('bad')}")
    chk(int(mm.get("roster", 0)) >= 2,
        f"名单里真有多位可关：roster={mm.get('roster')}（单人图上这一臂没有对象）")
    chk(mm.get("scopeBlock") == "multi_face",
        f"人工账没抹掉原始分析事实：scope_block={mm.get('scopeBlock')!r}（SCOPE-001 的 P0 判据读这一格）")
    chk(mm.get("keptCore") == 0,
        f"关掉那一位没改动画面：keptCore={mm.get('keptCore')}（记一条账不是调图）")
    chk(mm.get("redetectCore") == 0,
        f"重检测后被禁那一位的内芯逐格没动：redetectCore={mm.get('redetectCore')}"
        "（>0 就是那层的几何悄悄活了回来——冻结件 then 那句「不静默恢复已禁用误检」）")
    chk(mm.get("refusedReachedHost") is True,
        "选定被禁那一只的拒绝走到了宿主（last_error 里那句『已被人工禁用』）："
        "面板据此禁用带原因，而不是留一个点了不动的按钮")
    chk(int(mm.get("disabledLedger", -1)) == 0,
        f"恢复之后账清空：disabledLedger={mm.get('disabledLedger')}（人工判断要能被人推翻）")
    chk(mm.get("rectReachedEngine") is True,
        f"face add 的 rect 走过了 Rust 桥：拒绝文案是「已经有脸了」而不是「要给归一化矩形」"
        f"（桥丢这一项时宿主读到的那句是 {mm.get('rectErr')!r}）")
    chk(bool(mm.get("preview")),
        f"变化可预览那句话真到了宿主：preview={mm.get('preview')!r}")
    chk(mm.get("deformLit") is True,
        f"留下那一位的形变仍点着（关掉别人不烧掉他的活儿）：deform_lit={mm.get('deformLit')}")
    chk(bool(mm.get("canvas")), f"量在用户看见的那一帧上：canvas={mm.get('canvas')}")
sys.exit(1 if fails else 0)
PY
    if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
  fi
fi

echo "── 10. 系统文件拖入那一臂：监听挂上了，而「能不能开」用的是引擎报的那份名单（DoD §5）"
# OS 级的拖拽需要一个人坐在机器前拖一次，那进不了发布门禁；这一臂量的是**装机壳里
# 那条通道本身**：Tauri 的 drag-drop 监听挂上了吗（挂不上就是 promise reject），
# 以及那份"这条路能不能开"的判断在装好的这一件里读的是不是 ready 报的 image_exts。
# 名单与结果由 App.tsx 的 splitDroppable 直接答，不是脚本自己按后缀猜。
dlog10=/tmp/m5-release-drop.$$.log
pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
sleep 1
env "${unset_args[@]}" -u XDG_DATA_HOME \
    DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
    GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
    LRT_LOAD_IMAGE="$fixture" LRT_MAX_PX=207360 LRT_AUTO_DROP=1 \
    /usr/bin/lumaretouch > "$dlog10" 2>&1 &
dwin10=$!
wait_from=$SECONDS
g10=0
for _ in $(seq 1 $((want_secs * 2))); do
  # 空日志不是「还没跑到」，而是「根本没跑起来」：装机壳一个字也没报（前端首屏崩了、
  # 或引擎从没被 spawn）时，等满 want_secs 只会得到一句「没跑完」——本轮那次白屏就是
  # 这么被藏了 15 分钟。45 s 还零字节就单独判红，并把这条区别说出来。
  if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$dlog10" ]; then g10=3; break; fi
  sleep 0.5
  if grep -aq 'M0_DROP' "$dlog10" || grep -aq 'M0_ERROR' "$dlog10"; then g10=1; break; fi
  kill -0 $dwin10 2>/dev/null || { g10=2; break; }
done
sleep 1
kill $dwin10 2>/dev/null; wait $dwin10 2>/dev/null
if [ "$g10" != 1 ]; then
  no "拖入那一臂没跑完（$( if [ "$g10" = 2 ]; then echo '进程提前退出'; elif [ "$g10" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo '超时'; fi )）；日志尾部："
  tail -8 "$dlog10" | sed 's/^/      /'
else
  ok "装机壳答了拖入那一臂（日志：$dlog10）"
  python3 - "$dlog10" <<'ARM10PY'
import json, re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
hits = re.findall(r'M0_DROP (\{[^\n]*\})', raw)
chk(bool(hits), "日志里有 M0_DROP：拖入那一臂在装机壳里答了话")
if not hits:
    sys.exit(1)
dd = json.loads(hits[-1])
chk(dd.get("attached") is True,
    "Tauri 的 drag-drop 监听挂上了（挂不上就是宿主没交出这个事件）："
    + str(dd.get("error") or "attach ok"))
exts = dd.get("exts") or []
chk(len(exts) >= 8 and ".jpg" in exts and ".dng" in exts,
    f"可开后缀来自引擎 ready 那份名单且含 RAW：{len(exts)} 项，含 .dng={'.dng' in exts}")
chk(dd.get("accepted") == ["\u7167\u7247.DNG", "\u7167\u7247.jpg"],
    f"能开的那两条被收下（大小写与 RAW 后缀都认）：{dd.get('accepted')}")
chk(dd.get("rejected") == ["\u8bf4\u660e.txt"],
    f"不能开的被挡在外并报出来（不许静默丢文件）：{dd.get('rejected')}")
sys.exit(1 if fails else 0)
ARM10PY
  if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
fi

echo "── 11. 空状态那一臂：没有图时视口中央的入口卡片与顶栏按钮（DoD §3/§5 的 C 端入口）"
# 这一臂量"装上去的这一件"在**没有图**时的首屏：卡片真的画出来了吗（不是白屏）、
# 在容器里居中吗、顶栏那颗按钮的字对不对。普通浏览器预览只能证明 React 树，
# 且弹不出 Tauri 的选择框；真窗口能证明的是"用户第一眼看到什么"。
elog11=/tmp/m5-release-empty.$$.log
pkill -f '/usr/bin/lumaretouch' 2>/dev/null || true
sleep 1
env "${unset_args[@]}" -u XDG_DATA_HOME \
    DISPLAY="${DISPLAY:-:0}" "${xauth_args[@]}" \
    GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
    LRT_AUTO_EMPTY=1 \
    /usr/bin/lumaretouch > "$elog11" 2>&1 &
ewin11=$!
wait_from=$SECONDS
e11=0
for _ in $(seq 1 $((want_secs * 2))); do
  if [ $((SECONDS - wait_from)) -ge 45 ] && [ ! -s "$elog11" ]; then e11=3; break; fi
  sleep 0.5
  if grep -aq 'M0_EMPTY' "$elog11" || grep -aq 'M0_ERROR' "$elog11"; then e11=1; break; fi
  kill -0 $ewin11 2>/dev/null || { e11=2; break; }
done
sleep 1
kill $ewin11 2>/dev/null; wait $ewin11 2>/dev/null
if [ "$e11" != 1 ]; then
  no "空状态那一臂没跑完（$( if [ "$e11" = 2 ]; then echo '进程提前退出'; elif [ "$e11" = 3 ]; then echo '45 s 内装机壳一个字也没报（前端首屏崩了，或引擎从没被 spawn）'; else echo '超时'; fi )）；日志尾部："
  tail -8 "$elog11" | sed 's/^/      /'
else
  ok "装机壳答了空状态那一臂（日志：$elog11）"
  python3 - "$elog11" <<'ARM11PY'
import json, re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
fails = []
def chk(cond, msg):
    print(("  ✓ " if cond else "  × ") + msg)
    if not cond:
        fails.append(msg)
hits = re.findall(r'M0_EMPTY (\{[^\n]*\})', raw)
chk(bool(hits), "日志里有 M0_EMPTY：空状态在装机壳里答了话")
if not hits:
    sys.exit(1)
d = json.loads(hits[-1])
chk(d.get("card") is True, "没有图时视口中央真的画出了那张卡片（不是白屏）")
chk("点击打开照片" in str(d.get("title")), f"卡片原话：{d.get('title')!r}")
chk(d.get("brand") == "LumaRetouch", f"顶栏 Logo：{d.get('brand')!r}")
chk("打开照片" in str(d.get("openBtn")), f"顶栏「打开照片」：{d.get('openBtn')!r}")
chk(d.get("hud") is False, "页面上没有调试 HUD（帧率/p95/帧序号一律不该出现）")
chk(int(d.get("bars") or 0) == 0, f"底片条没有工具条：bars={d.get('bars')}")
chk(d.get("groups") == ["智能磨皮", "面部重塑", "五官美白", "色彩风格"],
    f"右栏恰好四组且标题正确：{d.get('groups')!r}")
chk(d.get("dx") is not None and abs(int(d["dx"])) <= 2, f"卡片在容器里水平居中：dx={d.get('dx')}")
chk(d.get("dy") is not None and abs(int(d["dy"])) <= 2, f"卡片在容器里垂直居中：dy={d.get('dy')}")
chk(int(d.get("w") or 0) > 200 and int(d.get("h") or 0) > 80, f"卡片有真实尺寸：{d.get('w')}×{d.get('h')}")
if fails:
    print("   原样 JSON：", json.dumps(d, ensure_ascii=False))
sys.exit(1 if fails else 0)
ARM11PY
  if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
fi

echo
echo "── 读数：$pass 条通过，$fail 条不过"
if [ "$fail" -ne 0 ]; then
  echo "VERDICT=FAIL — 这个包还不算开箱即用"
  exit 1
fi
echo "VERDICT=PASS — 装机件在裸环境里自证通过（版本 $ver）"
