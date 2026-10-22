"""Read-only Linux budget snapshot, not an allocation/OOM guarantee.

Only a fully visible, unambiguous cgroup v2 hierarchy is supported. Hidden ancestor
limits, v1/hybrid mounts and read failures fail closed, never fall back to host RAM.
"""
import os
import re
from pathlib import Path


def available_estimate(proc=Path('/proc')):
    def fail(reason):
        raise ValueError('Cannot establish CPU memory budget: '+reason)
    def read(path):
        with path.open('rb') as handle:
            data=handle.read(1024*1024+1)
        if len(data)>1024*1024:
            fail('oversized memory metadata')
        return data.decode('utf-8')
    def uint(text):
        if not re.fullmatch(r'[0-9]{1,20}',text):
            fail('invalid memory counter')
        return int(text)
    def unescape(text):
        return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),text)
    try:
        membership=read(proc/'self/cgroup');lines=membership.splitlines()
        if len(lines)!=1 or not lines[0].startswith('0::'):
            fail('v1, hybrid or unknown cgroup layout')
        group=lines[0][3:]
        if not group.startswith('/') or any(p in ('.','..') for p in group.split('/')):
            fail('cgroup path outside visible hierarchy')
        mountinfo=read(proc/'self/mountinfo');mounts=[]
        for line in mountinfo.splitlines():
            left,sep,right=line.partition(' - ');a,b=left.split(),right.split()
            if not sep or len(a)<6 or len(b)<3:
                fail('invalid mountinfo')
            mounts.append((unescape(a[3]),Path(unescape(a[4])),b[0],a[2]))
        cg=[m for m in mounts if m[2]=='cgroup2']
        if len(cg)!=1 or cg[0][0]!='/':
            fail('ambiguous or subtree-only cgroup2 mount')
        _,root,_,device=cg[0]
        if not root.is_absolute():
            fail('invalid cgroup2 mount path')
        if any(m!=cg[0] and (m[1]==root or root in m[1].parents) for m in mounts):
            fail('overlaid cgroup hierarchy')
        major,minor=map(int,device.split(':'))
        if root.stat().st_dev!=os.makedev(major,minor):
            fail('cgroup mount changed')
        if 'memory' not in read(root/'cgroup.controllers').split():
            fail('memory controller unavailable at visible root')
        for name in ('memory.max','memory.current'):
            try:
                (root/name).stat()
            except FileNotFoundError:
                pass
            else:
                fail('ancestor memory limits are hidden')
        host=None
        for line in read(proc/'meminfo').splitlines():
            fields=line.split()
            if fields and fields[0]=='MemAvailable:':
                if len(fields)!=3 or fields[2]!='kB':
                    fail('invalid MemAvailable')
                host=uint(fields[1])*1024
        if host is None:
            fail('MemAvailable unavailable')
        available=host
        node=root.joinpath(*group.strip('/').split('/')) if group!='/' else root
        while node!=root:
            limit=read(node/'memory.max').strip();used=uint(read(node/'memory.current').strip())
            if limit!='max':
                available=min(available,max(0,uint(limit)-used))
            node=node.parent
        if read(proc/'self/cgroup')!=membership or read(proc/'self/mountinfo')!=mountinfo:
            fail('cgroup membership or mount layout changed; retry')
        return available
    except (OSError,UnicodeError) as error:
        raise ValueError('Cannot read CPU memory budget') from error
