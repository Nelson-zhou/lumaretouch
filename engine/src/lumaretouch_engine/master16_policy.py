"""One neutral RGB16 pass-through policy for live and frozen export state."""
from .ops import curves as CURVES,levels as LEVELS
from . import photo_grain_state as PGS
from . import colour_editor_state as CES
from . import white_balance_recipe as WB,local_grade_layers as LG,effect_recovery_state as ERS
from . import manual_liquify_state as MLS,studio_background_state as SBS,optics_state as OPS,sky_replacement_state as SKS
from . import lip_makeup_state as LIPS,brow_shape_state as BROWS,nose_shape_state as NOSES,eye_shape_state as EYES,mouth_shape_state as MOUTHS
from . import reference_color_state as RCS,semantic_colour_state as SCS


class Master16PolicyMixin:
    @staticmethod
    def _master16_snapshot_blockers(snap: dict) -> list:
        """Adapt a frozen export recipe to the existing neutral-state validator.

        No live Engine state is changed, so preflight cannot corrupt the active
        document or race with rendering. Keep one definition of pixel blockers.
        This selects neutral passthrough versus the editing pipeline. A nonempty
        result must now route to edits, never be ignored or treated as completion.
        """
        from types import SimpleNamespace
        defaults = {
            "strength": 0.0, "grade": (0.0, 0.0, 0.0, 1.0),
            "grade_scope": "all", "lut": None, "lut_amount": 0.0,
            "repair_ops": [], "light_ops": [], "deform": {},
            "crop_rect": (0.0, 0.0, 1.0, 1.0), "crop_rotation": 0.0,
            "exposure": (0.0,) * 7, "wb_options": WB.default_options(), "hsl": (0.0,) * 24, "enhance": {}, "fabric_amount": 0.0,
            "curves": CURVES.default_curves(), "levels": LEVELS.default_levels(),
        }
        fields = {"_" + key: snap.get(key, value) for key, value in defaults.items()}
        fields["_colour_editor"] = CES.check(snap["colour_editor"]) if "colour_editor" in snap else CES.neutral()
        fields["_photo_grain"] = PGS.check(snap["photo_grain"]) if "photo_grain" in snap else PGS.neutral()
        fields["_bg"] = snap.get("_bg", {})
        fields["_local_grade_layers"] = LG.check(snap.get("local_grade_groups"))
        fields["_effect_recovery"] = ERS.check(snap.get("effect_recovery"))
        fields["_manual_liquify"] = MLS.check(snap.get("manual_liquify"))
        fields["_studio_background"] = SBS.check(snap.get("studio_background"))
        fields["_optics"] = OPS.check(snap.get("optics"))
        fields["_sky_replacement"] = SKS.check(snap.get("sky_replacement"))
        fields["_lip_makeup"] = LIPS.check(snap.get("lip_makeup"))
        fields["_brow_shape"] = BROWS.check(snap.get("brow_shape")); fields["_brow_shape_owner"] = snap.get("brow_shape_owner")
        fields["_nose_shape"] = NOSES.check(snap.get("nose_shape")); fields["_nose_shape_owner"] = snap.get("nose_shape_owner")
        fields["_eye_shape"] = EYES.check(snap.get("eye_shape"))
        fields["_eye_shape_owner"] = snap.get("eye_shape_owner")
        fields["_reference_color"] = RCS.check(snap.get("reference_color")); fields["_semantic_colour"] = SCS.check(snap.get("semantic_colour"))
        fields["_mouth_shape"] = MOUTHS.check(snap.get("mouth_shape"))
        fields["_mouth_shape_owner"] = snap.get("mouth_shape_owner")
        fields["_body_pose_bank"]=(snap.get("body_pose") or {}).get("bank")
        blockers=Master16PolicyMixin._master16_blockers(SimpleNamespace(**fields),
            scale=snap.get("scale", 1), sharpen=snap.get("sharpen", 0.0))
        from .people_export import fastpath_blocker
        if fastpath_blocker(snap.get('people')):blockers.append('人物图保留的参数或源归属资产（须完整尺寸准备，不可直通）')
        return blockers

    def _master16_blockers(self, *, scale: int, sharpen: float) -> list:
        """16-bit 直通能不能走：把“会改像素的那几项”逐个点名。

        只在中立位上才放行：磨皮强度 0、色阶三个增量全 0、LUT 未挂或强度 0、
        修脸/光影/形变算子表为空、放大倍率 1、出片锐化 0。这里不拿 strength 默认值 0.5
        当“没动过”——默认值也是会作用到像素上的一个值，用户要 16-bit 直通就得先把它们关掉，
        而不是让引擎替他在后台偷偷降到 8-bit。radius/eps/各层增益不单独拦：它们是
        “作用时怎么作”的参数，强度为 0 时不参与。每一层的中立位必须与 PreviewPipeline /
        ExportSpec 同源；只在这层拦不住的是“参数有值但实际为恒等变换”那一种，宁可多拦
        也不能默默降级。
        """
        b: list = []
        if CES.active(getattr(self,"_colour_editor",CES.neutral())):b.append("连续色彩编辑器（全源图统一目标，不可直通）")
        if PGS.active(getattr(self,"_photo_grain",PGS.neutral())):b.append("确定性源像素颗粒（须完整浮点编辑，不能直通）")
        from .body_pose_render import fastpath_blocker
        if fastpath_blocker(getattr(self,"_body_pose_bank",None)):b.append("身体几何（源图姿态与完整尺寸共同映射，不可直通）")
        if any(layer['enabled'] for layer in LG.check(getattr(self, '_local_grade_layers', None))['layers']):
            b.append('独立局部调色组（须验证所有启用组，不能绕过编辑路径）')
        if MLS.check(getattr(self, '_manual_liquify', None))['strokes']:
            b.append('手动液化与保护笔迹（须全尺寸重放，不能绕过编辑路径）')
        if SKS.check(getattr(self,'_sky_replacement',None))['enabled']:
            b.append('换天空（原件素材及区域全尺寸浮点重放）')
        if OPS.active(getattr(self,'_optics',None)): b.append('镜头/透视校正（完整浮点全局映射）')
        if LIPS.active(getattr(self, '_lip_makeup', None)): b.append('唇妆增强（三个独立控件）')
        if BROWS.active(getattr(self, '_brow_shape', None)): b.append('眉形（七项左右独立几何）')
        if NOSES.active(getattr(self, '_nose_shape', None)): b.append('鼻形（六项二维几何）')
        if EYES.active(getattr(self, '_eye_shape', None)): b.append('眼形（十项双侧二维几何）')
        if RCS.active(getattr(self, '_reference_color', None)): b.append('同场景参考校正（完整浮点 RGB16）')
        if SCS.active(getattr(self,'_semantic_colour',None)): b.append('AI 语义追色（完整浮点 RGB16）')
        if MOUTHS.active(getattr(self, '_mouth_shape', None)): b.append('嘴形（九项二维几何）')
        if SBS.active(getattr(self, '_studio_background', None)):
            b.append('影棚背景调整（须完整源图重新计算）')
        if ERS.enabled(getattr(self, '_effect_recovery', None)):
            b.append('效果恢复笔迹（须验证源图与全尺寸蒙版，不能绕过编辑路径）')
        if float(self._strength) != 0.0:
            b.append(f"磨皮强度={self._strength}")
        grade = list(self._grade) + [0.0, 0.0, 0.0, 0.0]
        if any(abs(float(v)) > 0.0 for v in grade[:3]) and float(grade[3]) != 0.0:
            b.append(f"色阶增量={tuple(grade[:3])}")
        # P1-5 附带修：老写法 `if self._lut` 在 cube 是 numpy/torch 数组时会抛
