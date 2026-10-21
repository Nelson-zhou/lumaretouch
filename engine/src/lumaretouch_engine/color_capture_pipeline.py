"""Adapters between identified capture policy and the existing proxy renderer."""
from .color_scopes_sampling import gather
from .color_scopes_bridge import analyze


def document_context(document_id,shm,crop):
    presentation=crop.get('out_full') or crop.get('out') or crop.get('crop_out')
    if not presentation or len(presentation)!=2:raise ValueError('capture presentation geometry unavailable')
    return {'document_id':document_id,'shm_instance':shm.instance_id.hex() if shm.instance_id else None,
            'width':shm.w,'height':shm.h,'presentation_width':int(presentation[0]),'presentation_height':int(presentation[1])}


def sample_output(pipeline,strength,channel,params,region,expected_size):
    if tuple(expected_size)!=(pipeline.w,pipeline.h):raise ValueError('capture raster changed')
    x,y,w,h=(region[k] for k in ('x','y','width','height'))
    if any(type(v) is not int for v in (x,y,w,h)) or x<0 or y<0 or w<1 or h<1 or w*h>121:
        raise ValueError('invalid capture neighbourhood')
    if x+w>pipeline.w or y+h>pipeline.h:raise ValueError('capture neighbourhood outside image')
    samples=[]
    def tap(stage,tensor):
        if stage!='output':return
        if (int(tensor.shape[-1]),int(tensor.shape[-2]))!=tuple(expected_size):raise ValueError('capture output shape changed')
        samples.append(gather(tensor[:,:,y:y+h,x:x+w]))
    pipeline.retouch(strength,channel=channel,scope_tap=tap,**params)
    if len(samples)!=1:raise RuntimeError('capture sample stage unavailable')
    return analyze(samples[0])
