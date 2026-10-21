"""Optional per-slot presentation metadata, committed atomically with its pixels.

This describes composition/aspect, not an inverse transform or semantic alignment.
Unknown/legacy slot extensions are display-only; no latest-document substitution.
"""
from dataclasses import dataclass
import hashlib
import json
import struct

TAG=b'LPR1'
WIRE=struct.Struct('<4sQIIQII')
KINDS={'edited':1,'original':2,'preview':3,'synthetic':4}

@dataclass(frozen=True)
class Presentation:
    document:int
    width:int
    height:int
    geometry:int
    kind:int

    def pack(self):
        if type(self.document) is not int or not 0<=self.document<(1<<64):raise ValueError('invalid presentation document')
        if self.kind not in KINDS.values() or (self.document==0 and self.kind!=KINDS['synthetic']):raise ValueError('invalid presentation kind/document')
        if any(type(v) is not int or not 0<v<=0xffffffff for v in (self.width,self.height)):raise ValueError('invalid presentation dimensions')
        if type(self.geometry) is not int or not 0<self.geometry<(1<<64):raise ValueError('invalid geometry identity')
        return WIRE.pack(TAG,self.document,self.width,self.height,self.geometry,self.kind,0)


def parse(data):
    if len(data)!=36:raise ValueError('invalid presentation slot size')
    if data[:4]!=TAG:return None
    _,document,width,height,geometry,kind,flags=WIRE.unpack(data)
    if flags:raise ValueError('unsupported presentation flags')
    value=Presentation(document,width,height,geometry,kind);value.pack();return value


def make(document,source,rect=(0.,0.,1.,1.),rotation=0.,kind='edited'):
    if kind not in KINDS:raise ValueError('unknown presentation kind')
    width,height=map(int,source)
    if width<1 or height<1:raise ValueError('invalid presentation source')
    if kind=='edited':
        from .ops.geometry import out_size,is_identity
        output=out_size(width,height,tuple(rect),float(rotation))
        recipe=([width,height,'uncropped'] if is_identity(rect,rotation) else [width,height,list(rect),float(rotation)])
    else:output=(width,height);recipe=[width,height,'uncropped']
    digest=hashlib.blake2b(json.dumps(recipe,separators=(',',':'),allow_nan=False).encode(),digest_size=8).digest()
    result=Presentation(int(document),int(output[0]),int(output[1]),int.from_bytes(digest,'little') or 1,KINDS[kind])
    result.pack();return result
