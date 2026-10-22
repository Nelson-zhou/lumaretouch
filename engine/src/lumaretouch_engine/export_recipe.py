"""One recipe-to-ExportSpec implementation shared by export and inspection.

Consumes already-owned inputs; does not read an Engine or select another face.
Mask resampling allocates full-resolution assets, so the caller must admit the
render and dimensions before calling this function. Missing-layer reports remain
mandatory and full-quality inspection must reject any skipped active layers.
"""
from . import white_balance_recipe as WB
from .export import ExportSpec, resample_field
from .vram import RepairOp, LightOp
from .ops import curves as CURVES
from .ops import levels as LEVELS
from .repair_record import check_repair_params, validate_repair_ops


def build_export_spec(snap: dict, eh: int, ew: int, *, for_document: bool):
    """从命令线程拍好的快照里组一份 ExportSpec。返回 (spec, skipped)。

    为什么不直接读 self._*：导出跑在 worker 线程里，而 stdin 线程随时可能在改参数。
    读 live 状态的话，一批三张图会各自拿到"当时"的设置——中间拖一下滑块，前两张与
    后两张就不是同一套设置，而 export_done 里只写了一份。全部取自分好的 snap。

    `for_document=False`（导的不是当前这张图）时，消除笔、修容笔迹与形变一律不带：
    那些坐标属于**这一张脸**。把它们搬到别的照片上不是"批量应用设置"而是误调——
    与 M2-b 拒绝 synthetic 占位关键点是同一条理由。能跨图复用的只有参数级的东西：
    磨皮参数、调色表、肤色定向。skip 必须逐图报出去，不能默默少几层。
    """
    # 模块层不硬拉 numpy，与本文件其余按需取用的写法同一条。这一笔是真窗口抓出来的：
    # 形变与通道那两条分支用了 np，而当时挂上的图层里没有形变，协议用例也没走到
    # 那里——于是 `NameError: name 'np' is not defined` 一路活到了装机件。
    import numpy as np

    p = snap["params"]
    skipped: list = list(snap.get("export_skipped", []))
    if snap.get("channel") and float(snap.get("strength", 0)) != 0:
        if not for_document or snap.get("precompute") is None:
            from .export import ExportError
            raise ExportError("缺少这张图片的蒙版，禁止把局部磨皮扩大为全图")
    spec = ExportSpec(strength=float(snap["strength"]), radius=int(p["radius"]),
                      eps=float(p["eps"]), texture_radius=int(p["texture_radius"]),
                      broad_gain=float(p["broad_gain"]), mid_gain=float(p["mid_gain"]),
                      detail_gain=float(p["detail_gain"]),
                      grade=tuple(snap["grade"]), cube=snap["lut"],
                      # COLOR-004：作用域从 snap 取而不是读 self._grade_scope——导出跑在
                      # worker 线程里，而 stdin 线程随时可能在切作用域（上面那段理由）。
                      # 缺键的旧批次台账（存于 1.2.0 之前）当“全图”，不拿 None 去比名单。
                      grade_scope=str((snap.get("grade_scope") or "all")),
                      # 旧底片条格子里没这个键（它是在这一层之前存下的）：用 .get 兜零而
                      # 不是直接索引——拿历史快照导出应当“没有曝光层”，不是报错。
                      exposure=tuple(snap.get("exposure", (0.0,) * 7)),
                      exposure_ref_k=snap.get("exposure_ref_k"),
                      wb_options=WB.check_options(snap["wb_options"]) if "wb_options" in snap else WB.default_options(),
                      hsl=tuple(snap.get("hsl", (0.0,) * 24)),
                      curves=CURVES.check_curves(snap.get("curves")), levels=LEVELS.check_levels(snap.get("levels")),
                      lut_amount=float(snap["lut_amount"]),
                      deform_amounts={},
                      scale=int(snap.get("scale", 1)),
                      upscale_backend=str(snap.get("upscale_backend", "lanczos3")),
                      sharpen_amount=float(snap.get("sharpen", 0.0)))
    from .fabric_export import configure_export
    if for_document:
        configure_export(spec, snap, eh, ew)
    elif float(snap.get("fabric_amount", 0)) != 0:
        raise ValueError("衣物细褶需要逐图分析衣物语义蒙版，禁止复用另一张图片的蒙版")
    if not for_document:
        if spec.grade_scope == "objects": raise ValueError("Source-bound mask objects cannot transfer to another photo")
        skipped += ["repair", "light", "deform", "channel（笔迹与掩膜属于当前文档）",
                    "enhance（眼牙掩膜是从当前那一张脸的关键点画的，不能搬到别的图）",
                    "bg（换底遮罩是从当前那张图的色键/网络抠图算出来的，不能搬到别的图）"]
        if spec.grade_scope != "all":
            # 局部调色那一片也是**这一张图**的：skin 来自当前文档的预计算，brush 来自
            # 当前文档的笔迹。拿不到那一片就把整层调色一起放下，而不是“那就全图调一下”：
            # 把局部调色搬成全局调色不是“批量应用设置”，而是一张错图。
            spec.grade = (0.0, 0.0, 0.0, 1.0)
            spec.grade_scope = "all"
            skipped.append("grade 整层（局部调色作用域属于当前文档，不能搬到别的图）")
        return spec, skipped
    validate_repair_ops(snap["repair_ops"])
    spec.repair = [RepairOp(op_id=op.op_id,
                            weight=resample_field(op.weight, (eh, ew), uint8=True),
                            kind=op.kind, params=check_repair_params(op.kind, op.params))
                   for op in snap["repair_ops"]]
    spec.light = [LightOp(op_id=op.op_id,
                          weight=resample_field(op.weight, (eh, ew), uint8=True),
                          sign=op.sign) for op in snap["light_ops"]]
    spec.light_exposure = float(snap["light"]["exposure"])
    spec.light_radius = int(snap["light"]["radius"])
    deform = snap["deform"]
    amounts = {k: float(v) for k, v in (deform.get("amounts") or {}).items()
               if float(v) != 0.0}
    pc = snap["precompute"]
    # 待重挂的那一层也是用户的配方（CORE-001）：不能因为 `built=False` 就静默不导出。
    # 出片走的是另一条求值路径（满幅/分块自己从关键点重解场），所以它只需要关键点，
    # 不需要会话里那个单位场。
    if amounts and not (deform.get("built") or snap.get("deform_defer")):
        skipped.append("deform（配方非零但图层未构建且未标记可重建；不能报为完整应用）")
    if amounts and (deform.get("built") or snap.get("deform_defer")):
        if pc is None:
            # 关键点不在就没有场：宁可少一层形变也不能拿上一张脸的场来凑
            skipped.append("deform（没有可用的关键点）")
        else:
            spec.deform_amounts = amounts
            spec.landmarks = np.asarray(pc.landmarks, dtype=np.float32)
    # PORTRAIT-009：眼牙增强跟到导出。与形变同一条前提——它需要关键点，而出片是
    # 按**导出尺寸**重画掩膜（不放大预览档那张小掩膜：放大一份"身份"会涂错位置，
    # 而内容门的相对统计也会跟着插值得到的假边一起漂）。
    en = snap.get("enhance") or {}
    enh_amounts = {k: float(v) for k, v in (en.get("amounts") or {}).items()
                   if float(v) != 0.0}
    if enh_amounts and not (en.get("built") or snap.get("enhance_defer")):
        skipped.append("enhance（配方非零但图层未构建且未标记可重建；不能报为完整应用）")
    if enh_amounts and (en.get("built") or snap.get("enhance_defer")):
        if pc is None:
            skipped.append("enhance（没有可用的关键点，掩膜画不出来）")
        else:
            spec.enhance = enh_amounts
            spec.landmarks = np.asarray(pc.landmarks, dtype=np.float32)
    if snap["channel"]:
        if pc is None:
            skipped.append(f"channel:{snap['channel']}（没有掩膜）")
        else:
            arr, names = pc.stack()
            spec.channel = snap["channel"]
            spec.mask_names = list(names)
            spec.masks = resample_field(np.asarray(arr, dtype=np.float32), (eh, ew))
    # COLOR-004：局部调色也要跟到导出。两条臂的“那一片”来自不同地方：brush 用存下的
    # 画笔区域，skin 用当前档的人脸掩膜。两者都是代理帧坐标上的连续覆盖度，所以与
    # 修容/减淡笔迹走同一个 resample_field（双线性、uint8）——预览与导出是同一个连续场
    # 的两张网格，不是两套口径。
    if spec.grade_scope == "objects":
        from . import local_mask_state as LM
        spec.local_masks = LM.check(snap.get("local_masks"))
        spec.local_mask_source_path = snap.get("local_mask_source_path")
        _, required = LM.R.dependencies(spec.local_masks["recipe"])
        if required and (spec.local_masks["semantic_owner"] is None or spec.local_masks["semantic_owner"] != snap.get("local_mask_owner")):
            raise ValueError("Semantic mask source/backend/contract changed; export suspended")
        for name in required:
            if pc is None or name not in (pc.masks or {}):
                raise ValueError("Required semantic mask is unavailable: " + name)
            spec.local_mask_semantics[name] = resample_field(np.asarray(pc.masks[name], dtype=np.float32), (eh, ew))
    if spec.grade_scope in ("skin", "brush") and tuple(spec.grade) != (0.0, 0.0, 0.0, 1.0):
        cov = None
        if spec.grade_scope == "brush":
            gm = snap.get("grade_mask")
            if gm is None:
                skipped.append("grade 整层（画笔区域不在了）")
            else:
                # 不拿“与会话尺寸相等”当条件：代理档是按原图长宽比算出来的，
                # 从任何一档代理网格到导出网格都是同一个连续场的重采样（与笔迹
                # 同一条处理），而这里要防的是“静默加宽到全图”，不是网格尺寸。
                cov = np.asarray(gm)
        else:      # skin：从预计算产物里取那一片，不拿脸框去猜一个粗矩形
            if pc is None or "skin" not in (pc.masks or {}):
                skipped.append("grade 整层（没有可用的 skin 掩膜）")
            else:
                # 预览里走的是 float 掩膜，这里先量化成 uint8 覆盖度再重采样（与 brush
                # 同一个入口）。差异上界 0.5/255 的权重，而导出本来就是另一张网格：
                # export.py 头部定下的口径是“同尺寸上分块==整幅”，不是“与预览逐字节”。
                cov = np.round(np.clip(np.asarray(pc.masks["skin"], dtype=np.float64),
                                       0.0, 1.0) * 255.0).astype(np.uint8)
        if cov is not None:
            if int((cov > 0).sum()) == 0:
                skipped.append("grade 整层（调色区域一个像素也没盖到）")
            else:
                spec.grade_mask = resample_field(cov, (eh, ew), uint8=True)
                # 作用域名字原封不动留在 spec.grade_scope 里（skin 就是 skin）：导出环
                # 拿那份重采样后的覆盖度执行，而事件报的是用户选的那一档。
    # P1-2 换底：预览里 pipe.set_background 挂的是代理档坐标上的 uint8 遮罩，
    # _capture_state 把整份 _bg（含 matte/bg/backend/tol/softness）落进快照；导出这一路
    # 只做两件事——按导出尺寸重采样覆盖度（与 grade_mask 同一 resample_field 入口，
    # 双线性、uint8），并把 [0,1] 三分量背景色原样带到 spec.bg_ref。链序由 PreviewPipeline
    # 保证：apply_grade 之后、apply_geometry 之前 apply_background——与预览逐帧那一次同源。
    _bgs = snap.get("_bg") or {}
    if _bgs.get("active") and (_bgs.get("matte") is None or _bgs.get("bg") is None):
        skipped.append("bg（换底已启用但缺少遮罩或背景色，不能静默省略）")
    if _bgs.get("active") and _bgs.get("matte") is not None and _bgs.get("bg") is not None:
        _mt = np.asarray(_bgs["matte"])
        _bgv = _bgs["bg"]
        if _mt.ndim != 2:
            skipped.append(f"bg（遮罩形状异常：{_mt.shape}，需要 (H,W)）")
        elif int((_mt > 0).sum()) == 0:
            # 全 0 遮罩 = 整幅都是前景：这一层在导出里不会有任何作用。不静默加宽，
            # 也不拿未定义背景写出去——与「调色区域一个像素也没盖到」同一条口径。
            skipped.append("bg（遮罩全 0：整幅前景，换底在导出里不会有任何作用）")
        elif (not isinstance(_bgv, (list, tuple))) or len(_bgv) != 3:
            skipped.append(f"bg（背景色形状异常：{_bgv!r}，需要 3 分量）")
        else:
            try:
                _ref = tuple(float(v) for v in _bgv)
            except (TypeError, ValueError):
                skipped.append(f"bg（背景色不能转成 3 个 float：{_bgv!r}）")
            else:
                spec.bg_matte = resample_field(_mt, (eh, ew), uint8=True)
                spec.bg_ref = _ref
    return spec, skipped

