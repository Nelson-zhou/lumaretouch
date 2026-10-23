# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded fsync/atomic per-engine-epoch arm receipts, never a replay queue.

The private journal survives lost notifications in this engine. A process restart
has a new document epoch and must not resend the old request. Project/history own
retained edits; this journal does not infer that an uncertain render succeeded.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from . import body_pose_evidence as E


class ArmReceiptJournal:
    def __init__(self):
        self.directory=tempfile.TemporaryDirectory(prefix='lumaretouch-arm-receipts-')
        self.root=Path(self.directory.name);self.entries={};self.bytes=0

    def get(self,request_id):
        E.token(request_id);entry=self.entries.get(request_id)
        if entry is None:return None
        path=self.root/entry['name']
        if path.stat().st_size!=entry['size']:raise ValueError('Retained arm receipt journal size changed')
        with path.open('rb') as stream:raw=stream.read(entry['size']+1)
        if len(raw)!=entry['size'] or sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Retained arm receipt journal changed')
        value=json.loads(raw)
        if value['request_id']!=request_id:raise ValueError('Arm journal receipt identity differs')
        return deepcopy({k:value[k] for k in ('digest','result')})

    def put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest);old=self.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Arm request identity cannot be reused')
        if old is not None and old['result'].get('phase')=='done' and not old['result'].get('outcome_unknown') and old['result']!=result:
            raise ValueError('A confirmed arm receipt cannot regress or change')
        raw=json.dumps({'request_id':request_id,'digest':digest,'result':result},sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        prior=self.entries.get(request_id);used=0 if prior is None else prior['size']
        if len(raw)>8*1024*1024 or (prior is None and len(self.entries)>=4096) or self.bytes-used+len(raw)>128*1024*1024:raise ValueError('Arm receipt journal budget exhausted before write')
        name=sha256(request_id.encode()).hexdigest()+'.json';target=self.root/name;partial=self.root/(name+'.pending')
        try:
            with partial.open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
            os.replace(partial,target)
            # The atomic rename is now observable. Update our content index
            # before durability sync, which can fail after a completed write.
            self.entries[request_id]={'name':name,'size':len(raw),'sha256':sha256(raw).hexdigest()};self.bytes=self.bytes-used+len(raw)
            fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:partial.unlink(missing_ok=True)

    def close(self):self.directory.cleanup()
