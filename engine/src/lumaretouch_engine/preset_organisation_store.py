"""Metadata-only preset organisation. Recipes, IDs and referenced assets are never rewritten.

All callers changing recipe files MUST hold catalogue_lock() too. Keep the sidecar
outside *.json enumeration. Linux flock serialises processes; RLock serialises threads.
"""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import fcntl
import json
import os
import re
import stat
import tempfile
import threading
import unicodedata

SCHEMA = 'lrt.preset-organisation.v1'
DEFAULT = 'custom'
BUILTIN = 'builtin'
MAX_BYTES = 4 * 1024 * 1024
MAX_ITEMS = 10000
LOCK = threading.RLock()
LOCAL = threading.local()
ACTIONS = {'category_create', 'category_rename', 'category_move', 'category_trash',
           'category_restore', 'preset_rename', 'preset_move', 'preset_trash', 'preset_restore'}

class OrganisationError(ValueError):
    def __init__(self, message, *, outcome_unknown=False):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown

def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')

def digest(value):
    return sha256(encoded(value)).hexdigest()

def name(value):
    if type(value) is not str: raise OrganisationError('名称必须是文本')
    value = unicodedata.normalize('NFC', value.strip())
    if not value or len(value) > 20 or any(unicodedata.category(c).startswith('C') for c in value):
        raise OrganisationError('名称须为 1–20 个 Unicode 字符，不含控制字符')
    return value

def identity(value):
    if type(value) is not str or not re.fullmatch(r'[a-z0-9._-]{1,64}', value) or value.startswith('.') or '..' in value:
        raise OrganisationError('无效的稳定 ID')
    return value

