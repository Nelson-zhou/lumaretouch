"""Cheap identity guards for an already SHA-verified numeric gesture only.

The admission/commit paths still verify source/model bytes. These stamps do not
authorize a new mask, model or recipe; they detect replacement of the exact
inputs whose retained tensors are borrowed by a short-lived preview session.
"""
from pathlib import Path
from . import local_mask_state as M


def snapshot(engine, groups):
    row = engine._docs[engine._doc_index]
    source = (row['path'], M.file_stamp(row['path']))
    semantic = any(layer['enabled'] and M.R.dependencies(layer['mask']['recipe'])[1]
                   for layer in groups['layers'])
    from .creative_derived_source import record
    if record(engine) is not None:
        from .creative_derived_masks import live_dependencies
        source=(*source,live_dependencies(engine,groups))
        semantic=False # Exact measured category bank, never original-file model inference.
    models = []
    if semantic:
        from .face import model_search_dirs, SELFIE_MULTICLASS_MODEL
        path = next((Path(folder) / SELFIE_MULTICLASS_MODEL for folder in model_search_dirs(None)
                     if (Path(folder) / SELFIE_MULTICLASS_MODEL).is_file()), None)
        if path is None:
            raise ValueError('局部语义组模型已不可用')
        models.append((str(path.resolve()), M.file_stamp(path)))
    from .prompted_mask_resolver import active
    if any(layer['enabled'] and active(layer['mask']['recipe']) for layer in groups['layers']):
        from .prompted_model_install import model_root, runtime_path
        from .prompted_model_manifest import CHECKPOINT_FILENAME
        root, site = model_root(), runtime_path()
        # Track membership as well as each file: newly added/replaced code must
        # not retain the earlier full-inventory SHA verification.
        paths = [root / 'receipt.json', root / CHECKPOINT_FILENAME, site]
        paths.extend(sorted(site.rglob('*')))
        for path in paths:
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue  # Same immutable-code inventory policy as admission.
            if path.is_symlink():
                raise ValueError('AI 运行时路径变成符号链接，请重新验证模型')
            models.append((str(path), M.file_stamp(path)))
    return source, tuple(models)
