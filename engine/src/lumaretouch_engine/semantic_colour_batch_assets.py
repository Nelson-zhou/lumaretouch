# SPDX-License-Identifier: GPL-3.0-or-later
"""Private bounded proposal files; FrozenPlan contains small immutable references."""
from hashlib import sha256
import json
from pathlib import Path
import stat
import tempfile
import uuid
from .batch_preflight import canonical
LIMIT=512*1024*1024
RECORD_LIMIT=24*1024*1024


class ProposalAssets:
    def __init__(self):
        self.directory=tempfile.TemporaryDirectory(prefix='lumaretouch-semantic-plans-')
        self.root=Path(self.directory.name);self.entries={};self.plans={};self.used=0
    def close(self):
        self.entries.clear();self.plans.clear();self.used=0;self.directory.cleanup()
    def admit(self):
        if self.used+RECORD_LIMIT>LIMIT:raise ValueError('追色冻结审核的私有资源已达 512 MiB 预算，请完成/释放现有审核后分批继续')
    def put(self,record):
        self.admit();raw=canonical(record,limit=RECORD_LIMIT).encode();key=uuid.uuid4().hex
        descriptor={'id':key,'sha256':sha256(raw).hexdigest(),'bytes':len(raw),'proof':record['proof']}
        with (self.root/(key+'.json')).open('xb') as handle:handle.write(raw)
        self.entries[key]=descriptor;self.used+=len(raw)
        return dict(descriptor)
    def get(self,descriptor):
        if type(descriptor) is not dict or self.entries.get(descriptor.get('id'))!=descriptor:raise ValueError('追色冻结审核资源已释放或身份改变')
        path=self.root/(descriptor['id']+'.json');info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size!=descriptor['bytes']:raise ValueError('追色冻结审核资源大小改变')
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=descriptor['sha256']:raise ValueError('追色冻结审核资源字节改变')
        record=json.loads(raw)
        if record.get('proof')!=descriptor['proof']:raise ValueError('追色冻结审核凭据改变')
        return record
    def drop(self,ident):
        entry=self.entries.pop(ident,None)
        if entry is not None:
            self.used-=entry['bytes'];(self.root/(ident+'.json')).unlink(missing_ok=True)
    def bind(self,token,descriptors):self.plans[token]=[d['id'] for d in descriptors]
    def release(self,token):
        for ident in self.plans.pop(token,[]):self.drop(ident)
    def prune(self,store):
        # Reuse the existing store's TTL/eviction, never a parallel token service.
        store._prune(store.clock())
        for token in list(self.plans):
            if token not in store.pending:self.release(token)
