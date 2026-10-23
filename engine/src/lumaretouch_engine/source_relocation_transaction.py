"""Path-only project transactions; immutable recipes and exact source SHA required.

The host must hold its project mutation gate across final validation, replace, and
publication. The advisory lock serializes cooperating relocation writers. Other
application writers must use the host gate; arbitrary external writers cannot be
made transactional by an advisory lock and are checked using content CAS.
"""
from __future__ import annotations
import copy
import fcntl
import hashlib
import json
import os
import re
import uuid
import time
import stat
from .source_relocation_io import Budget, hash_file, open_regular, open_directory

DIGEST = re.compile(r'^[0-9a-f]{64}$')
MAX_PROJECT = 256_000_000


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def project_digest(project):
    return hashlib.sha256(encoded(project)).hexdigest()


def read_project(path):
    fd = open_regular(path)
    try:
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_PROJECT + 1)
        if len(raw) > MAX_PROJECT: raise ValueError('项目超过大小上限')
        return raw, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def expected(row, project=None):
    source = (project or {}).get('source_assets',{}).get(row.get('source_asset_id'),{})
    fp = source.get('fingerprint') or row.get('fingerprint') or {}
    if fp.get('hash_level') != 'full' or not isinstance(fp.get('sha256'), str) or not DIGEST.fullmatch(fp['sha256']):
        raise ValueError('旧项目没有完整 SHA-256，不能证明是原图；请从可信备份恢复原文件')
    if type(fp.get('bytes')) is not int or fp['bytes'] < 1:
        raise ValueError('缺少原图大小证据')
    return fp


def preview(project, identities, paths, directory, cancelled):
    from .source_relocation_io import candidates
    if not identities or len(identities) > 64:
        raise ValueError('请选择 1–64 张缺失原图')
    rows, results, errors = {}, [], []
    for identity in identities:
        old = identity['old_path']
        matches = [r for r in project['docs'] if r['path'] == old and (r.get('document_id') == identity['document_id'] or not r.get('document_id'))]
        if len(matches) != 1: raise ValueError('项目来源身份不唯一')
        # lexists rejects a replaced, unreadable or dangling-link original, not just readable files.
        if os.path.lexists(old): raise ValueError('原路径仍存在；这是源文件变化或权限问题，不是缺失重定位')
        fp = expected(matches[0], project)
        rows[old] = (matches[0], fp)
        family = [r for r in project['docs'] if r.get('source_asset_id') == matches[0].get('source_asset_id')] if matches[0].get('source_asset_id') else matches
        results.append({**identity, 'affected_documents':[{'document_id':r.get('document_id'), 'copy_number':r.get('copy_number',0), 'trashed':bool(r.get('trashed'))} for r in family], 'sha256': fp['sha256'], 'bytes': fp['bytes'], 'candidates': [],
                        'metadata_equivalence': 'full-byte-sha256',
                        'format': identity.get('format'), 'width': identity.get('width'),
                        'height': identity.get('height'), 'orientation': identity.get('orientation')})
    budget = Budget(cancelled)
    wanted = {fp['bytes'] for _, fp in rows.values()}
    for path in candidates(paths, directory, budget, errors):
        try:
            # Size is only a read optimization, never acceptance evidence.
            fd = open_regular(path)
            try: size = os.fstat(fd).st_size
            finally: os.close(fd)
            if size not in wanted: continue
            found = hash_file(path, budget)
            for result in results:
                if found['sha256'] == result['sha256'] and found['bytes'] == result['bytes']:
                    if len(result['candidates']) >= 32:
                        raise TimeoutError('相同内容候选超过 32 个，请缩小目录范围')
                    if sum(len(r['candidates']) for r in results) >= 256:
                        raise TimeoutError('候选总数超过 256 个，请缩小扫描范围')
                    result['candidates'].append(found)
                elif directory is None and len(errors) < 64:
                    errors.append({'path': path, 'reason': '源文件变化：不是所选原图的完整内容'})
        except (TimeoutError, InterruptedError):
            raise
        except (OSError, ValueError) as error:
            if len(errors) < 64: errors.append({'path': path, 'reason': str(error)})
    budget.check()
    return {'rows': results, 'errors': errors, 'files_hashed': budget.files,
            'bytes_hashed': budget.bytes, 'project_digest': project_digest(project)}


