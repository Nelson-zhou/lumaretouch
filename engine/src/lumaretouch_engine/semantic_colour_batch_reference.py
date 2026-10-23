# SPDX-License-Identifier: GPL-3.0-or-later
"""Admit private reference hydration before the existing decoder allocates pixels."""
from hashlib import sha256
import io
import zipfile
import numpy as np
from . import reference_color_assets as A
from .cpu_memory_budget import available_estimate


class ChunkReader(io.RawIOBase):
    def __init__(self,chunks):super().__init__();self.chunks=chunks;self.size=sum(x.size for x in chunks);self.position=0
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        if type(offset) is not int or type(whence) is not int:raise TypeError('样片资源读取位置必须是整数')
        destination=offset+(self.position if whence==1 else self.size if whence==2 else 0)
        if whence not in (0,1,2) or not 0<=destination<=self.size:raise ValueError('样片资源读取位置无效')
        self.position=destination;return destination
    def read(self,size=-1):
        if size is not None and type(size) is not int:raise TypeError('样片资源读取长度必须是整数')
        remaining=self.size-self.position if size is None or size<0 else min(size,self.size-self.position)
        out=[];start=0
        for part in self.chunks:
            end=start+part.size
            if self.position<end and remaining:
                begin=max(0,self.position-start);count=min(remaining,end-self.position)
                out.append(memoryview(part)[begin:begin+count]);remaining-=count;self.position+=count
            start=end
            if not remaining:break
        return b''.join(out)


def hydrate(reference,chunks):
    if chunks is None:
        from .semantic_colour_canvas import reference_admission
        reference_admission(reference);A.hydrate(reference,None);return
    if type(chunks) is not list or not 1<=len(chunks)<=40:raise ValueError('完整样片资源分块无效')
    if any(type(x) is not np.ndarray or x.dtype!=np.uint8 or x.ndim!=1 or not x.flags.c_contiguous or not 0<x.size<=7_000_000 for x in chunks):raise ValueError('完整样片资源字节块无效')
    size=sum(x.size for x in chunks)
    if size>A.MAX_BYTES or available_estimate()<2*size+128*1024*1024:raise ValueError('完整样片压缩资源内存预算不足')
    digest=sha256()
    for part in chunks:digest.update(memoryview(part))
    if digest.hexdigest()!=reference['asset_id']:raise ValueError('完整样片资源身份改变')
    with ChunkReader(chunks) as stream,zipfile.ZipFile(stream) as archive:
        entries=archive.infolist();expanded=sum(x.file_size for x in entries)
        if len(entries)!=3 or {x.filename for x in entries}!={'rgb.npy','authentic.npy','metadata.npy'} or expanded>A.MAX_RAW_BYTES:raise ValueError('完整样片展开目录无效')
    if available_estimate()<2*expanded+2*size+128*1024*1024:raise ValueError('完整样片展开内存不足，不会改用缩略图')
    A.hydrate(reference,chunks)
