"""Bounded real-operator tool-stage preview, never labelled final-chain output."""
import base64
import io
from .ops import levels as L, curves as C, hsl as H
from .quant import quantize_t
MAX_EDGE=512
MAX_PNG_BYTES=2*1024*1024

def freeze(tensor):
    import torch.nn.functional as F
    h,w=tensor.shape[-2:];scale=min(1.,MAX_EDGE/max(h,w))
    # At most 512² RGB floats; no persistent full-resolution capture allocation.
    return F.interpolate(tensor,size=(max(1,round(h*scale)),max(1,round(w*scale))),mode='bilinear',align_corners=False).clone().detach()

def render(frozen,action,channel,recipe):
    import torch
    from PIL import Image
    if action.startswith('levels_'):out=L.levels_t(frozen,L.parameters(recipe))
    elif action=='hsl':out=H.hsl_t(frozen,recipe)
    else:
        # The frozen image is already at this selected channel's input.
        # Do not apply upstream curves twice; use their existing compiled math.
        selected=C.default_curves()
        if channel=='luminance':selected.update(version=2,luminance_space=C.LUMINANCE_SPACE,luminance=recipe.get('luminance',[[0.,0.],[1.,1.]]))
        else:selected[channel]=recipe[channel]
        bundles=C.tensor_bundles(selected,frozen.device,frozen.dtype)
        if channel=='master':out=torch.stack([C._eval_t(frozen[:,i],bundles[0]) for i in range(3)],dim=1)
        elif channel=='luminance':out=C.curves_t(frozen,(None,None,None,None,bundles[4]))
        else:
            index=('red','green','blue').index(channel)
            out=torch.stack([C._eval_t(frozen[:,i],bundles[i+1]) if i==index else frozen[:,i] for i in range(3)],dim=1)
    if not torch.isfinite(out).all():raise ValueError('Tool-stage preview produced nonfinite pixels')
    pixels=quantize_t(out[0].permute(1,2,0)).contiguous().cpu().numpy()
    stream=io.BytesIO();Image.fromarray(pixels,'RGB').save(stream,format='PNG')
    data=stream.getvalue()
    if len(data)>MAX_PNG_BYTES:raise ValueError('Tool-stage preview exceeds its byte budget')
    return {'format':'png','width':int(pixels.shape[1]),'height':int(pixels.shape[0]),
            'domain':'targeted-tool-stage','quality':'bounded-proxy-float-operator','data':base64.b64encode(data).decode('ascii')}