# 「truth value ambiguous」——还没走到「拒绝并说明理由」就崩。is not None 才是这里要的
# 判据（cube 挂了没有），配合 amount>0 才叫「LUT 层在像素上有点火」。
        if self._lut is not None and float(self._lut_amount) > 0.0:
            b.append(f"LUT 强度={self._lut_amount}")
        if self._repair_ops:
            b.append(f"修脸算子 {len(self._repair_ops)} 个")
        if self._light_ops:
            b.append(f"光影算子 {len(self._light_ops)} 个")
        # 控制点"存在"不等于"作用了"：load_image 会把上一次的控制点带进新一张图（位置还在、
        # 位移全零），拿条目数当判据会把一张干净的图挪成"有图层"而拒掉直通。只有非零位移才会改像素。
        nz = sum(1 for v in (self._deform.get("amounts") or {}).values()
                 if abs(float(v)) > 0.0)
        if nz:
            b.append(f"形变控制点 {nz} 个（位移非零）")
        if self._crop_rect != (0.0, 0.0, 1.0, 1.0):
            b.append(f"裁剪框={tuple(round(v, 4) for v in self._crop_rect)}")
        if float(self._crop_rotation) != 0.0:
            b.append(f"旋转={self._crop_rotation}°")
        if int(scale) != 1:
            b.append(f"放大倍率={scale}")
        if float(sharpen) != 0.0:
            b.append(f"出片锐化={sharpen}")
        # P1-5 补齐：直通这一路只走「16-bit 解码 → 原样写 TIFF」，图层不进；
        # 所以任何**会改像素**的编辑都必须挡在门外，否则出来的是「报着 bits=16、
        # readback_max_diff=0 的保真好话，但用户设的 EV/HSL/换底全被静默跳过」。
        # 前一份 blockers 只覆盖到 sharpen 为止，以下五条是漏网的。
        # 曝光/白平衡：7 元组 = (ev, temperature_shift, tint_shift, contrast,
        # highlights, shadows, saturation)。非零任一分量都会动像素；ref_k 只有
        # 在 temperature/tint 有值时才起作用，所以不单独拦（与 exposure 那条同源）。
        expo = list(self._exposure) + [0.0] * 7
        if any(abs(float(v)) > 0.0 for v in expo[:7]):
            b.append(f"曝光/白平衡/影调={tuple(round(float(v), 4) for v in expo[:7])}")
        if WB.has_picks(getattr(self, "_wb_options", WB.default_options())):
            b.append("白平衡中性点校正")
        # 八色 HSL：24 元组（8 段 × 色相/饱和度/明亮度），任一分量非零都会动像素。
        if not LEVELS.is_identity(getattr(self, "_levels", None)): b.append("色阶（有有效调整）")
        if not CURVES.is_identity(getattr(self, "_curves", None)):
            b.append("RGB/master 曲线（含亮度通道）")
        hsl = list(self._hsl) + [0.0] * 24
        if any(abs(float(v)) > 0.0 for v in hsl[:24]):
            b.append("八色 HSL（有色调偏移）")
        # 眼/牙增强：amounts 里任一非零就是像素级编辑（与 deform 同规：
        # 「条目存在」不等于「作用了」——只有非零位移/非零额度才真的改像素）。
        if self._fabric_amount: b.append("衣物细褶淡化（有有效调整）")
        _en = (self._enhance or {}).get("amounts") or {}
        _en_nz = sum(1 for v in _en.values() if abs(float(v)) > 0.0)
        if _en_nz:
            b.append(f"眼/牙增强 {_en_nz} 项（额度非零）")
        # 换底：active=True 意味着合成链上有一层 composite_t 会重画背景像素。
        # 与 P1-2 修的那条相呼应——直通这一路目前还没接 bg_matte/bg_ref，那就要拦。
        if (self._bg or {}).get("active"):
            b.append("换底（背景合成会改像素，直通不进这一层）")
        # 局部调色：scope=brush/skin 时那一片 matte 会参与 grade；直通这一路目前
        # 也不进 matte。全图 grade 上面已经通过 `self._grade` 拦了，这里只补作用域那一条。
        if str(self._grade_scope) != "all" and float(grade[3]) != 0.0 and any(abs(float(v)) > 0.0
                                                    for v in (list(self._grade) + [0.0, 0.0, 0.0, 0.0])[:3]):
            b.append(f"局部调色作用域={self._grade_scope}（brush/skin 遮罩不参与直通）")
        return b
