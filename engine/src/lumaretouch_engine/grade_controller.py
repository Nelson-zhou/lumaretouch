"""Existing grade transaction, extracted without changing the effect chain."""
from time import monotonic_ns
from .ops.grade import check_params, GradeError

def handle(self, p: dict, emit):
    """肤色 HSL 定向（M3-b）+ 局部调色（COLOR-004）：三个滑块、一个混入比例、一个作用域。

    与 cmd_lut 的区别只有一件：这一层不拿表，拿的是公式（窗口内逐帧内核）。
    其余铁律逐字沿用：跑靶互斥、先全量校验后一次性提交、被拒整条不留痕、
    出帧失败回滚 + 补帧、事件只有一个组装点。它与磨皮/修容/形变一样不参与
    任何缓存键：改它不会让滤波重算，反向也一样。

    六个 action：set（增量）/amount（混入比例）/clear（关整层，**不动区域**）/
    scope（all|skin|brush）/mask（画笔区域）/mask_clear（丢掉区域）。两条硬规矩：
    ① 作用域要不到掩膜就整条拒，不静默退回全图（局部调色静默变成全图调色，用户从
    画面上分不出来，而他会以为只动了皮肤）；② **落笔即生效** —— 涂了一笔而画面不
    动是这一仓最像 bug 的体验，所以 mask 那一条在区域真非空时顺手把作用域切到
    brush，并把最终作用域随 grade_done 报出去（UI 的选择框读它，不自己记一份）。
    """
    action = p.get("action", "set")
    if action == "mask":
        from .final_canvas_flip_state import require_processing_capture
        require_processing_capture(self)
    if action not in ("set", "clear", "amount", "scope", "mask", "mask_clear"):
        emit({"event": "error",
              "error": f"未知 grade action: {action}（可用：set/clear/amount/"
                       "scope/mask/mask_clear）"})
        return
    if not self._image_loaded or self._vram is None:
        emit({"event": "error", "error": "尚未 load_image"})
        return
    if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
        emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x"
              f"{getattr(self.shm, 'h', '?')} != 会话 {self._vram.w}x{self._vram.h}，"
              "请先 load_image"})
        return
    if self.bench is not None and self.bench.is_alive():
        emit({"event": "error", "error": "跑靶进行中，拒绝 grade：先 bench_stop"})
        return
    # 参数键集合当场卡住：拼错了名字的键会被默默当作“没给”而沿用旧值，
    # 那是“按了滑块但画面不动、而事件看起来完全正常”的下一个版本。
    # cmd 本身也算一个键（命令与参数同层），所以它必须在白名单里——第一版就是
    # 忘了它，协议用例一跑就全军“grade 收到不认识的参数：cmd”。
    extra = sorted(set(p) - {"cmd", "action", "dh", "ds", "dv", "amount",
                             "scope", "rle", "feather", "mode"})
    if extra:
        emit({"event": "error", "error": f"grade 收到不认识的参数：{', '.join(extra)}"
              "（可用：dh / ds / dv / amount / scope / rle / feather / mode）"})
        return
    t_start = monotonic_ns()
    prev = self._grade
    prev_preset = self._lut_preset
    prev_scope = str(self._grade_scope)
    prev_mask = self._grade_mask
    if action == "set":
        cur = dict(dh=self._grade[0], ds=self._grade[1], dv=self._grade[2])
        given = {k: p[k] for k in ("dh", "ds", "dv") if p.get(k) is not None}
        if not given and p.get("amount") is None:
            emit({"event": "error", "error": "grade set 什么也没给：三个增量里至少给一个，"
                  "或者走 clear 把整层关掉"})
            return
        cur.update(given)
        try:
            # 部分提交语义与 cmd_deform 一致：拖一个滑块不该把另外两个抹零，
            # 但合出来的那组数必须整组校过才能写进常驻层
            vals = check_params(cur["dh"], cur["ds"], cur["dv"],
                                amount=float(p.get("amount", self._grade[3])))
        except GradeError as e:
            emit({"event": "error", "error": f"grade 被拒，整条不生效：{e}"})
            return
        info = self._vram.set_grade(vals[0], vals[1], vals[2], amount=vals[3])
        self._grade = vals
        # 手动改了肤色，预设身份就当场失效：不然下一条 `lut amount` 会以为
        # “这层的肤色还是预设那份”，把用户刚调的数与表的强度绑在一起盖掉
        self._lut_preset = None
    elif action == "amount":
        if p.get("amount") is None:
            emit({"event": "error", "error": "grade amount 什么也没给：需要一个 0–1 的数值"})
            return
        try:
            info = self._vram.set_grade_amount(p["amount"])
        except GradeError as e:
            emit({"event": "error", "error": f"肤色定向强度被拒，会话原样未动：{e}"})
            return
        self._grade = (self._vram.grade_params[0], self._vram.grade_params[1],
                       self._vram.grade_params[2], float(self._vram.grade_amount))
    elif action == "scope":
        scope = p.get("scope")
        if not isinstance(scope, str) or not scope:
            emit({"event": "error", "error": "grade scope 缺 scope：需要 all/skin/brush 三选一"})
            return
        try:
            # 名单与判据全部交回库层（vram.GRADE_SCOPES）：命令层抄一份就是下一轮
            # 加第四种作用域时漏改的那一处，而 skin/brush 的“掩膜在不在”只有会话知道
            info = self._vram.set_grade_scope(scope)
        except (ValueError, RuntimeError) as e:
            emit({"event": "error", "error": f"调色作用域被拒，会话原样未动：{e}"})
            return
        self._grade_scope = str(self._vram.grade_scope)
        self._grade_mask = self._vram.grade_mask
    elif action == "mask":
        import numpy as np

        from .ops.inpaint import feather_np, mask_from_rle

        rle = p.get("rle")
        if not isinstance(rle, list) or not rle:
            emit({"event": "error", "error": "grade mask 缺 rle 或 rle 为空："
                  "应为 [[y,x,len,value255], …]，从代理帧坐标采集"})
            return
        mode = str(p.get("mode", "add"))
        if mode not in ("add", "replace"):
            emit({"event": "error", "error": f"grade mask mode={mode!r} 非法（可用：add/replace）"})
            return
        try:
            feather = int(p.get("feather", 2))
        except (TypeError, ValueError):
            emit({"event": "error", "error": f"feather 非法：{p.get('feather')!r}（需 0–8 的整数）"})
            return
        if not 0 <= feather <= 8:
            emit({"event": "error", "error": f"feather={feather} 超出范围 [0, 8]"})
            return
        h, w = self._vram.h, self._vram.w
        try:
            hard = mask_from_rle(rle, h, w)
        except (ValueError, TypeError) as e:
            emit({"event": "error", "error": f"rle 非法，整条拒绝：{e}"})
            return
        soft = feather_np(hard, feather) if feather else hard.astype(np.float32)
        weight = np.round(np.clip(soft, 0.0, 1.0) * 255.0).astype(np.uint8)
        if int((weight > 0).sum()) == 0:
            emit({"event": "error", "error": "羽化后覆盖度归零：画笔太小或坐标不匹配"
                  "（会话为代理帧尺寸，得用代理帧坐标而不是原图坐标）"})
            return
        try:
            info = self._vram.set_grade_mask(weight, mode=mode)
        except (ValueError, RuntimeError) as e:
            emit({"event": "error", "error": f"调色区域被拒，会话原样未动：{e}"})
            return
        self._grade_mask = self._vram.grade_mask
        if self._vram.grade_scope != "brush":
            # 落笔即生效（见 docstring 那条理由）。区域刚刚校过非空，这一步按库层
            # 的判据不可能失败；真失败了（例如以后改了 setter）就走成对回滚，
            # 不留“区域多了一笔而作用域还是 all”那种半截状态。
            try:
                info = self._vram.set_grade_scope("brush")
            except (ValueError, RuntimeError) as e:
                self._grade_mask = prev_mask
                self._grade_scope = prev_scope
                self._restore_grade(prev, prev_scope, prev_mask)
                emit({"event": "error", "error": f"落笔后切局部作用域失败，已退回上一状态：{e}"})
                return
        self._grade_scope = str(self._vram.grade_scope)
        self._grade_mask = self._vram.grade_mask
    elif action == "mask_clear":
        info = self._vram.clear_grade_mask()
        # 库层会顺手把 brush 退回 all（没区域还写着 brush 就是每帧一异常），
        # 所以这两个字段必须从会话取而不是写死
        self._grade_mask = self._vram.grade_mask
        self._grade_scope = str(self._vram.grade_scope)
    else:
        info = self._vram.clear_grade()
        self._grade = (0.0, 0.0, 0.0, 1.0)
        self._lut_preset = None
    try:
        fr = self._write_current_frame("grade")
    except Exception as e:
        self._grade = prev
        self._lut_preset = prev_preset
        self._restore_grade(prev, prev_scope, prev_mask)
        self._grade_scope = str(self._vram.grade_scope)
        self._grade_mask = self._vram.grade_mask
        try:
            back = self._write_current_frame("grade")
            back.pop("render_ms", None)
            emit(back)
        except Exception:      # 回滚后仍出不了一帧：能说清的只有“重新导图”
            emit({"event": "engine_warn", "warn": "肤色定向回滚后仍无法出帧，本会话不可信，"
                  "请重新导入图片"})
        emit({"event": "error", "error": f"肤色定向渲染失败，已退回上一状态（"
              f"{type(e).__name__}）：{e}"})
        return
    fr["doc_state"] = self.doc_state()
    render_ms = fr.pop("render_ms")
    self._emit_grade_state(action, info, render_ms=render_ms,
                           total_ms=round((monotonic_ns() - t_start) / 1e6, 2))
    emit(fr)
