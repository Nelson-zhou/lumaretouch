#!/usr/bin/env python3
"""生成 THIRD_PARTY_NOTICES：从**实际安装**的 dist-info 元数据读许可，不手写。

为什么要生成而不是手写：手写那份会在依赖一升级就变成假声明。

拿实际数据说话（本工具自己把自己错学过一次）：matplotlib 的第三方组件清单
（FreeType / Qhull / HarfBuzz / STIX 与 DejaVu 字体 / Yorick colormaps）确实存在，
但它在 `dist-info/METADATA` 的 `License` 字段里、**不在 `dist-info/LICENSE` 文件里**；
只查后者会得出“这个版本没有组件清单”的错误结论（本注释的第一版就错了）。所以
许可一律从元数据读，而元数据的字段形状在不同包之间不统一（SPDX / 自由文本 / 整段
许可正文），必须按实际内容分类处理而不是假定有一个短字段。

处理规则：
  · SPDX 优先取 `License-Expression`（PEP 639）；没有才回退 `License` 字段；
  · `License` 字段装的可能是一整篇许可正文（matplotlib、kiwisolver、cycler 就是这样）：
    表里只留摘要与长度，全文指向包内许可文本——声明不重写上游的话，但也不把几 KB
    正文灌进一张人要读的表里；
  · `dist-info/licenses/` 与包内许可文本的文件名及字节数全部列出，用来证明“许可文本确实
    随副本分发”（Apache-2.0 §4(a)、BSD、CC-BY 的共同要求）；
  · 按包名排序、带版本，同输入同输出，可被 check-release.sh 逐字节对账。

用法：
    python3 packaging/gen-notices.py --python <运行时的 python> > THIRD_PARTY_NOTICES
"""
import argparse
import importlib.metadata as md
import os
import subprocess
import sys

# 故意不进表的包：本仓库自己的产物，许可已在 LICENSE / NOTICE 里声明。
OURS = {"lumaretouch-engine"}


def license_of(dist):
    """返回 (表内许可文本, 形式标签, 是否需要指向全文)。

    形式只有三种，且第三种必须自己说清：“元数据未声明”与“声明了一整篇正文”
    对读表人是完全不同的行动（前者要去上游问，后者只要去指那个文件）。
    """
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr, "SPDX", False
    lic = meta.get("License")
    if lic and lic.strip() and lic.strip().upper() != "UNKNOWN":
        t = " ".join(lic.split())
        if len(t) > 160 or "\n" in lic:
            # 整篇许可正文：只留摘要 + 长度，全文去包内文件读
            return (f"（自由文本，共 {len(lic)} 字符，摘要：{t[:110]}…）", "整篇正文→见右列文件", True)
        return t, "自由文本（未归一，不替上游猜 SPDX）", False
    return "（元数据未声明，需人读包内文本）", "缺失", True


def license_files(dist):
    """列出随副本分发的许可文本及其字节数——这是“文本真在包里”的证据，不是声明。"""
    try:
        fs = dist.files or []
    except (FileNotFoundError, OSError):
        return []
    out = []
    for f in fs:
        s = str(f)
        base = os.path.basename(s).lower()
        if "license" in base or base in ("copying", "copying.md"):
            try:
                out.append((s, f.locate().stat().st_size))
            except OSError:
                out.append((s, None))
    return sorted(out)


