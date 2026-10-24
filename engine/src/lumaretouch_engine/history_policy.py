"""Pure edit identity and gesture grouping; no engine, transport or I/O ownership."""
import json

def state_signature(st: dict) -> str:
    """状态的可比签名。判"这一步真改了没有"必须走它，不能拿字典直接 ==：
    调色表是 numpy 数组（== 返回数组，真值判断直接抛 ValueError），参数是浮点
    （1e-16 的差不能算"改过"），_deform/_grade 又是嵌套结构。"""
    d = {}
    for k, v in st.items():
        if k == "_creative_asset_records":
            d[k] = sorted(v or {})
        elif k == "_creative_base":
            d[k] = None if v is None else v["id"]
        elif k == "_id_background_bundle":
            d[k] = None if v is None else v["binding"]
        elif k == "_semantic_colour_mask_assets":
            d[k] = sorted(v)  # Recipe contains hash/shape references; immutable raw arrays never stringify.
        elif k == "_semantic_colour_bundle":
            d[k] = st.get("_semantic_colour",{}).get("reference")
        elif k == "_lut":
            # 表按对象身份比：内容相同的两张表是两个不同的调色动作，同一张表重复
            # 提交才是空操作。拷一份内容来比会把 33³ 的表在每次滑块时读一遍。
            d[k] = None if v is None else f"obj:{id(v)}"
        elif k == "_deform":
            d[k] = {"amounts": {a: round(float(b), 6) for a, b in v["amounts"].items()},
                    "built": bool(v["built"])}
        elif k == "_deform_default":
            d[k] = {a: round(float(b), 6) for a, b in v.items()}
        elif k == "_deform_overrides":
            # 覆盖是"哪一张脸 + 哪几个数"：脸盒按 5 位归一化取整（与 faces() 同一个
            # 口径），数值按 6 位——1e-16 的浮点噪声不该算"改过一层"。整份折成 JSON
            # 串再比：那堆 [list, dict] 直接 sorted() 会在脸盒相等时去比 dict，抛 TypeError。
            d[k] = json.dumps([[[round(float(x), 5) for x in o["box"]],
                                {a: round(float(b), 6) for a, b in o["amounts"].items()}]
                               for o in v], sort_keys=True)
        elif k == "_grade":
            d[k] = [round(float(x), 6) for x in v]
        elif k == "_enhance":
            # 三个数按 6 位取整，脸盒按 5 位（与 faces() 同一口径）：1e-16 的浮点噪声
            # 不算"改过一层"，而换了一张脸必须算
            d[k] = json.dumps([{a: round(float(b), 6) for a, b in v["amounts"].items()},
                               bool(v.get("built")),
                               None if not v.get("box") else
                               [round(float(x), 5) for x in v["box"]]], sort_keys=True)
        elif k == "_grade_mask":
            # P1-6：老口径 (shape, sum) 会把"等面积、不同位置"的两笔遮膜折成
            # 同一个签名——撤销历史与未保存徽章看不见这一步；正是审查报的那一格。
            # 改成 (shape, sha1(bytes))：一次编辑手势一次哈希，1024×1280 的
            # uint8 遮膜 1 MB 十几毫秒，不在每帧热路径。多一笔少一笔仍会变（原
            # 判据的那半优势保留），而位置搬动也拦得住。
            if v is None:
                d[k] = None
            else:
                import hashlib as _hl
                d[k] = (list(v.shape), _hl.sha1(v.tobytes()).hexdigest())
        elif k == "_bg":
            # P1-6：matte 与 _grade_mask 同一条签名口径（shape + 内容 sha1）。
            # 拿 (shape, sum) 会漏掉"同一张背景，把'人'抠到左边 vs 抠到右边"这一格。
            from .common_background_source import check as check_common
            key_recipe=check_common(v)
            mt = None if key_recipe is not None else v.get("matte")
            if mt is None:
                _matte_sig = None
            else:
                import hashlib as _hl
                _matte_sig = (list(mt.shape), _hl.sha1(mt.tobytes()).hexdigest())
            d[k] = {"active": bool(v.get("active")), "bg": v.get("bg"),
                    "backend": v.get("backend"), "tol": v.get("tol"),
                    "softness": v.get("softness"), "matte": _matte_sig, "key_recipe": key_recipe}
        elif k == '_body_pose_bank':
            from .body_pose_document_history import signature
            d[k]=signature(v)
        elif k in ('_people_transition','_body_pose_transition'):
            continue
        elif k == '_people_history':
            d[k]=None if v is None else {name:value for name,value in v.items() if name not in ('asset_fence','association_fence','association_revision')}
        elif k in ("_repair_ops", "_redo_ops"):
            if "_repair_stack_signature" not in d:
                from .creative_derived_repairs import stack_digest
                d["_repair_stack_signature"] = stack_digest(st)
        elif k == "_strength":
            d[k] = round(float(v), 6)
        elif k in ("_params", "_light"):
            d[k] = {a: round(float(b), 6) for a, b in v.items()}
        else:
            d[k] = v
    return json.dumps(d, sort_keys=True, default=str)

