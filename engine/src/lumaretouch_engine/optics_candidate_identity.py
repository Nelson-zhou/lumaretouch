"""Streaming exact frozen candidate identity, including retained mask/model arrays."""
from dataclasses import fields,is_dataclass
from hashlib import sha256
import json,math,struct
import numpy as np


def fingerprint(value, *, exact=False):
    h=sha256();visited=set();nodes=0
    def token(tag,payload=b''):
        h.update(tag);h.update(struct.pack('>Q',len(payload)));h.update(payload)
    def visit(item,depth=0):
        nonlocal nodes
        nodes+=1
        if depth>64 or nodes>1_000_000:raise ValueError('目标候选状态超过身份预算')
        if isinstance(item,np.generic):item=item.item()
        if item is None:token(b'N')
        elif type(item) is bool:token(b'B',b'1' if item else b'0')
        elif type(item) is int:token(b'I',str(item).encode())
        elif type(item) is float:
            if not math.isfinite(item):raise ValueError('目标候选状态含非有限数值')
            token(b'F',struct.pack('>d',item))
        elif type(item) is str:token(b'S',item.encode())
        elif isinstance(item,(bytes,bytearray)):token(b'Y',item)
        elif isinstance(item,np.ndarray):
            if item.dtype.kind not in 'biuf':raise ValueError('目标候选数组类型不受支持')
            token(b'A',json.dumps([item.dtype.str,item.shape],separators=(',',':')).encode())
            # Buffered external loops bound temporary copies even for strided data.
            it=np.nditer(item,flags=['external_loop','buffered','zerosize_ok'],op_flags=['readonly'],order='C',buffersize=262144)
            for chunk in it:
                if not np.isfinite(chunk).all():raise ValueError('目标候选数组含非有限值')
                h.update(chunk.tobytes(order='C'))
        elif isinstance(item,(dict,list,tuple)) or is_dataclass(item):
            ident=id(item)
            if ident in visited:raise ValueError('目标候选状态包含循环')
            visited.add(ident)
            try:
                if isinstance(item,dict):
                    if any(type(k) is not str for k in item):raise ValueError('目标候选状态字典键无效')
                    from .final_canvas_flip_state import active, check
                    keys = [key for key in item if exact or key not in ('_final_canvas_flip', 'final_canvas_flip') or active(check(item[key]))]
                    token(b'D',str(len(keys)).encode())
                    for key in sorted(keys):visit(key,depth+1);visit(item[key],depth+1)
                elif is_dataclass(item):
                    token(b'C',(type(item).__module__+'.'+type(item).__qualname__).encode())
                    for field in fields(item):visit(field.name,depth+1);visit(getattr(item,field.name),depth+1)
                else:
                    token(b'L' if isinstance(item,list) else b'T',str(len(item)).encode())
                    for child in item:visit(child,depth+1)
            finally:visited.remove(ident)
        else:raise ValueError('无法冻结目标候选状态类型：'+type(item).__name__)
    visit(value)
    return h.hexdigest()