def target_site_packages(python: str) -> str:
    """问目标解释器要它自己的 purelib。不靠 execv、也不靠比对 realpath：

    venv 的 bin/python 是指向基座解释器的软链，`os.path.realpath(sys.executable)`
    会把两边判成同一个数，于是“跳到目标环境重跑自身”这个分支直接不走，表就就地
    用了启动它的那个 venv。实过的错长这样：表里有 pytest/iniconfig/pluggy（只可能在
    开发 venv）、却没有 torch（只在运行时有）——一个看起来完全成功的许可清单，其实
    把最大那个依赖漏了。所以这里只接受“问出来的绝对路径”，并验证它真的存在。
    """
    out = subprocess.run([python, "-c",
                          "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                         capture_output=True, text=True, check=True).stdout.strip()
    if not out or not os.path.isdir(out):
        raise SystemExit(f"× 拿不到 {python} 的 purelib（得到：{out!r}）")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable,
                    help="从哪个解释器的 site-packages 读元数据（就是运行时要发布的那套）")
    ap.add_argument("--only", default="",
                    help="逗号分隔的包名白名单；不填就是该解释器里的全部包（注意开发 venv 里会有 pytest 这种非发布件）")
    a = ap.parse_args()

    sp = target_site_packages(a.python)
    # 只给 discover 一个搜索根：sys.path 里混进任何其他 site-packages 都会让表静默变大。
    dists = sorted(md.Distribution.discover(path=[sp]),
                   key=lambda d: (d.metadata["Name"] or "").lower())
    if not dists:
        raise SystemExit(f"× 在 {sp} 里一个包都没发现——环境不对，不出表")
    only = None
    if a.only:
        only = {x.strip().lower() for x in a.only.split(",") if x.strip()}

    # 自证读对了环境：torch 是本项目最大的依赖，它不在场就说明读错了东西，直接拒绝出表。
    names = {(d.metadata["Name"] or "").lower() for d in dists}
    for must in ("torch", "mediapipe"):
        if must not in names:
            raise SystemExit(f"× 读的是 {sp}，但里面没有 {must}：环境搞错了或是运行时还没装齐，"
                             f"这个表不能当发布声明用")

    print("# 第三方许可与署名清单（THIRD_PARTY_NOTICES）")
    print("#")
    print("# 本文件由 packaging/gen-notices.py 从实际安装的 dist-info 生成，不要手改：")
    print("#   python3 packaging/gen-notices.py --python <运行时 python> > THIRD_PARTY_NOTICES")
    print("# 手改的那份会在依赖升级时默默变成假声明（旧审计就是这么失效的，见生成器顶部注释）。")
    print("#")
    # 只报环境与包版本，**不写绝对路径**：这张表会进 deb，把生成它的那台机器的
    # home 目录抄进发行物，等于在每一份副本里发一个用户名。check-release.sh 对这一条
    # 是硬门禁（本注释的第一版就写出了这个错，被它拦下）。
    print(f"# 读的搜索根：{os.path.relpath(sp, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))} 相对仓库根（不写绝对路径）")
    print("# 自证：本表要求 torch 与 mediapipe 均在场，缺一就直接报错不出表。")
    print()
    print("| 包 | 版本 | 许可（源头字段） | 形式 | 随副本的许可文本 |")
    print("|---|---|---|---|---|")
    for d in dists:
        name = d.metadata["Name"] or ""
        if not name or name.lower() in OURS:
            continue
        if only is not None and name.lower() not in only:
            continue
        lic, form, _ = license_of(d)
        files = license_files(d)
        ftxt = "、".join(f"{os.path.basename(s)}（{sz} B）" if sz is not None else s + "（读不到）"
                        for s, sz in files[:4]) or "⚠ 包内无许可文本"
        if len(files) > 4:
            ftxt += f" 等 {len(files)} 份"
        lic_cell = lic.replace("|", "\\|")
        print(f"| {name} | {d.version} | {lic_cell} | {form} | {ftxt} |")
    print()
    print("## 本软件自己分发的模型权重")
    print()
    print("以 `docs/model-licenses/models.json` 为单一事实源（台账里逐条记了 sha256、")
    print("体积、许可、证据等级与使用限制）；本表不重复列权重，避免两处对不上。")
    print()
    print("## LGPL / 动态库")
    print()
    print("- 上表里出现 `自由文本` 形式时，声明以该文本为准，本文件不改写它的含义。")
    print("- 本软件以独立进程 + JSON-lines 协议调用引擎，不对任何第三方库做静态链接；")
    print("  对 LGPL 类依赖（如 sounddevice 经 ctypes 加载的 libportaudio），用户可用系统")
    print("  包管理器替换该库，这是 LGPL “可替换性”要求的实现方式。未装该库时音频路径")
    print("  本来就不可用，与本软件的图像功能无关（实测本机 libportaudio2 为未安装态）。")
    print()
    print("## 本软件")
    print()
    print("LumaRetouch 源码以 GPL-3.0-or-later 发布（见 `LICENSE`），非商业自由软件；")
    print("署名与非商业告知见 `NOTICE`。分发本 deb 即同时分发上述许可文本，")
    print("安装件里的副本位于 `/usr/share/doc/luma-retouch/`。")


if __name__ == "__main__":
    main()
