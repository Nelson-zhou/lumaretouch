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
    from .export_format_plan import validate_settings
    format_plan = validate_settings(settings)
    policy = Policy(**policy_value)
    records = []
    receipts = {}
    explicit_ext = ('png' if settings.get('bit_depth') == 16 and settings['format'] == 'png'
                    else 'tif' if settings.get('bit_depth') == 16 else settings['format'])
    for row, key in zip(rows, entry_ids):
        decision = format_plan['entries'][key] if format_plan else None
        ext = decision['extension'] if decision else explicit_ext
        provenance = validate(row.get('import_origin') or origin(row['path'], kind='legacy_parent'))
        version = engine._document_versions().version(row) if row.get('document_id') else None
        receipt = digest({'workspace':engine._document_versions().workspace,
                          'document_id':getattr(version,'document_id',None),
                          'revision':getattr(version,'revision',None),
                          'recipe_version_id':row.get('recipe_version_id'),
                          'source':entries[key].get('fingerprint'), 'origin':provenance,
                          **({'format_decision_id':decision['decision_id']} if decision else {})})
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


def run(payload, key, function, *args, trusted_roots=None, previous_outputs=None, **kwargs):
    if payload is None:
        if trusted_roots is not None:
            raise DestinationError('Owned workflow output requires its frozen destination plan')
        return function(*args, **kwargs)
    plan = restore(payload)
    entries = {e.item_id:e for e in plan.entries}
    base = entries[key]
    info = Path(base.source_path).stat()
    if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns) != base.source_stamp:
        raise DestinationError('导出来源已变化；请重新预览')
    from . import owned_export_destination as owned
    owned_token = owned.enter(trusted_roots)
    token = _ACTIVE.set((plan, entries, key, previous_outputs or []))
    try: return function(*args, **kwargs)
    finally:
        _ACTIVE.reset(token)
        owned.leave(owned_token)


def variant_target(default, variant):
    active = _ACTIVE.get()
    if active is None: return default
    _, entries, key, _ = active
    return entries[key+'::clean'].target if variant == 'clean' else entries[key].target


def resolve(path):
    active = _ACTIVE.get()
    if active is None: return None
    plan, entries, key, _ = active
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


def frozen_profile(name):
    current = _ACTIVE.get()
    if current is None:
        return None
    from .export_format_plan import validate_settings
    envelope = validate_settings(json.loads(current[0].settings_json), current[0].entries)
    asset = envelope.get('output_profile_asset') if envelope else None
    if asset is None or name != asset['path']:
        return None
    from .export_format_profile import validate as profile_bytes
    return profile_bytes(asset)


def reuse_output(path):
    """Continue a partial Original delivery, not a skip or a fresh filename."""
    current = _ACTIVE.get()
    if current is None:
        return None
    plan, entries, key, previous = current
    from .export_format_plan import validate_settings
    format_plan = validate_settings(json.loads(plan.settings_json), plan.entries)
    if format_plan is None:
        return None
    matches = [entries[k] for k in (key, key+'::clean') if k in entries and entries[k].target == path]
    if len(matches) != 1 or matches[0].disposition != 'write':
        return None
    from .export_format_receipts import reusable
    from copy import deepcopy
    for output in previous:
        if reusable(output, path, format_plan['entries'][key]):
            return {**deepcopy(output), 'reused_previous_commit':True}
    return None


def decorate(result, payload, key):
    if payload is None: return
    plan = restore(payload)
    entry = next(e for e in plan.entries if e.item_id == key)
    result['destination_plan_id'] = plan.plan_id
    result['planned_target'] = entry.target
    result['renamed_from'] = entry.renamed_from
    from .export_format_plan import validate_settings, receipt_fields
    format_plan = validate_settings(json.loads(plan.settings_json), plan.entries)
    decision = format_plan['entries'][key] if format_plan else None
    if decision:
        result.update(receipt_fields(decision))
        # A non-watermarked ordinary writer has one result rather than a list.
        # Keep the actual codec reported by that writer; never label it Original.
        if not result.get('outputs') and result.get('out'):
            result['outputs'] = [{'path':result['out'], 'format':result.get('format'),
                'variant':'clean', 'bits':result['bits'], 'skipped':bool(result.get('out_skipped')),
                'bytes':result.get('bytes'), 'encoded_sha256':result.get('encoded_sha256'),
                'encoder_quality':result.get('encoder_quality'),
                **({'quality_mapping_version':result['quality_mapping_version']}
                   if 'quality_mapping_version' in result else {})}]
    by_target = {e.target:e for e in plan.entries if e.item_id in (key,key+'::clean')}
    for output in result.get('outputs') or []:
        planned = by_target.get(output.get('path'))
        if planned:
            output['renamed_from'] = planned.renamed_from
            if decision:
                output.update(receipt_fields(decision))
                # Commit failures may carry only a committed path. Encoding is
                # already complete when the canonical byte committer is entered.
                if output.get('committed') and not output.get('format'):
                    output['format'] = decision['codec']
                if (not output.get('output_identity') and not output.get('error')
                        and not output.get('skipped') and output.get('bytes', 0) > 0
                        and output.get('durability_confirmed') is not False
                        and output.get('directory_fsync') is not False):
                    from .export_format_receipts import identity
                    try:
                        proof = identity(output['path'])
                        encoded = output.get('encoded_sha256') or output.get('sha256')
                        if not encoded or encoded != proof['sha256'] or output['bytes'] != proof['bytes']:
                            raise ValueError('Original 输出与实际编码字节摘要不符；不能认证重试复用')
                        output['output_identity'] = proof
                    except (OSError, ValueError) as error:
                        # Keep the actual writer receipt. Lack of proof blocks
                        # later reuse; it must not erase a successful commit.
                        output['output_identity_error'] = str(error)
