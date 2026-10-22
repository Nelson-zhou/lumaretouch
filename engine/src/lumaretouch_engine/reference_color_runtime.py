"""Source-bound installation shared by live preview and original export."""
from . import reference_color_state as S,local_mask_state as M
from .reference_color_stage import ReferenceColorStage


def sync(engine,*,strict=False):
    if engine._vram is None:return
    recipe=S.check(getattr(engine,S.KEY,None))
    if recipe["reference"] is not None:
        _ensure_reference(engine,recipe["reference"])
    if S.active(recipe):
        M.verify_source({'source':recipe['source']},engine._doc_path)
    engine._vram.reference_color=ReferenceColorStage(recipe)


def configure_export(spec,snap,*,for_document):
    recipe=S.check(snap.get('reference_color'))
    if S.active(recipe) and not for_document:
        raise ValueError('参考校正属于另一张照片；请先对导出目标逐图预检，不复制拟合增益')
    spec.reference_color=recipe


def verify_export(snap,path,shape):
    recipe=S.check(snap.get('reference_color'))
    if S.active(recipe):M.verify_source({'source':recipe['source']},path,shape)


def report(engine):
    return {'recipe':S.check(getattr(engine,S.KEY,None)),'method':S.ALGORITHM,
            'note':'同场景对应区域白平衡/亮度；不是 AI 风格迁移'}


def _ensure_reference(engine,reference):
    """Avoid decompressing the unchanged retained image on every slider frame.

    Cache only validation, never a substitute RGB/mask. File mutation, restored
    state/bundle identity or changed reference metadata forces full validation.
    """
    from .reference_color_assets import cache_root,hydrate
    from .batch_preflight import canonical
    path=cache_root()/(reference['asset_id']+'.npz')
    bundle=getattr(engine,'_reference_color_bundle',None)
    def key():
        if path.is_symlink():raise ValueError('参考图资源不能是符号链接')
        st=path.stat()
        return (canonical(reference),id(bundle),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    try:current=key()
    except FileNotFoundError:current=None
    if current is not None and current==getattr(engine,'_reference_color_asset_validation',None):return
    hydrate(reference,bundle)
    engine._reference_color_asset_validation=key()