def stage(project, plan, choices, cancelled):
    if project_digest(project) != plan['project_digest']: raise ValueError('项目已变化，请重新扫描')
    if not isinstance(choices, dict) or not choices or not all(isinstance(v, str) and v for v in choices.values()) or set(choices) - {r['document_id'] for r in plan['rows']}:
        raise ValueError('选择不属于此预览')
    output = copy.deepcopy(project)
    updates, budget = [], Budget(cancelled)
    sources = {}
    for item in plan['rows']:
        selected = choices.get(item['document_id'])
        if selected is None: continue
        found = next((c for c in item['candidates'] if c['path'] == selected), None)
        if found is None: raise ValueError('必须显式选择已核验候选，不能按文件名猜测')
        if os.path.lexists(item['old_path']): raise ValueError('原路径重新出现，请重新核验')
        current = hash_file(selected, budget, item['bytes'])
        if current['sha256'] != item['sha256'] or current['stat'] != found['stat']:
            raise ValueError('候选文件在预览后变化，请重新扫描')
        legacy = not any(r.get('document_id') for r in output['docs'])
        if legacy:
            row = next(r for r in output['docs'] if r['path'] == item['old_path'])
            if any(r is not row and r['path']==selected for r in output['docs']):
                raise ValueError('目标路径已属于另一文档；不能静默合并业务副本')
            row['path'] = selected; row['fingerprint']['path'] = selected
            updates.append({**item,'new_path':selected})
            continue
        row = next(r for r in output['docs'] if r.get('document_id') == item['document_id'])
        source_id = row['source_asset_id']
        if source_id in sources:
            if sources[source_id] != selected: raise ValueError('同源副本必须重连到同一个已核验文件')
            continue
        if any(r['path']==selected and r['source_asset_id']!=source_id for r in output['docs']):
            raise ValueError('目标属于另一独立来源；不能静默合并业务文档')
        sources[source_id] = selected
        from .virtual_copy_storage import relocate_source
        relocate_source(output, source_id, selected, {**expected(row,output),'path':selected})
        for sibling in output['docs']:
            if sibling['source_asset_id'] != source_id: continue
            sibling.setdefault('source_relocation_aliases',{})[item['old_path']] = item['sha256']
            updates.append({**item, 'document_id':sibling['document_id'], 'source_asset_id':source_id, 'new_path':selected})
    return output, updates


def persist(path, output, before_sha, operation_id, validate, cancelled, recheck, *, relocated=0):
    """Return old on pre-replace error; unknown after replace, never overwrite rollback."""
    validate(output)
    body = {k: v for k, v in output.items() if k not in ('_source_path', '_source_sha256')}
    body['updated_ns'] = time.time_ns()
    body['source_relocation_receipt'] = {'operation_id': operation_id, 'previous_sha256': before_sha, 'relocated': relocated}
    data = encoded(body)
    if len(data) > MAX_PROJECT: raise ValueError('项目超过大小上限')
    after_sha = hashlib.sha256(data).hexdigest()
    directory = os.path.dirname(path)
    parent = open_directory(directory)
    target = os.path.basename(path)
    lock, temp, replaced = None, None, False
    try:
        lock = os.open(target + '.relocation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(lock).st_mode): raise ValueError('项目锁不是普通文件')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if read_project(path)[1] != before_sha: raise ValueError('磁盘项目已变化，请重新打开并审核')
        temp = '.lrt-relocation-' + uuid.uuid4().hex
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if cancelled(): raise InterruptedError('已取消，项目保持原样')
        recheck()
        if cancelled(): raise InterruptedError('已取消，项目保持原样')
        if read_project(path)[1] != before_sha: raise ValueError('提交前项目发生变化')
        latest_parent = open_directory(directory)
        try:
            if (os.fstat(parent).st_dev, os.fstat(parent).st_ino) != (os.fstat(latest_parent).st_dev, os.fstat(latest_parent).st_ino):
                raise ValueError('项目所在目录发生变化')
        finally:
            os.close(latest_parent)
        os.replace(temp, target, src_dir_fd=parent, dst_dir_fd=parent)
        replaced, temp = True, None
        os.fsync(parent)
        return {'status': 'succeeded', 'sha256': after_sha, 'project': body}
    except Exception as error:
        if replaced:
            return {'status': 'unknown', 'sha256': after_sha, 'error': str(error), 'requires_readback': True}
        raise
    finally:
        if temp is not None:
            try: os.unlink(temp, dir_fd=parent)
            except OSError: pass
        if lock is not None: os.close(lock)
        os.close(parent)
