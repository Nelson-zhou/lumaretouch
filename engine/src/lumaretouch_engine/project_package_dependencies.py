"""Bounded package inventory; replay assets stay in the validated project JSON.

Only authoritative source paths and sky replacement asset bindings are relocatable.
Other paths are provenance, not permission to read arbitrary local files.
"""
from __future__ import annotations
import hashlib
import os


def pointer(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def inventory(project, include_originals=False, include_references=False):
    if type(include_originals) is not bool or type(include_references) is not bool:
        raise ValueError('包含原片/外部参考必须明确选择')
    if project.get('schema_version') != 'lrt.project.v23':
        raise ValueError('便携包需要 v23 工程；旧版工程请先正常打开并保存以完成既有迁移')
    rows = []
    for source_id, source in project.get('source_assets', {}).items():
        prefix = '/source_assets/' + pointer(source_id)
        bindings = [prefix + '/path']
        if 'path' in source.get('fingerprint', {}): bindings.append(prefix + '/fingerprint/path')
        for i, doc in enumerate(project['docs']):
            if doc['source_asset_id'] == source_id:
                bindings.append(f'/docs/{i}/path')
                if 'path' in doc.get('fingerprint', {}): bindings.append(f'/docs/{i}/fingerprint/path')
        rows.append({'id': 'source-' + hashlib.sha256(source_id.encode()).hexdigest(),
                     'type': 'original', 'source_asset_id': source_id, 'path': source['path'],
                     'include': include_originals, 'bindings': bindings,
                     'sha256_expected': source.get('fingerprint', {}).get('sha256') if source.get('fingerprint', {}).get('hash_level') == 'full' else None,
                     'licence': 'user-provided; redistribution rights not inferred',
                     'provenance': {'source_asset_id': source_id, 'original_path': source['path']}})
    references = {}
    nodes = 0
    def walk(value, at='', depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 2_000_000 or depth > 128: raise ValueError('工程依赖嵌套/节点预算超限')
        if isinstance(value, dict):
            sky = value.get('_sky_replacement')
            asset = sky.get('asset') if isinstance(sky, dict) else None
            if isinstance(asset, dict) and isinstance(asset.get('path'), str):
                key = (asset['path'], asset['sha256'])
                record = references.setdefault(key, {'id': 'reference-' + hashlib.sha256(repr(key).encode()).hexdigest(),
                    'type': 'reference', 'path': asset['path'], 'include': include_references,
                    'sha256_expected': asset['sha256'], 'bindings': [],
                    'licence': 'user-provided; redistribution rights not inferred',
                    'provenance': {'feature': 'sky_replacement', 'original_path': asset['path']}})
                record['bindings'].append(at + '/_sky_replacement/asset/path')
            for key, child in value.items(): walk(child, at + '/' + pointer(key), depth + 1)
        elif isinstance(value, list):
            for i, child in enumerate(value): walk(child, at + '/' + str(i), depth + 1)
    walk(project)
    rows.extend(references.values())
    if len(rows) > 10000: raise ValueError('工程外部依赖数量超限')
    return rows


def summary(project, dependencies):
    embedded = []
    for identity, asset in project.get('assets', {}).items():
        embedded.append({'id': identity, 'type': 'embedded-replay-asset', 'kind': asset.get('kind'),
                         'bytes': asset.get('bytes'), 'status': 'mandatory-in-project',
                         'licence': 'retained user project asset; rights not inferred'})
    rows = []
    for dep in dependencies:
        row = dict(dep)
        exists = os.path.isfile(dep['path']) and not os.path.islink(dep['path'])
        row.update(status='selected' if dep['include'] and exists else 'missing' if dep['include'] else 'excluded',
                   bytes=os.path.getsize(dep['path']) if exists else 0)
        rows.append(row)
    return {'dependencies': rows, 'embedded_assets': embedded,
            'bytes': sum(r['bytes'] for r in rows if r['include']),
            'model_dependencies': model_inventory(project),
            'warnings': ['内嵌参考、LUT、人物/身体支持、证件照背景及历史完整保留；选项只控制外部原片/天空参考。',
                         '仅打包您有权携带的本地素材；模型权重不打包、不下载。',
                         '未选或缺失依赖会保留明确缺失记录，恢复后需重定位原片或重新选择天空素材。']}


def validate_inventory(project, dependencies):
    expected = {row['id']: row for row in inventory(project, True, True)}
    if type(dependencies) is not list or len(dependencies) != len(expected):
        raise ValueError('便携包依赖清单与工程不一致')
    seen = set()
    for row in dependencies:
        wanted = expected.get(row.get('id'))
        if wanted is None or row['id'] in seen: raise ValueError('便携包依赖身份无效')
        seen.add(row['id'])
        if any(row.get(key) != wanted[key] for key in ('type', 'path', 'bindings', 'sha256_expected')):
            raise ValueError('便携包依赖路径绑定与工程不一致')
        if row.get('status') == 'bundled' and wanted.get('sha256_expected') and row.get('sha256') != wanted['sha256_expected']:
            raise ValueError('便携包源字节与工程已有完整指纹不一致')


def model_inventory(project):
    """Retained model identity evidence only, never discover or copy weight files."""
    evidence, nodes = [], 0
    def visit(value, at='', depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 2_000_000 or depth > 128: raise ValueError('模型依赖清单预算超限')
        if isinstance(value, dict):
            for key, child in value.items():
                location = at + '/' + pointer(key)
                if 'model' in key.lower() and isinstance(child, (str, int, float, bool)):
                    if len(evidence) >= 10000: raise ValueError('模型依赖证据数量超限')
                    evidence.append({'binding':location,'value':child,'status':'not-bundled','licence':'not inferred; review separately'})
                elif key not in ('assets','people_support_assets','people_landmarks'):
                    visit(child, location, depth+1)
        elif isinstance(value,list):
            for i,child in enumerate(value): visit(child, at+'/'+str(i), depth+1)
    visit(project)
    return {'status':'not-bundled','writer':project.get('writer'),'retained_evidence':evidence,
            'policy':'Recorded identities only, not a complete installed environment. No weights, downloads, or licence grants.'}
