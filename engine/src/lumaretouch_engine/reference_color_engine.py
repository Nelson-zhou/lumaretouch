"""Read-only Engine adapter for frozen target preparation; no temporary live swap."""
from . import reference_color_state as S, local_mask_state as M
from .reference_color_review import ColorInput,candidate_key as state_key
from .reference_color_provenance import admit
from .optics_candidate_identity import fingerprint


def render(engine,row,candidate_state,document_id,revision,*,reference=False,cancelled=lambda:False):
    def check_cancel(*_progress):
        if cancelled(): raise ValueError('完整参考渲染已取消，未提交样片或编辑')
    check_cancel()
    admit(candidate_state)
    from .decode import load_full,is_raw
    from .full_source_working import source_bits,require_opaque_8bit,working_rgb
    from .export_recipe import build_export_spec
    from .cpu_memory_budget import available_estimate
    from .export import export_float
    from . import local_grade_source as groups, effect_recovery_runtime as recovery
    from . import manual_liquify_runtime as manual, studio_background_runtime as studio
    from . import sky_replacement_runtime as sky
    from PIL import Image
    versions=engine._document_versions();version=versions.version(row)
    current=0<=engine._doc_index<len(engine._docs) and engine._docs[engine._doc_index] is row
    if str(version.revision)!=str(revision) or document_id not in (version.document_id,engine._load_id if current else None):
        raise ValueError('自动预检目标文档版本不匹配')
    if not candidate_state.get('_params') or not candidate_state.get('_light'):
        raise ValueError('目标缺少完整编辑状态，不能借用当前照片参数')
    path=row['path'];stamp=M.file_stamp(path);candidate_key=fingerprint(candidate_state)
    # Admit before decoding. Smaller RAM reduces admitted dimensions, never the
    # source resolution; an oversized target is reported blocked, not downscaled.
    available=available_estimate();limit=min(32_000_000,max(0,(available-768*1024*1024)//160))
    if limit<4096:raise ValueError('目标完整编辑预检没有足够内存')
    if is_raw(path):
        from .ops import libraw
        dimensions=libraw.identify(path)
        if dimensions is None or dimensions['w']*dimensions['h']>limit:
            raise ValueError('RAW 完整尺寸不可验证或超过内存预算，未尝试全幅分配')
        bits=16
    else:
        with Image.open(path) as image:
            if image.width*image.height>limit:raise ValueError('目标源图超过本次完整编辑内存预算')
            bits=16 if source_bits(path,image)>8 else 8
            if bits==8:require_opaque_8bit(image)
    check_cancel()
    decoded=load_full(path,max_px=limit,device='cpu',want_bits=bits)
    check_cancel()
    if M.file_stamp(path)!=stamp:raise ValueError('自动目标在解码期间变化')
    if (decoded.h,decoded.w)!=(decoded.src_h,decoded.src_w) or decoded.draft_used or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size'):
        raise ValueError('参考统一要求真实完整原片，不能使用代理或相机预览')
    if bits==16 and str(decoded.rgb.dtype)!='uint16':raise ValueError('高位深输入未保留真实 RGB16')
    source={'sha256':M.source_digest(path),'width':decoded.w,'height':decoded.h}
    from . import virtual_copy_people as VP
    snap=engine._state_to_export_snap(candidate_state,device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0.,source_path=path,people_context=VP.row_context(engine,row),people_graph=VP.row_snapshot(engine,row),people_document_id=engine._document_versions().version(row).document_id)
    from .people_export import verify_source as verify_people, isolated_snapshot
    verify_people(snap,path);snap=isolated_snapshot(snap,for_document=True)
    if not reference:snap['reference_color']=S.empty()
    # Match the owned full-source inspection/export guards. No replacement face
    # selection or inferred scope is synthesized for an unanalyzed target.
    from . import body_pose_render as body_render
    from . import common_background_source as common_background
    for owner in (groups,recovery,manual,studio,sky,body_render,common_background):
        owner.check_export_decode(snap,path,stamp,(decoded.h,decoded.w))
    if snap.get('grade_scope')=='objects':
        M.verify_source(M.check(snap.get('local_masks')),path,(decoded.h,decoded.w));snap['local_mask_source_path']=path
    spec,skipped=build_export_spec(snap,decoded.h,decoded.w,for_document=True)
    if skipped:raise ValueError('自动预检不能略过目标上游效果：'+', '.join(map(str,skipped)))
    from .reference_color_runtime import verify_export
    verify_export(snap,path,(decoded.h,decoded.w))
    # RGB16 decoders retain source ICC encoding; the float renderer consumes
    # working sRGB. RGB8 was already converted in load_full and is not redone.
    rgb,_=export_float(working_rgb(decoded),spec,geometry=(snap['crop_rect'],snap['crop_rotation']),progress=check_cancel)
    check_cancel()
    if (M.file_stamp(path)!=stamp or str(versions.version(row).revision)!=str(revision)
            or fingerprint(candidate_state)!=candidate_key):
        raise ValueError('参考或目标完整候选在预检期间变化')
    return ColorInput(document_id,str(revision),source,state_key(candidate_state),rgb,spec.provenance_result)


def reference_intent(engine,row,state,document_id,revision,strength):
    from . import reference_color_assets as A
    from .reference_color_scope import check_params
    strength=S.number(strength,0,1)
    if strength==0:return check_params({'version':1,'strength':0.,'reference':None})
    frame=render(engine,row,state,document_id,revision,reference=True)
    ref=A.save(A.cache_root(),frame)
    return check_params({'version':1,'strength':strength,'reference':ref})


def prepare_target(engine,row,state,document_id,revision,params):
    from . import reference_color_assets as A,reference_color_review as R
    from .reference_color_scope import check_params
    request=check_params(params)
    if not request['strength']:return None
    A.hydrate(request['reference'],state.get('_reference_color_bundle') if S.check(state.get(S.KEY))['reference']==request['reference'] else None)
    reference=A.load(A.cache_root(),request['reference'])
    target=render(engine,row,state,document_id,revision)
    return R.prepare(reference,target,reference_asset_id=request['reference']['asset_id'],strength=request['strength'])
