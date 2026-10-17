"""权重门禁的单一出处（M8）：lama / birefnet / realesrgan 三个权重后端共用同一套放行条件。

为什么要有这一份：这三处「能不能上生产」原来是三个模块各写一遍同一段（文件在不在、
有没有给校验和、校验和对不对得上）。而能力上报（ready 里那份后端清单）要的正是同一个
判据——再抄一遍就是两个出处：上报说可用而提交被引擎拒（或反过来，明明放行了一直报
「等权重」），两种都在报表上看不出来。所以放行条件只允许存在这一份，两边都从这里取。

sha256 按 (路径, 大小, mtime_ns, 期望值) 缓存：ready 时算一次，之后 `load_net` 不再重读
整份权重；文件被换过则 mtime/大小变了，缓存自然失效，不会拿旧结论放行新内容。
没有权重文件时连读都不读（一次 `isfile` 就返回），所以「裸装机 + 未放行」这一档零成本。
"""

from __future__ import annotations

import hashlib
import os

#: 缓存条数上限：只有三个后端会进来，这道守卫挡的是被人拿任意路径反复调用的情况。
_CACHE_LIMIT = 16
_digest_cache: dict[tuple, tuple[bool, str]] = {}


def sha256_matches(path: str, want: str) -> tuple[bool, str]:
    """算一次 sha256 并与期望对账。返回 (是否一致, 不一致时的理由)。"""
    st = os.stat(path)
    key = (path, st.st_size, st.st_mtime_ns, want)
    hit = _digest_cache.get(key)
    if hit is not None:
        return hit
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    got = h.hexdigest()
    res = (got == want, "" if got == want else f"权重 sha256 不符：期望 {want}，实得 {got}（{path}）")
    if len(_digest_cache) >= _CACHE_LIMIT:
        _digest_cache.clear()
    _digest_cache[key] = res
    return res


def production_gate(*, model_file: str, sha_env: str, path: str, absent_reason: str) -> tuple[bool, str]:
    """这个权重后端现在能不能上生产：返回 (能与否, 不能的话是为什么)。

    三条都是硬条件，缺一条就整条不接单——**绝不静默降级**：
      1. 权重文件在位（权重不入库、引擎不吃下载，由安装器按 sha256 取官方发布件）；
      2. 给了 `<环境>` 校验和（无校验和的权重不可信：权重被换过在报表上看不出来，
         与「会话在 CPU 上跑却标 cuda」同源）；
      3. 实算摘要与校验和一致。
    """
    if not os.path.isfile(path):
        return False, absent_reason
    want = os.environ.get(sha_env, "").strip().lower()
    if not want:
        return False, (f"{model_file} 存在但没有 {sha_env}：无校验和的权重不许上生产——"
                       "权重被换过在报表上看不出来，与「会话在 CPU 上跑却标 cuda」同源")
    return sha256_matches(path, want)
