"""Freeze explicit documents into unique task entries; never use source path as recipe ID."""
from copy import deepcopy
import os
import hashlib


def select(engine, command):
    ids = command.get('document_ids')
    if ids is not None:
        if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):
            raise ValueError('导出文档身份必须是非重复列表')
        rows = {r['document_id']:r for r in engine._docs}
        if set(ids)-set(rows): raise ValueError('导出文档已变化，请刷新')
        chosen = [rows[x] for x in ids]
        if any(r.get('trashed') for r in chosen): raise ValueError('请先恢复回收站文档再导出')
        return chosen
    images = command.get('images')
    if not images:
        index = engine._doc_index
        return [engine._docs[index]] if 0 <= index < len(engine._docs) else []
    if not isinstance(images,list) or any(not isinstance(p,str) or not p for p in images):
        raise ValueError('导出来源必须为非空路径列表')
    chosen = []
    for path in images:
        index = engine._index_of(path)
        if index>=0:
            row = engine._docs[index]
            if row.get('trashed'): raise ValueError('请先恢复回收站文档再导出')
            chosen.append(row)
        else: chosen.append({'path':os.path.abspath(path)})
    return chosen


def bounded_stem(stem, suffix):
    # Leave 16 bytes for output extension; filenames are limited in bytes.
    budget = 239 - len(suffix.encode("utf-8"))
    return stem.encode("utf-8")[:budget].decode("utf-8", "ignore") + suffix


def output_stem(row):
    stem = os.path.splitext(os.path.basename(row['path']))[0]
    if not row.get('copy_number',0): return stem
    suffix = hashlib.sha256(row['document_id'].encode('utf-8')).hexdigest()
    return bounded_stem(stem,'-copy-'+str(row['copy_number'])+'-'+suffix)


def output_names(chosen):
    stems = [output_stem(row) for row in chosen]
    names = [stem if stems.count(stem)==1 else bounded_stem(stem,'-doc-'+hashlib.sha256(
        (row.get('document_id') or row['path']).encode('utf-8')).hexdigest())
        for row,stem in zip(chosen,stems)]
    if len(set(names)) != len(names): raise ValueError('导出文档目标名称冲突，请移除重复选择')
    return names


def source_collisions(engine, chosen, directory, fmt):
    sources = {os.path.realpath(r['path']) for r in engine._docs} | {os.path.realpath(r['path']) for r in chosen}
    return [os.path.join(directory,stem+'.'+ext) for stem in output_names(chosen) for ext in {fmt,'tif'}
            if os.path.realpath(os.path.join(directory,stem+'.'+ext)) in sources]


def freeze(engine, chosen, snap):
    snapshots, entries, sources = {}, {}, {}
    names = output_names(chosen)
    for index,row in enumerate(chosen):
        key = 'document:'+hashlib.sha256(row['document_id'].encode('utf-8')).hexdigest() if row.get('document_id') else 'external:'+str(index)
        path = row['path']
        if key in snapshots: raise ValueError('导出目标重复')
        is_document = 'document_id' in row
        if is_document:
            state = engine._capture_state() if 0 <= engine._doc_index < len(engine._docs) and row is engine._docs[engine._doc_index] else row['state']
            options = dict(device=snap['device'],scale=snap['scale'],upscale_backend=snap['upscale_backend'],sharpen=snap['sharpen'],source_path=path)
            from .virtual_copy_people import row_snapshot, row_context
            options['people_graph'] = row_snapshot(engine,row)
            options['people_context'] = row_context(engine,row)
            local = engine._state_to_export_snap(state,**options)
        else: local = snap
        snapshots[key] = (deepcopy(local),is_document)
        stem = names[index]
        expected = None
        if is_document:
            source_key = row['source_asset_id']
            if source_key not in sources:
                from .virtual_copy_source import fingerprint_for
                sources[source_key] = fingerprint_for(row)[0]
            expected = sources[source_key]
        entries[key] = {'fingerprint':expected, 'path':path,'document_id':row.get('document_id'),'source_asset_id':row.get('source_asset_id'),
                        'recipe_version_id':row.get('recipe_version_id'),'copy_number':row.get('copy_number',0),'stem':stem}
    return list(entries),snapshots,entries
