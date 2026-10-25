"""Export validation and real memory admission, shared by both output depths."""
import os
from . import sky_replacement_state as S


def check_spec(spec):
    value=S.check(spec.sky_replacement);spec.sky_replacement=value
    if not value['enabled']:
        return
    S.ready(value)
    path,stamp=spec.sky_replacement_path,spec.sky_replacement_stamp
    if (type(path) is not str or not os.path.isabs(path) or '\x00' in path
            or type(stamp) is not list or len(stamp)!=5
            or any(type(v) is not int or v<0 for v in stamp)):
        raise ValueError('换天空导出缺少经验证的源图与解码时间戳')
    if spec.bg_matte is not None:
        raise ValueError('完整换背景会覆盖天空替换，请选择一种效果后导出')
    prepared=spec.sky_replacement_prepared
    if prepared is not None:
        source=value['source']
        if prepared['value']!=value or prepared['shape']!=(source['height'],source['width']):
            raise ValueError('天空导出准备并非当前配方或完整源尺寸')


def resident_bytes(spec):
    prepared=spec.sky_replacement_prepared
    if prepared is None:
        return 0
    arrays=[*prepared['raw_fields'].values(),*(prepared['fields'] or {}).values()]
    arrays += [prepared.get(key) for key in ('asset','reflection','tint')]
    return sum(int(v.nbytes) for i,v in enumerate(arrays) if v is not None and all(v is not old for old in arrays[:i]))


def admit_tile(spec,h,w,tile,margin,bits,device):
    """Include the 12-channel aligned float fields and real halo, not just RGB."""
    check_spec(spec)
    if not spec.sky_replacement['enabled']:
        return 0
    from .cpu_memory_budget import available_estimate
    from .optional_dependencies import optional_module
    torch=optional_module('torch')
    if torch is None:
        raise ValueError('换天空导出需要 PyTorch')
    target=torch.device(device)
    if target.type=='cuda' and not torch.cuda.is_available():
        target=torch.device('cpu')
    pixels=min(h,int(tile)+2*margin)*min(w,int(tile)+2*margin)
    # Existing filters + packed mask/RGB warp + linear compose temporaries.
    required=pixels*(1024 if bits==16 else 768)
    from .optics_state import active as optics_active
    output=h*w*(12 if bits==16 or optics_active(spec.optics) else 3)*int(spec.scale)**2
    output+=h*w*(12 if spec.repair else 0)+h*w*(4 if spec.fabric_amount else 0)+h*w*(196 if spec.fabric_sweat else 0)+h*w*(196 if spec.limb_vein else 0)
    reserve=64*1024**2
    # Already prepared source/asset arrays are included in available_estimate's
    # resident usage; do not falsely regard proxy storage as reusable export RGB.
    cpu=output+(required if target.type=='cpu' else pixels*64)+reserve
    if cpu>available_estimate():
        raise ValueError('全尺寸换天空和输出缓冲超过可用内存，请减少瓦片尺寸或释放内存；不降位导出')
    if target.type=='cuda':
        free,_=torch.cuda.mem_get_info(target)
        if required+reserve>free*.8:
            raise ValueError('换天空浮点瓦片及其真实 halo 超过显存预算，请减小导出瓦片尺寸')
    return required


def admit_stage(device,shape):
    """Bound sampling, resident arrays and the packed warp before allocations."""
    from .cpu_memory_budget import available_estimate
    from .optional_dependencies import optional_module
    torch=optional_module('torch')
    if torch is None: raise ValueError('换天空需要 PyTorch')
    target=torch.device(device); pixels=int(shape[0])*int(shape[1]); reserve=64*1024**2
    if pixels*(768 if target.type=='cpu' else 128)+reserve>available_estimate():
        raise ValueError('换天空的真实预览/瓦片及浮点缓冲超过内存预算，请减小代理或瓦片尺寸')
    if target.type=='cuda':
        free,_=torch.cuda.mem_get_info(target)
        if pixels*768+reserve>free*.8:
            raise ValueError('换天空预览/瓦片的区域与浮点形变超过显存预算，请减小代理或瓦片尺寸')