@contextmanager
def catalogue_lock(root):
    root = os.path.abspath(root)
    with LOCK:
        # Shared-store save/list may nest under an organisation transaction.
        if getattr(LOCAL, 'root', None) == root:
            yield
            return
        if getattr(LOCAL, 'root', None) is not None: raise OrganisationError('不能交叉锁定预设目录')
        os.makedirs(root, exist_ok=True)
        fd = os.open(os.path.join(root, '.organisation.lock'), os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise OrganisationError('预设目录锁不是普通文件')
            fcntl.flock(fd, fcntl.LOCK_EX)
            LOCAL.root = root
            yield
        finally:
            LOCAL.root = None
            os.close(fd)

def empty():
    return {'schema': SCHEMA, 'generation': 0, 'categories': [
        {'id': BUILTIN, 'name': '内置预设', 'deleted': False},
        {'id': DEFAULT, 'name': '未分类', 'deleted': False}], 'items': {}, 'receipts': []}

def validate(state):
    if type(state) is not dict or set(state) != {'schema','generation','categories','items','receipts'} or state['schema'] != SCHEMA:
        raise OrganisationError('分类存储版本或字段无效；未覆盖原文件')
    if type(state['generation']) is not int or not 0 <= state['generation'] < 2**53: raise OrganisationError('无效目录版本')
    cats, items, receipts = state['categories'], state['items'], state['receipts']
    if type(cats) is not list or not 2 <= len(cats) <= 512 or type(items) is not dict or len(items)>MAX_ITEMS:
        raise OrganisationError('目录数量越界')
    ids = set()
    for c in cats:
        if type(c) is not dict or set(c) != {'id','name','deleted'} or type(c['deleted']) is not bool: raise OrganisationError('分类结构无效')
        identity(c['id'])
        if c['id'] in ids: raise OrganisationError('重复分类 ID')
        ids.add(c['id'])
        if name(c['name']) != c['name']: raise OrganisationError('分类名称未规范化')
    if not {BUILTIN, DEFAULT} <= ids: raise OrganisationError('缺少系统分类')
    for c in cats:
        if c['id'] in (BUILTIN,DEFAULT) and (c['deleted'] or c['name'] != ('内置预设' if c['id']==BUILTIN else '未分类')):
            raise OrganisationError('系统分类被改写')
    names=[c['name'].casefold() for c in cats if not c['deleted']]
    if len(set(names)) != len(names): raise OrganisationError('重复分类名称')
    positions=[]
    for pid, item in items.items():
        identity(pid)
        if type(item) is not dict or set(item) != {'category_id','name','deleted','position'}: raise OrganisationError('预设分类记录无效')
        if item['category_id'] not in ids or type(item['deleted']) is not bool or type(item['position']) is not int or not 0<=item['position']<MAX_ITEMS:
            raise OrganisationError('预设分类引用无效')
        if item['name'] is not None and name(item['name']) != item['name']: raise OrganisationError('预设名称无效')
        positions.append(item['position'])
    if set(positions) != set(range(len(items))): raise OrganisationError('预设位置不连续或重复')
    deleted_categories={c['id'] for c in cats if c['deleted']}
    if any(i['category_id'] in deleted_categories for i in items.values()): raise OrganisationError('预设不能引用已删除分类')
    if type(receipts) is not list or len(receipts)>128: raise OrganisationError('回执存储无效')
    receipt_ids=set()
    for r in receipts:
        if type(r) is not dict or set(r) != {'request_id','request_hash','action','revision','generation'} or r['action'] not in ACTIONS:
            raise OrganisationError('回执结构无效')
        if type(r['request_id']) is not str or not 0<len(r['request_id'])<=128 or any(not isinstance(r[k],str) or not re.fullmatch('[0-9a-f]{64}',r[k]) for k in ('request_hash','revision')):
            raise OrganisationError('回执身份无效')
        if r['request_id'] in receipt_ids or type(r['generation']) is not int or not 0<r['generation']<=state['generation']: raise OrganisationError('回执序列无效')
        receipt_ids.add(r['request_id'])
    return state

def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise OrganisationError('分类存储包含重复字段')
        result[key]=value
    return result

def load(root):
    path = os.path.join(root, '.organisation.state')
    try: fd = os.open(path, os.O_RDONLY | getattr(os,'O_NOFOLLOW',0) | os.O_NONBLOCK)
    except FileNotFoundError: return empty()
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise OrganisationError('分类存储不是普通文件')
        with os.fdopen(fd,'rb',closefd=False) as f: raw=f.read(MAX_BYTES+1)
    finally: os.close(fd)
    if len(raw)>MAX_BYTES: raise OrganisationError('分类存储过大')
    try: return validate(json.loads(raw, object_pairs_hook=_unique_object))
    except (UnicodeError, json.JSONDecodeError) as error: raise OrganisationError('分类存储损坏；未覆盖原文件') from error

def write(root,state):
    payload=encoded(validate(state))
    if len(payload)>MAX_BYTES: raise OrganisationError('分类存储过大')
    tmp=None; replacing=False; committed=False
    try:
        with tempfile.NamedTemporaryFile(dir=root,prefix='.organisation-',suffix='.tmp',delete=False) as f:
            tmp=f.name; f.write(payload); f.flush(); os.fsync(f.fileno())
        replacing=True
        os.replace(tmp,os.path.join(root,'.organisation.state')); committed=True
        fd=os.open(root,os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    except OSError as error:
        # Never retry a possibly committed write. Read/query the original request.
        raise OrganisationError(str(error),outcome_unknown=replacing or committed) from error
    finally:
        if tmp is not None:
            try: os.unlink(tmp)
            except OSError: pass

def reconcile(state,docs):
    """Populate only metadata; keep missing IDs as tombstones for restored/imported recipes."""
    state=deepcopy(state); seen=set()
    for doc in docs:
        pid=identity(doc['id'])
        if pid in seen: raise OrganisationError('源目录包含重复预设 ID，必须先解决冲突')
        seen.add(pid)
        if type(doc.get('builtin')) is not bool or type(doc.get('name')) is not str or type(doc.get('modules')) is not dict:
            raise OrganisationError('源预设目录不完整')
        if pid not in state['items']:
            state['items'][pid]={'category_id':BUILTIN if doc['builtin'] else DEFAULT,'name':None,'deleted':False,'position':len(state['items'])}
        item=state['items'][pid]
        if doc['builtin'] and (item['category_id']!=BUILTIN or item['name'] is not None or item['deleted']):
            raise OrganisationError('内置预设元数据被改写')
        if not doc['builtin'] and item['category_id']==BUILTIN: raise OrganisationError('用户预设不能归入内置分类')
    validate(state)
    return state

def revision(state,docs):
    return digest({'generation':state['generation'],'categories':state['categories'],'items':state['items'],'source':docs})

def project(state,docs,errors=()):
    state=reconcile(state,docs)
    cats=state['categories']; rows=[]
    for doc in docs:
        item=state['items'][doc['id']]
        rows.append({'id':doc['id'],'name':item['name'] if item['name'] is not None else doc['name'],
                     'kind':doc['kind'],'builtin':doc['builtin'],**{k:item[k] for k in ('category_id','deleted','position')}})
    rows.sort(key=lambda row:row['position'])
    return {'schema':SCHEMA,'revision':revision(state,docs),'generation':state['generation'],
            'categories':deepcopy(cats),'presets':rows,'errors':list(errors),
            'missing':[{'id':pid,'category_id':item['category_id']} for pid,item in state['items'].items() if pid not in {d['id'] for d in docs}]}

def overlay(docs,root):
    """Caller already owns catalogue_lock; projected recipe copies retain every module/asset."""
    state=reconcile(load(root),docs); positions=state['items']
    out=[]
    for doc in docs:
        item=positions[doc['id']]
        if item['deleted']: continue
        copy=deepcopy(doc)
        if item['name'] is not None: copy['name']=item['name']
        out.append(copy)
    out.sort(key=lambda doc:positions[doc['id']]['position'])
    return out

def mutate(state,docs,request):
    action=request.get('action')
    if action not in ACTIONS: raise OrganisationError('未知目录操作')
    allowed={'action','request_id','expected_revision','id'}
    if action in ('category_create','category_rename','preset_rename'): allowed.add('name')
    if action in ('category_move','preset_move'): allowed.add('before_id')
    if action=='preset_move': allowed.add('category_id')
    if set(request)-allowed: raise OrganisationError('目录操作包含未知字段')
    pid=identity(request.get('id')); categories=state['categories']; items=state['items']
    by_cat={c['id']:c for c in categories}; by_doc={d['id']:d for d in docs}
    def category(cid,deleted=False):
        c=by_cat.get(cid)
        if not c or c['deleted']!=deleted: raise OrganisationError('分类不存在或状态已经变化')
        return c
    def unique_category(value):
        if any(c['id']!=pid and not c['deleted'] and c['name'].casefold()==value.casefold() for c in categories): raise OrganisationError('分类名称已存在')
    def unique_preset(value,cid):
        if any(d['id']!=pid and not items[d['id']]['deleted'] and items[d['id']]['category_id']==cid and
               unicodedata.normalize('NFC',items[d['id']]['name'] or d['name']).casefold()==value.casefold() for d in docs):
            raise OrganisationError('目标分类已有同名预设，请先重命名')
    if action.startswith('category_'):
        if pid in (DEFAULT,BUILTIN) and action!='category_move': raise OrganisationError('系统分类不能重命名、删除或重建')
        if action=='category_create':
            if pid in by_cat: raise OrganisationError('分类 ID 已存在，包括回收站')
            value=name(request.get('name')); unique_category(value)
            categories.append({'id':pid,'name':value,'deleted':False}); return
        c=category(pid,action=='category_restore')
        if action=='category_rename':
            value=name(request.get('name')); unique_category(value); c['name']=value
        elif action=='category_trash':
            if any(i['category_id']==pid for i in items.values()): raise OrganisationError('请先移出分类中的预设（含回收站和离线记录），再删除空分类')
            c['deleted']=True
        elif action=='category_restore': unique_category(c['name']); c['deleted']=False
        elif action=='category_move':
            before=request.get('before_id')
            if before==pid: raise OrganisationError('不能移动到自身之前')
            if before is not None: category(identity(before))
            categories.remove(c); categories.insert(next((i for i,v in enumerate(categories) if v['id']==before),len(categories)),c)
        return
    doc=by_doc.get(pid)
    if not doc or pid not in items: raise OrganisationError('源预设不存在，请刷新')
    if doc['builtin'] and action!='preset_move': raise OrganisationError('内置预设只读；请另存为自定义副本')
    item=items[pid]
    if item['deleted'] != (action=='preset_restore'): raise OrganisationError('预设状态已改变，请刷新')
    if action=='preset_rename':
        value=name(request.get('name')); unique_preset(value,item['category_id']); item['name']=value
    elif action=='preset_trash': item['deleted']=True
    elif action=='preset_restore':
        category(item['category_id']); unique_preset(item['name'] or doc['name'],item['category_id']); item['deleted']=False
    elif action=='preset_move':
        cid=identity(request.get('category_id')); category(cid)
        if (cid==BUILTIN) != doc['builtin']: raise OrganisationError('内置预设只能在内置分类中排序；自定义预设不能移入内置分类')
        unique_preset(item['name'] or doc['name'],cid)
        before=request.get('before_id')
        if before is not None:
            identity(before)
            if before==pid or before not in by_doc or items[before]['deleted'] or items[before]['category_id']!=cid: raise OrganisationError('排序锚点已改变，请刷新')
        order=sorted(items,key=lambda key:items[key]['position']); order.remove(pid)
        if before is not None: index=order.index(before)
        else:
            siblings=[i for i,key in enumerate(order) if items[key]['category_id']==cid]
            index=siblings[-1]+1 if siblings else len(order)
        order.insert(index,pid); item['category_id']=cid
        for index,key in enumerate(order): items[key]['position']=index

class OrganisationStore:
    def __init__(self,root,source):
        self.root=root; self.source=source # raw validated recipe list + errors, never overlay
    def snapshot(self):
        with catalogue_lock(self.root):
            docs,errors=self.source()
            return project(load(self.root),docs,errors)
    def transact(self,request):
        if type(request) is not dict or len(encoded(request))>16384: raise OrganisationError('目录请求过大或无效')
        rid=request.get('request_id')
        if type(rid) is not str or not 0<len(rid)<=128 or any(ord(c)<32 for c in rid): raise OrganisationError('缺少请求身份')
        hashed=digest(request)
        with catalogue_lock(self.root):
            docs,errors=self.source(); state=reconcile(load(self.root),docs)
            for receipt in state['receipts']:
                if receipt['request_id']==rid:
                    if receipt['request_hash']!=hashed: raise OrganisationError('同一请求 ID 不能用于不同操作')
                    return {**receipt,'replayed':True}
            if errors: raise OrganisationError('源预设目录存在错误，请先修复，未更改分类')
            if request.get('expected_revision')!=revision(state,docs): raise OrganisationError('目录已变化，请刷新后重新操作')
            mutate(state,docs,request); state['generation']+=1; validate(state)
            receipt={'request_id':rid,'request_hash':hashed,'action':request['action'],
                     'generation':state['generation'],'revision':revision(state,docs)}
            state['receipts']=(state['receipts']+[receipt])[-128:]
            write(self.root,state)
            return receipt
    def receipt(self,rid):
        with catalogue_lock(self.root):
            for item in load(self.root)['receipts']:
                if item['request_id']==rid: return deepcopy(item)
        return None
