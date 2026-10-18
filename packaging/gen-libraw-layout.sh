#!/usr/bin/env bash
# 生成 ops/libraw_layout.py —— ctypes 绑定用的字段偏移/常量表，出处全部来自真头文件。
#
# 为什么不能手抄偏移：libraw_data_t 有 381 KB，字段位置随 LibRaw 版本变；写错一处不会
# 报错，只会读到一堆"看着像数据"的垃圾（尺寸读成 0、机型名读成随机字节），而那正是本仓
# 最不能容的"自洽假数据"形状。所以：让编译器按**这台机器装的那份头**算 offsetof/sizeof，
# 生成物连同来源指纹（头 sha256 + LibRaw 版本 + 编译器版本）一起落进代码里。
#
# 只在开发机跑；产出的 .py 才是进包的那一份。跑之前需要 libraw-dev（apt install）。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
if ! dpkg -L libraw-dev >/dev/null 2>&1; then
  echo "× 没装 libraw-dev——偏移表只能从真头生成，不能凭记忆写"
  exit 1
fi
hdrs=$(dpkg -L libraw-dev | grep '/include/libraw/.*\.h$' | sort)
sha=$(sha256sum $hdrs | sha256sum | cut -d' ' -f1)
gccv=$(gcc --version | head -1)
out="$here/../engine/src/lumaretouch_engine/ops/libraw_layout.py"

python3 - "$here/libraw_layout.c" "$out" "$sha" "$gccv" <<'PY'
import json, os, subprocess, sys, tempfile

probe_c, out, sha, gccv = sys.argv[1:5]
exe = tempfile.mktemp()
subprocess.run(["gcc", "-Wall", "-O0", "-I/usr/include/libraw", "-o", exe, probe_c, "-lraw"], check=True)
data = json.loads(subprocess.run([exe], capture_output=True, text=True, check=True).stdout)
os.unlink(exe)
ver = data.pop("libraw_version")
csha = subprocess.run(["sha256sum", probe_c], capture_output=True, text=True, check=True).stdout.split()[0]

lines = [
    '"""LibRaw ctypes 绑定的字段偏移与常量 —— **生成物，不要手改**.',
    '',
    '生成：`packaging/gen-libraw-layout.sh` 编 `packaging/libraw_layout.c`，由编译器算',
    'offsetof/sizeof。手抄一份偏移的后果不是报错而是读到垃圾数据（尺寸 0、机型名乱码），',
    '那种"内部自洽"的读数本仓拦过多次，所以这张表只允许被生成。',
    '',
    f'来源指纹：LibRaw {ver}；头文件集合 sha256={sha[:16]}…；{gccv}；',
    f'探针源码 sha256={csha[:16]}… 。',
    '',
    '运行期还有一道真值自检（ops/libraw.py 的 self_check）：拿一张我们自己写的 DNG，',
    '按这张表读出尺寸与机型，与自研读侧解析出的 TIFF 标签逐一对账——表与 .so 不一致时',
    '整条后端拒绝上线，而不是拿垃圾当数据。',
    '"""',
    '',
    f'LIBRAW_VERSION = "{ver}"',
    f'HEADER_SET_SHA256 = "{sha}"',
    f'PROBE_SOURCE_SHA256 = "{csha}"',
    f'BUILT_BY = "{gccv}"',
    '',
    "LAYOUT = " + json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
    '',
]
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write("\n".join(lines))
print(f"✓ 已生成 {out}（LibRaw {ver}，{len(data)} 项）")
PY
