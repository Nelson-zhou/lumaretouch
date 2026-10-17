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
  env "${unset_args[@]}" -u XDG_DATA_HOME \
      DISPLAY="${DISPLAY:-:0}" XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/.mutter-Xwaylandauth.OJ5EX3}" \
      GDK_BACKEND=x11 HOME="$HOME" USER="$USER" PATH="$PATH" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
      LRT_LOAD_IMAGE="$fixture" LRT_MAX_PX=207360 \
      LRT_PRECOMPUTE=template LRT_PRECOMPUTE_CHANNEL=skin \
      LRT_AUTO_BENCH=672x848:240:16.6:image_stream LRT_AUTO_RELEASE=1 LRT_AUTO_HISTORY=0.85 \
      /usr/bin/lumaretouch > "$log" 2>&1 &
  win=$!
  got=0
  for _ in $(seq 1 400); do
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
    no "真窗口没跑完（$([ "$got" = 2 ] && echo '进程提前退出' || echo '300 s 内没等到 M0_RELEASE/M0_STATS')）；日志尾部："
    tail -12 "$log" | sed 's/^/      /'
  else
  ok "装机壳在裸环境里跑到了报账（日志：$log）"
  python3 - "$log" "$ver" "$want_prefix" <<'PY'
import json, re, sys
log, want_ver, want_prefix = sys.argv[1], sys.argv[2], sys.argv[3]
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
sys.exit(1 if fails else 0)
PY
  if [ $? -ne 0 ]; then fail=$((fail + 1)); else pass=$((pass + 1)); fi
  # 撤销/重做也必须在裸环境里绕回来（M5-b 的装机证据是另一轮专门跑的）
  if grep -aq 'M0_HISTORY' "$log"; then
    echo "  · 附带：LRT_AUTO_HISTORY 也在这轮跑了（细节见 $log）"
  fi
  fi
fi

echo
echo "── 读数：$pass 条通过，$fail 条不过"
if [ "$fail" -ne 0 ]; then
  echo "VERDICT=FAIL — 这个包还不算开箱即用"
  exit 1
fi
echo "VERDICT=PASS — 装机件在裸环境里自证通过（版本 $ver）"
