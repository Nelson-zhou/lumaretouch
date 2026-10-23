"""Actual queue/render adapter: stable per-document and derivative targets."""
from contextvars import ContextVar
from pathlib import Path
from dataclasses import asdict
import json
import math
import os
from .export_destination_policy import Source, Policy, DestinationError, freeze, restore, digest
from .export_destination_import import validate, origin

_ACTIVE = ContextVar('export_destination', default=None)


def build(engine, rows, entry_ids, entries, settings, policy_value, revision):
    policy = Policy(**policy_value)
    records = []
    receipts = {}
    ext = 'png' if settings['bit_depth'] == 16 and settings['format'] == 'png' else 'tif' if settings['bit_depth'] == 16 else settings['format']
    for row, key in zip(rows, entry_ids):
        provenance = validate(row.get('import_origin') or origin(row['path'], kind='legacy_parent'))
        version = engine._document_versions().version(row) if row.get('document_id') else None
        receipt = digest({'workspace':engine._document_versions().workspace,
                          'document_id':getattr(version,'document_id',None),
                          'revision':getattr(version,'revision',None),
                          'recipe_version_id':row.get('recipe_version_id'),
                          'source':entries[key].get('fingerprint'), 'origin':provenance})
        receipts[key] = receipt
        base = Source(key, row['path'], provenance['root'], receipt,
                      entries[key]['stem']+'.'+ext, provenance['relative'], origin_kind=provenance['kind'])
        records.append(base)
        if (settings.get('watermark') or {}).get('alsoClean'):
            records.append(Source(**{**asdict(base), 'item_id':key+'::clean', 'output_subdirectory':'无水印'}))
    if settings.get('layout'):
        from .layout_spec import geometry
        spec = settings['layout']; g = geometry(spec)
        count = math.ceil(len(rows)*spec['copies']/len(g['cells']))
        if count > 200: raise DestinationError('单批排版最多 200 页')
        if policy.layout_root:
            layout_root = policy.layout_root
        elif policy.mode == 'chosen_root':
            layout_root = policy.chosen_root
        else:
            # No arbitrary first-image directory for a multi-directory sheet.
            parents = {str(Path(r['path']).parent) for r in rows}
            if len(parents) != 1: raise DestinationError('跨原图目录排版请显式指定排版汇总目录')
            layout_root = parents.pop()
        folder = 'layout-'+digest({'receipts':receipts,'settings':settings,'policy':policy_value})[:24]
        for filename in [f'page-{i+1:04}.png' for i in range(count)]+['layout.pdf','manifest.json']:
            records.append(Source(**{**asdict(records[0]),'item_id':'layout::'+filename,
                'target_filename':filename,'output_subdirectory':folder,'destination_root':layout_root}))
    return freeze(records, policy, settings, revision,
                  protected_sources=[r['path'] for r in engine._docs])


def primary_target(payload, key):
    plan = restore(payload)
    return next(e.target for e in plan.entries if e.item_id == key)


def run(payload, key, function, *args, **kwargs):
    if payload is None: return function(*args, **kwargs)
    plan = restore(payload)
    entries = {e.item_id:e for e in plan.entries}
    base = entries[key]
    info = Path(base.source_path).stat()
    if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns) != base.source_stamp:
        raise DestinationError('导出来源已变化；请重新预览')
    token = _ACTIVE.set((plan, entries, key))
    try: return function(*args, **kwargs)
    finally: _ACTIVE.reset(token)


def variant_target(default, variant):
    active = _ACTIVE.get()
    if active is None: return default
    _, entries, key = active
    return entries[key+'::clean'].target if variant == 'clean' else entries[key].target


def resolve(path):
    active = _ACTIVE.get()
    if active is None: return None
    plan, entries, key = active
    matches = [entries[k] for k in (key,key+"::clean") if k in entries and entries[k].target == str(Path(path))]
    if len(matches) != 1: raise DestinationError('输出路径不属于冻结批次')
    entry = matches[0]
    if entry.disposition == 'skip': return (None, '按冻结目录计划跳过')
    if entry.disposition != 'write': raise DestinationError('请在导出设置中确认冲突处理')
    if os.path.lexists(path): raise DestinationError('冻结输出已存在；请核对原批次，重试不会改名或覆盖')
    return (path, None)


def create_missing():
    active = _ACTIVE.get()
    return bool(active and json.loads(active[0].policy_json)['create_missing'])


def active():
    return _ACTIVE.get() is not None


def decorate(result, payload, key):
    if payload is None: return
    plan = restore(payload)
    entry = next(e for e in plan.entries if e.item_id == key)
    result['destination_plan_id'] = plan.plan_id
    result['planned_target'] = entry.target
    result['renamed_from'] = entry.renamed_from
    by_target = {e.target:e for e in plan.entries if e.item_id in (key,key+'::clean')}
    for output in result.get('outputs') or []:
        planned = by_target.get(output.get('path'))
        if planned: output['renamed_from'] = planned.renamed_from