def command_group(name: str, msg: dict) -> str:
    """一次手势的身份证：命令名 + action + 这条命令**带了哪些参数名**。
    同一个滑块连发五十条 → 同一个组 → 合并成一步；换另一个滑块（参数名不同）就是新的一步。
    拿值当组名会出两件事：拖回原位那种"值又变回去"合并不了，而把 action 与路径参数
    （rle/paths）算进组名会让每一笔都是新组——那正好是我们要区分的两种动作。"""
    if name in ("shoulder_shape","leg_shape","arm_shape","waist_shape","leg_length","neck_shape","torso_length"):return name+":gesture:"+str((msg.get("request") or {}).get("gesture_id",msg.get("request_id","missing")))[:128]
    if name=='hair_colour':return 'hair_colour:'+str((msg.get('people_context') or {}).get('target'))+':'+str(msg.get('request_id','missing'))
    if name=="people":
        if msg.get('action')=='eyeliner_palette':return 'people:eyeliner_palette:'+str(msg.get('request_id'))
        if msg.get('action')=='eyelash_palette':return 'people:eyelash_palette:'+str(msg.get('request_id'))
        if msg.get('action')=='brow_makeup_palette':return 'people:brow_makeup_palette:'+str(msg.get('request_id'))
        if msg.get('action')=='lipstick_palette':return 'people:lipstick_palette:'+str(msg.get('request_id'))
        if msg.get('action')=='blush_palette':return 'people:blush_palette:'+str(msg.get('request_id'))
        if msg.get('action') in ('eye_light_review','blush_review','lipstick_review','eyeliner_review','eyelash_review','brow_makeup_review','iris_review'):return 'people:'+str(msg.get('action'))+':'+str(msg.get('request_id'))
        target=msg.get('target') or {};patches=(msg.get('payload') or {}).get('patches') or []
        return 'people:'+str(target.get('scope'))+':'+str(target.get('target_id'))+':'+str(msg.get('action'))+':'+','.join(sorted(str(p.get('operation_id'))+str(p.get('parameter_path')) for p in patches))
    if name in ("brow_shape","nose_shape","eye_shape","mouth_shape"): return name+":gesture:" + str(msg.get("gesture_id", "missing"))[:128]
    if name == "lip_makeup": return "lip_makeup:" + str(msg.get("control", "all"))
    if name in ("curves", "levels") and isinstance(msg.get("gesture_id"), str) and msg["gesture_id"]:
        return name + ":gesture:" + msg["gesture_id"][:128]
    keys = sorted(k for k in msg if k not in ("cmd", "action"))
    return f"{name}:{msg.get('action', '')}:{','.join(keys)}"

