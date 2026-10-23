"""Persistence hooks shared by ordinary save/open and managed-import admission."""
import copy
import os
import re
import uuid


def validate(project):
    receipts = project.get('managed_import_receipts',{})
    if not isinstance(receipts,dict) or len(receipts)>256: raise ValueError('托管导入回执格式无效')
    for key,value in receipts.items():
        if str(uuid.UUID(key))!=key or not isinstance(value,dict) or value.get('request_id')!=key or value.get('status')!='succeeded' or type(value.get('imported')) is not int or not 0<=value['imported']<=512:
            raise ValueError('托管导入回执身份无效')
    for row in project.get('docs',[]):
        record = row.get('managed_import')
        if record is None: continue
        required = {'operation_id','original_path','original_stat','content_sha256','managed_root','mode'}
        if not isinstance(record,dict) or set(record)!=required or record['mode']!='copy': raise ValueError('托管来源记录格式无效')
        if str(uuid.UUID(record['operation_id']))!=record['operation_id']: raise ValueError('托管操作身份无效')
        if not isinstance(record['content_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',record['content_sha256']): raise ValueError('托管来源缺少完整内容哈希')
        if not isinstance(record['original_stat'],list) or len(record['original_stat'])!=5 or any(type(v) is not int for v in record['original_stat']): raise ValueError('托管来源文件身份无效')
        for key in ('original_path','managed_root'):
            path = record[key]
            if not isinstance(path,str) or not path.startswith('/') or '\x00' in path or len(path)>4096 or (path!='/' and any(p in ('','.','..') for p in path.split('/')[1:])): raise ValueError('托管来源路径无效')
        # The current path may be relocated later; logical original/root stay immutable.
        if record['content_sha256'] != row.get('fingerprint',{}).get('sha256'): raise ValueError('托管原图内容身份不匹配')


def save_row(runtime,stored):
    if 'managed_import' in runtime: stored['managed_import'] = copy.deepcopy(runtime['managed_import'])


def restore_row(stored,runtime):
    if 'managed_import' in stored:
        runtime['managed_import'] = copy.deepcopy(stored['managed_import'])
        runtime['name'] = os.path.basename(stored['managed_import']['original_path'])


def save_receipts(engine,project):
    project['managed_import_receipts'] = copy.deepcopy((engine._project or {}).get('managed_import_receipts',{}))
