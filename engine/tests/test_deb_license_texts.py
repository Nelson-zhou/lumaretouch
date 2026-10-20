"""P2-7：Debian 包必须随副本分发 Apache-2.0 许可**全文**（不只是 NOTICE 转述）。

缺陷现场：packaging/build-deb.sh 的许可随包那一步只 cp LICENSE/NOTICE/README/models.json，
把 docs/model-licenses/archive/ 下的第三方许可全文整个漏掉了；而最终包回读校验的
for f in 只验 copyright/NOTICE/models.json，验不到全文——于是"包里根本没有 Apache 原文"
这件发布缺陷一路静默活到装机件。内置的 MediaPipe 权重是 Apache-2.0，NOTICE 自己明写
「§4 要求保留版权声明、许可链接与 NOTICE 内容」，而 §4(b) 要的是许可**全文**随副本分发。

这里全是 CPU：不起 GPU、不打真实 .deb（那需要完整 release 产物）。判据两层——
① 静态钉住脚本确实"既 cp 全文进包、又在最终包回读验全文"（回归这道缺陷的门）；
② 用真仓库文件跑一遍 staging+verify 的行为模拟，证明"少 cp 全文"这一形状会被验红。
写盘只落在工作区内（沙盒只许写 workspace），跑完即删。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD_DEB = REPO / "packaging" / "build-deb.sh"
ARCHIVE = REPO / "docs" / "model-licenses" / "archive"


def test_source_license_archive_has_real_apache_fulltext():
    """源里必须真有 Apache-2.0 全文（不是 stub、不是只有链接）——否则进包也没内容。"""
    txts = sorted(ARCHIVE.glob("*.txt"))
    assert txts, f"{ARCHIVE} 下没有任何许可原文文件"
    apache = [f for f in txts
              if "Apache License" in f.read_text(encoding="utf-8", errors="ignore")
              and "Version 2.0" in f.read_text(encoding="utf-8", errors="ignore")]
    assert apache, "archive/ 里找不到含「Apache License」+「Version 2.0」的全文文件"
    # 全文体量：Apache-2.0 正文约 11KB，几百字节的链接版不算全文
    big = [f for f in apache if len(f.read_bytes()) > 8000]
    assert big, "找到的所谓 Apache 全文过小，像是只写了链接的摘要版"


def test_build_deb_stages_and_verifies_fulltext():
    """钉住脚本：既把 archive 全文 cp 进包，又在最终包回读验 Apache 全文（两道都在才放行）。"""
    s = BUILD_DEB.read_text(encoding="utf-8")
    # ① staging：把 archive/*.txt 拷进包内 model-licenses/LICENSES
    assert re.search(r"cp\s+.*archive/\*\.txt.*LICENSES", s) or \
        re.search(r'cp\s+"\$\{lics\[@\]\}"\s+"\$docdir/model-licenses/LICENSES/"', s), \
        "build-deb.sh 没把 archive/ 的许可全文 cp 进包（P2-7 原缺陷）"
    # ② verify：在解包出来的最终包里按内容找 Apache 全文
    assert re.search(r'grep\s+-rl\s+"Apache License".*model-licenses/LICENSES', s), \
        "build-deb.sh 的最终包回读没验 Apache 全文（缺全文不会被拦下）"


def test_staging_verify_simulation_catches_missing_fulltext():
    """行为模拟：跑脚本里那两步的真实语义——少 cp 全文时，回读必须判红；补上才判绿。"""
    work = Path(tempfile.mkdtemp(prefix="p2_7_sim_", dir=str(REPO)))
    try:
        docdir = work / "pkg" / "usr" / "share" / "doc" / "luma-retouch"
        verify = work / "verify"

        def run_stage(copy_fulltext: bool) -> int:
            shutil.rmtree(docdir, ignore_errors=True)
            shutil.rmtree(verify, ignore_errors=True)
            (docdir / "model-licenses").mkdir(parents=True)
            # 只放转述件（NOTICE/copyright/models.json）——这正是上一版做到的一切
            (docdir / "NOTICE").write_text("NOTICE stub\n", encoding="utf-8")
            if copy_fulltext:
                # 复刻脚本新增的那一步：archive/*.txt → LICENSES/
                (docdir / "model-licenses" / "LICENSES").mkdir(parents=True, exist_ok=True)
                for f in ARCHIVE.glob("*.txt"):
                    shutil.copy2(f, docdir / "model-licenses" / "LICENSES" / f.name)
            shutil.copytree(docdir, verify / docdir.relative_to(work), symlinks=True)
            # 复刻脚本的回读判据：最终包里按内容找 Apache 全文（解出的树保留 pkg/ 前缀）
            lic_dir = verify / "pkg" / "usr" / "share" / "doc" / "luma-retouch" / "model-licenses" / "LICENSES"
            r = subprocess.run(["bash", "-c",
                                f'grep -rl "Apache License" "{lic_dir}" 2>/dev/null | grep -q .'],
                               text=True)
            return r.returncode

        # 不 cp 全文（原缺陷形状）：回读必须判红（grep 找不到 → 非 0）
        assert run_stage(copy_fulltext=False) != 0, \
            "缺全文时回读竟然放行——那 P2-7 就没被真正堵住"
        # cp 全文（修复后）：回读判绿
        assert run_stage(copy_fulltext=True) == 0, \
            "补了全文回读仍判红：模拟与脚本判据对不上"
    finally:
        shutil.rmtree(work, ignore_errors=True)
