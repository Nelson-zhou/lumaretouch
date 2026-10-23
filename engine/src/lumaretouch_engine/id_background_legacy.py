"""Unchanged proxy-bound legacy path; not the reviewed ID workflow."""
from time import monotonic_ns
from . import sky_replacement_state as SKS, studio_background_state as SBS
def legacy_background(self, p: dict, emit):
    """抠图/换底（M6）：事件驱动——一次“换底”算一次遮罩，之后逐帧只做线性光合成。

    两个后端，证据强度不同，不许混报：
    * `color_key`（默认）：确定性色键，拿当前代理图与背景参考色的色差算遮罩——零依赖、可测。
    * `birefnet`：神经网络自动抠图。权重不在就是 MissingBackend，整条拒绝——
      绝不静默退成色键然后报一个“抠图成功”（与消除笔的 lama 守卫同一条规矩）。
    遮罩存为代理坐标 uint8，进 PROXY_BOUND（换代理档即作废）与统一历史栈（可撤销）。
    """
    import numpy as np

    action = p.get("action", "set")
    if action not in ("set", "clear"):
        emit({"event": "error", "error": f"未知 background action: {action}（可用：set/clear）"})
        return
    if not self._image_loaded or self._vram is None:
        emit({"event": "error", "error": "尚未 load_image"})
        return
    if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
        emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x"
              f"{getattr(self.shm, 'h', '?')} != 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
        return
    if self.bench is not None and self.bench.is_alive():
        emit({"event": "error", "error": "跑靶进行中，拒绝 background：先 bench_stop"})
        return
    extra = sorted(set(p) - {"cmd", "action", "backend", "bg", "tol", "softness"})
    if extra:
        emit({"event": "error", "error": f"background 收到不认识的参数：{', '.join(extra)}"
              "（可用：backend / bg / tol / softness）"})
        return
    t_start = monotonic_ns()
    if action == "clear":
        info = self._vram.clear_background()
        self._bg = dict(active=False, matte=None, bg=None, backend=None,
                        tol=None, softness=None)
        fr = self._write_current_frame("background")
        render_ms = fr.pop("render_ms")
        emit({"event": "bg_done", "action": "clear", "bg_ms": round(float(self._vram.last_bg_ms), 2),
              "render_ms": render_ms,
              "total_ms": round((monotonic_ns() - t_start) / 1e6, 2),
              "device": str(self._vram.device), **info})
        emit(fr)
        return

    if SKS.check(self._sky_replacement)["enabled"]:
        raise ValueError("请先关闭换天空，再启用完整换背景，避免后层覆盖天空效果")
    if SBS.active(self._studio_background):
        raise ValueError("完整换底会覆盖影棚背景调整，请先关闭背景调整；笔迹会保留")
    backend = p.get("backend", "color_key")
    if backend not in ("color_key", "birefnet"):
        emit({"event": "error", "error": f"未知抠图后端: {backend}（可用：color_key/birefnet）"})
        return
    bg = p.get("bg")
    if (not isinstance(bg, (list, tuple))) or len(bg) != 3:
        emit({"event": "error", "error": "background set 缺 bg：需 [r,g,b] 三个 0–255 整数"})
        return
    try:
        bg_i = [int(v) for v in bg]
    except (TypeError, ValueError):
        emit({"event": "error", "error": f"bg 非整数三元：{bg!r}"})
        return
    if any(not 0 <= v <= 255 for v in bg_i):
        emit({"event": "error", "error": f"bg 分量超出 0–255：{bg_i}"})
        return
    unit = [v / 255.0 for v in bg_i]
    src = self._src_rgb
    if src is None or src.shape[:2] != (self._vram.h, self._vram.w):
        emit({"event": "error", "error": "源图尺寸与会话不符（先 load_image）"})
        return
    matte_u8 = None
    if backend == "color_key":
        from .ops.matting import key_matte_np
        tol = float(p.get("tol", 0.12))
        softness = float(p.get("softness", 0.10))
        if not (0.0 <= tol <= 1.0 and 1e-3 <= softness <= 1.0):
            emit({"event": "error", "error": f"tol={tol}/softness={softness} 越界（tol∈[0,1]、softness∈[0.001,1]）"})
            return
        a = key_matte_np(src, tol=tol, softness=softness)
        matte_u8 = np.round(np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
        if int((matte_u8 > 0).sum()) == 0:
            emit({"event": "error", "error": "色键遮罩全为 0：背景与前景太接近，调高 tol 或换 birefnet"})
            return
    else:
        from .ops import birefnet
        try:
            matte = birefnet.BiRefNetMatte(device=str(self._vram.device))(self._src_gpu_norm())
        except birefnet.MissingBackend as e:
            emit({"event": "error", "error": str(e)})   # 绝不静默退成色键
            return
        matte_u8 = (matte.detach().cpu().numpy() * 255.0).round().clip(0, 255).astype(np.uint8)
    try:
        info = self._vram.set_background(matte_u8, unit)
    except (ValueError, RuntimeError) as e:
        emit({"event": "error", "error": f"换底被拒，会话原样未动：{e}"})
        return
    self._bg = dict(active=True, matte=matte_u8, bg=unit, backend=backend,
                    tol=float(p.get("tol", 0.12)) if backend == "color_key" else None,
                    softness=float(p.get("softness", 0.10)) if backend == "color_key" else None)
    fr = self._write_current_frame("background")
    render_ms = fr.pop("render_ms")
    fill = round(float((matte_u8 > 127).mean()), 4)
    emit({"event": "bg_done", "action": "set", "backend": backend, "bg": bg_i,
          "matte_fill_fg": fill, "bytes_bg": int(info["bytes_bg"]),
          "bg_ms": round(float(self._vram.last_bg_ms), 2), "render_ms": render_ms,
          "total_ms": round((monotonic_ns() - t_start) / 1e6, 2),
          "device": str(self._vram.device), **info})
    emit(fr)
