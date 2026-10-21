"""Identified proxy-output capture lifecycle; no renderer/Engine/transport ownership.

The production command dispatcher must invalidate this controller BEFORE any
potentially image-changing command. A mapping identity alone is not a recipe ID.
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

MAX_U64=(1<<64)-1
MAX_CAPTURE_BYTES=128*1024*1024
SIZES=(1,3,5,11)
CONTEXT_KEYS=('document_id','shm_instance','width','height','presentation_width','presentation_height')


def hex_id(value):
    return type(value) is str and len(value)==32 and all(c in '0123456789abcdef' for c in value) and value!='0'*32


def u64(value):
    return (type(value) is str and value.isascii() and value.isdigit() and not value.startswith('0')
            and len(value)<=20 and 0<int(value)<=MAX_U64)


@dataclass(frozen=True)
class CapturePorts:
    document:Callable[[],dict]
    guard:Callable[[],str|None]
    render:Callable[[],dict]
    sample:Callable[[dict,tuple[int,int]],dict]


class ColorCaptureController:
    def __init__(self,ports:CapturePorts,emit:Callable[[dict],None]):
        self.ports=ports;self.emit=emit;self.generation=0;self.capture=None

    def invalidate(self):
        self.capture=None
        if self.generation>=MAX_U64:raise RuntimeError('capture generation exhausted; restart engine')
        self.generation+=1

    def _guard(self):
        why=self.ports.guard()
        if why:raise ValueError(why)

    def _context(self):
        raw=self.ports.document()
        context={key:raw.get(key) for key in CONTEXT_KEYS}
        if not u64(context.get('document_id')) or not hex_id(context.get('shm_instance')):
            raise ValueError('no identified current document')
        for key in ('width','height','presentation_width','presentation_height'):
            if type(context.get(key)) is not int or not 0<context[key]<=0xffffffff:
                raise ValueError('invalid capture geometry')
        if context['width']*context['height']*4>MAX_CAPTURE_BYTES:
            raise ValueError('proxy capture exceeds 128 MiB budget')
        return context

    def handle(self,p):
        action=p.get('action');capture_id=p.get('capture_id');ticket=p.get('ticket')
        result={'event':'color_capture','action':action if type(action) is str and len(action)<=16 else None,'capture_id':capture_id if hex_id(capture_id) else None,
                'ticket':ticket if u64(ticket) else None,'success':False,'error':None}
        if action=='sample':
            request=p.get('request_id');request_ticket=p.get('request_ticket')
            result.update(event='color_capture_sample',
                request_id=request if type(request) is str and len(request)<=128 else None,
                request_ticket=request_ticket if u64(request_ticket) else None)
        try:
            allowed={'cmd','action','capture_id','ticket','document_id'}
            if action=='sample':allowed|={'generation','request_id','request_ticket','x','y','size'}
            if set(p)-allowed or action not in ('arm','cancel','sample'):
                raise ValueError('invalid capture command or fields')
            if not hex_id(capture_id) or not u64(ticket) or not u64(p.get('document_id')):
                raise ValueError('invalid capture identity')
            if action=='arm':
                self.invalidate();self._guard();context=self._context()
                if context['document_id']!=p['document_id']:raise ValueError('document changed before capture')
                generation=self.generation
                frame=self.ports.render()
                if self.generation!=generation or self._context()!=context:raise ValueError('document geometry changed during capture')
                if frame.get('w')!=context['width'] or frame.get('h')!=context['height'] or not u64(str(frame.get('seq'))):
                    raise ValueError('rendered frame does not match capture geometry')
                self.capture={**context,'version':1,'capture_id':capture_id,'ticket':ticket,
                    'generation':str(self.generation),'seq':str(frame['seq']),
                    'domain':'proxy-output','quality':'proxy-float-output','profile':'working-srgb'}
                self.emit(frame)
                result.update(success=True,descriptor=deepcopy(self.capture))
            else:
                current=self.capture
                if current is None or any(p.get(k)!=current[k] for k in ('capture_id','ticket','document_id')):
                    raise ValueError('capture is stale or cancelled')
                if action=='cancel':
                    self.invalidate();result['success']=True
                else:
                    self._guard()
                    if p.get('generation')!=current['generation'] or self._context()!=self._document_part(current):
                        raise ValueError('capture generation or geometry changed')
                    request=p.get('request_id');request_ticket=p.get('request_ticket')
                    if type(request) is not str or not 1<=len(request)<=128 or not u64(request_ticket):
                        raise ValueError('invalid sample request identity')
                    x,y,size=p.get('x'),p.get('y'),p.get('size')
                    if type(x) is not int or type(y) is not int or type(size) is not int or size not in SIZES:
                        raise ValueError('invalid sample point or neighbourhood')
                    if not 0<=x<current['width'] or not 0<=y<current['height']:
                        raise ValueError('sample point is outside the captured image')
                    radius=size//2
                    x0=max(0,x-radius);y0=max(0,y-radius)
                    region={'x':x0,'y':y0,'width':min(current['width'],x+radius+1)-x0,
                            'height':min(current['height'],y+radius+1)-y0}
                    analysis=self.ports.sample(region,(current['width'],current['height']))
                    if self.capture is not current or self._context()!=self._document_part(current):
                        raise ValueError('capture invalidated during sampling')
                    result.update(success=True,descriptor=deepcopy(current),region=region,analysis=analysis)
        except Exception as error:result['error']=str(error)[:2000]
        self.emit(result)

    @staticmethod
    def _document_part(capture):
        return {k:capture[k] for k in CONTEXT_KEYS}
