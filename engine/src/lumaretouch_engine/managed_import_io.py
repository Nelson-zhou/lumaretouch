"""Bounded read-only originals and exclusive managed copies (Linux dirfd API).

No decoder/model work here. Copies are published with link(O_EXCL semantics), not
replace: collisions always fail, even when bytes happen to match another source.
"""
from __future__ import annotations
import hashlib
import os
import stat
import time
import uuid
from pathlib import Path
from .source_relocation_io import open_directory, open_regular, signature
from .export_destination_import import origin

MAX_FILES = 512
MAX_ENTRIES = 10000
MAX_BYTES = 16 * 1024**3
MAX_FILE_BYTES = 2 * 1024**3
MAX_SECONDS = 300
CHUNK = 1024 * 1024
RESERVE = 64 * 1024**2

class Budget:
    def __init__(self, cancelled, progress):
        self.cancelled, self.progress = cancelled, progress
        self.started, self.bytes, self.total, self.entries = time.monotonic(), 0, 0, 0
    def check(self):
        if self.cancelled(): raise InterruptedError('导入已取消，原图保持不变')
        if time.monotonic()-self.started > MAX_SECONDS: raise TimeoutError('导入达到 300 秒上限，请分批选择')
        if self.entries > MAX_ENTRIES or self.total > MAX_BYTES: raise ValueError('导入超过 10,000 目录项或 16 GiB 上限')
    def report(self, phase, amount=0):
        self.bytes += amount
        self.check()
        self.progress({'phase':phase, 'bytes':self.bytes, 'total':self.total})

def select(paths, extensions, budget):
    if not isinstance(paths,list) or not 1 <= len(paths) <= MAX_FILES or any(not isinstance(p,str) for p in paths):
        raise ValueError('请选择 1–512 个文件或目录')
    found = {}
    def add(path, root, kind, st):
        if Path(path).suffix.lower() not in extensions: raise ValueError('不支持的图片格式：'+path)
        if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= MAX_FILE_BYTES: raise ValueError('需要非空普通文件，单文件最多 2 GiB')
        record = {'source':path,'origin':origin(path,root,kind=kind),'size':st.st_size,'signature':list(signature(st))}
        if path in found:
            if found[path]['origin'] != record['origin']: raise ValueError('选择目录重叠，请只选择一个层级')
            return
        found[path] = record
        budget.total += st.st_size
        if len(found)>MAX_FILES: raise ValueError('一次最多导入 512 张')
        budget.check()
    def walk(fd, path, root, depth):
        if depth > 16: raise ValueError('目录深度超过 16 层')
        with os.scandir(fd) as entries:
            for entry in entries:
                budget.entries += 1; budget.check()
                st = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode): raise ValueError('目录含符号链接，请单独选择普通图片：'+entry.name)
                childpath = os.path.join(path,entry.name)
                if stat.S_ISDIR(st.st_mode):
                    child = os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                    try: walk(child,childpath,root,depth+1)
                    finally: os.close(child)
                elif Path(entry.name).suffix.lower() in extensions:
                    add(childpath,root,'directory',st)
    for path in paths:
        budget.check()
        # open_directory/open_regular enforce absolute canonical paths and reject ALL symlink ancestors.
        try: fd = open_directory(path)
        except NotADirectoryError:
            fd = open_regular(path)
            try: add(path,os.path.dirname(path),'file',os.fstat(fd))
            finally: os.close(fd)
        else:
            try: walk(fd,path,path,0)
            finally: os.close(fd)
    if not found: raise ValueError('选择中没有支持的图片')
    return [found[key] for key in sorted(found)]

def digest_fd(fd,budget,phase):
    digest,head,count = hashlib.sha256(),bytearray(),0
    os.lseek(fd,0,os.SEEK_SET)
    while True:
        budget.check()
        block = os.read(fd,CHUNK)
        if not block: break
        count += len(block)
        if count>MAX_FILE_BYTES: raise ValueError('读取中源文件超出大小上限')
        digest.update(block)
        if len(head)<4096: head.extend(block[:4096-len(head)])
        budget.report(phase,len(block))
    return digest.hexdigest(), hashlib.sha256(head).hexdigest(), count

def prepare(item, root_fd, root, operation, budget):
    source = open_regular(item['source'])
    temp = None
    try:
        before = os.fstat(source)
        if list(signature(before)) != item['signature']: raise ValueError('源文件变化，请重新选择')
        if root_fd is None:
            sha,head,count = digest_fd(source,budget,'verifying')
            target = item['source']
        else:
            free = os.fstatvfs(root_fd)
            if free.f_bavail*free.f_frsize < item['size']+RESERVE: raise OSError('目标剩余空间不足（保留 64 MiB 安全空间）')
            name = str(uuid.uuid5(uuid.UUID(operation),item['source']))+Path(item['source']).suffix.lower()
            temp = '.lrt-import-'+uuid.uuid4().hex+'.partial'
            out = os.open(temp,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600,dir_fd=root_fd)
            try:
                digest,headbytes,count = hashlib.sha256(),bytearray(),0
                while True:
                    budget.check()
                    block = os.read(source,CHUNK)
                    if not block: break
                    count += len(block)
                    if count>item['size']: raise ValueError('复制时源文件变大')
                    digest.update(block)
                    if len(headbytes)<4096: headbytes.extend(block[:4096-len(headbytes)])
                    view = memoryview(block)
                    while view:
                        written = os.write(out,view)
                        if written<=0: raise OSError('复制写入没有进展')
                        view = view[written:]
                    budget.report('copying',len(block))
                os.fsync(out)
                sha,head,verified = digest_fd(out,budget,'verifying')
                if sha!=digest.hexdigest() or verified!=count or head!=hashlib.sha256(headbytes).hexdigest(): raise ValueError('复制内容校验失败')
                os.fchmod(out,0o444)
                os.fsync(out)
            finally: os.close(out)
            target = os.path.join(root,name)
        if count!=item['size'] or signature(before)!=signature(os.fstat(source)): raise ValueError('读取期间源文件变化')
        check = open_regular(item['source'])
        try:
            if signature(os.fstat(check))!=signature(before): raise ValueError('读取期间源路径变化')
        finally: os.close(check)
        budget.check()
        if root_fd is not None:
            current = open_directory(root)
            try:
                if (os.fstat(current).st_dev,os.fstat(current).st_ino)!=(os.fstat(root_fd).st_dev,os.fstat(root_fd).st_ino): raise ValueError('托管目录已变化')
            finally: os.close(current)
            os.link(temp,name,src_dir_fd=root_fd,dst_dir_fd=root_fd,follow_symlinks=False)
            os.unlink(temp,dir_fd=root_fd); temp = None
            os.fsync(root_fd)
        return {**item,'path':target,'sha256':sha,'fingerprint':{'path':target,'sha256':sha,'head_sha256':head,'hash_level':'full','bytes':count,'mtime_ns':os.stat(target,follow_symlinks=False).st_mtime_ns,'readonly':root_fd is not None}}
    finally:
        os.close(source)
        if temp is not None:
            try: os.unlink(temp,dir_fd=root_fd)
            except OSError: pass
