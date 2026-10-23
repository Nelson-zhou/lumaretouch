"""Frozen local ID backgrounds: immutable bytes and ICC-aware full RGB assets.

Only user-selected files are decoded. No downloads, stock bundles or models.
RGB16 PNG/TIFF remain genuine 16-bit through ICC conversion. Unassociated
asset alpha is retained and flattened only over the explicitly selected base. Linear float pixels are render data,
not a claim that an 8-bit input acquired additional source precision.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import tempfile
import numpy as np
from . import id_background_state as S, local_mask_state as M

CHUNK = 7_000_000
SUFFIXES = ('.jpg','.jpeg','.png','.tif','.tiff','.bmp')


@dataclass(frozen=True)
class IDBackgroundAsset:
    binding: dict
    pixels: np.ndarray
    content: bytes
    stamp: tuple | None
    alpha: np.ndarray | None = None


def inspect_path(path):
    if type(path) is not str or not os.path.isabs(path) or len(path) > 4096 or '\x00' in path:
        raise ValueError('请选择本地背景素材文件')
    if Path(path).suffix.lower() not in SUFFIXES:
        raise ValueError('背景素材支持 JPG、PNG、TIF、BMP')
    if not os.path.isfile(path) or not 0 < os.stat(path).st_size <= S.MAX_ASSET_BYTES:
        raise ValueError('背景素材必须是普通文件，且不超过 10 MB（10,000,000 字节）')
    return M.file_stamp(path)


def _decode(content, path, *, expected=None, cancelled=lambda:False, stamp=None):
    from PIL import Image
    from .decode import _source_bits, _refuse_multipage
    from .cpu_memory_budget import available_estimate
    if type(content) is not bytes or not 0 < len(content) <= S.MAX_ASSET_BYTES:
        raise ValueError('背景素材原始字节缺失或超过 10 MB')
    digest = sha256(content).hexdigest()
    if expected is not None:
        expected = S.asset(expected)
        if expected['sha256'] != digest or expected['path'] != path:
            raise ValueError('背景素材内容或选择身份改变')
    if cancelled(): raise InterruptedError('背景素材读取已取消')
    with Image.open(BytesIO(content)) as image:
        if image.format not in ('JPEG','PNG','TIFF','BMP'):
            raise ValueError('文件内容不是支持的 JPG/PNG/TIF/BMP 素材')
        _refuse_multipage(image,path)
        w,h = image.size
        if w*h > S.MAX_ASSET_PIXELS or max(w,h) >= 32767:
            raise ValueError('背景素材超过 3200 万像素或坐标预算；不会缩小后冒充原件')
        if w*h*80+32*1024**2 > max(0,available_estimate()-256*1024**2)*.65:
            raise ValueError('背景素材完整解码内存预算不足')
        bits = _source_bits(image)
        suffix = {'JPEG':'.jpg','PNG':'.png','TIFF':'.tif','BMP':'.bmp'}[image.format]
        if image.format == 'PNG' and len(content) >= 29 and content[:8] == b'\x89PNG\r\n\x1a\n':
            bits = content[24]
        source_icc = image.info.get('icc_profile') or None
        orientation = int(image.getexif().get(274,1) or 1)
        image_format = image.format
        has_alpha = 'A' in image.getbands() or 'transparency' in image.info
        if bits not in (1,2,4,8,16):
            raise ValueError('背景素材位深暂不支持')
    alpha = None
    if image_format == 'PNG':
        # Existing pinned imagecodecs/libpng dependency, BSD-3-Clause wrapper.
        # png_decode preserves u16 RGB/RGBA instead of Pillow's RGB8 conversion.
        import imagecodecs
        pixels = imagecodecs.png_decode(content)
        if pixels.dtype != (np.uint16 if bits > 8 else np.uint8) or pixels.shape[:2] != (h,w):
            raise ValueError('PNG 解码位深或尺寸与文件头不符')
        if pixels.ndim == 2: pixels = np.repeat(pixels[:,:,None],3,axis=2)
        if pixels.ndim != 3 or pixels.shape[2] not in (2,3,4):
            raise ValueError('PNG 通道布局不支持')
        if pixels.shape[2] in (2,4):
            alpha = pixels[:,:,-1].copy()
            pixels = pixels[:,:,:-1]
        if pixels.shape[2] == 1: pixels = np.repeat(pixels,3,axis=2)
        pixels = _orient(pixels,orientation)
        if alpha is not None: alpha = _orient(alpha,orientation)
        pixels = _colour_manage(pixels,source_icc)
    elif image_format == 'TIFF':
        import tifffile
        with tifffile.TiffFile(BytesIO(content)) as archive:
            page = archive.pages[0]
            if len(archive.pages) != 1: raise ValueError('背景素材不支持多页 TIFF')
            if int(page.photometric) == 2 and page.samplesperpixel in (3,4):
                if page.dtype.kind != 'u' or page.dtype.itemsize not in (1,2):
                    raise ValueError('RGB TIFF 背景要求 uint8 或真实 uint16')
                if (int(page.imagewidth),int(page.imagelength)) != (w,h):
                    raise ValueError('TIFF 解码尺寸与文件头不符')
                if page.samplesperpixel == 4 and tuple(int(v) for v in page.extrasamples) != (2,):
                    raise ValueError('TIFF 透明通道需明确为非预乘 alpha；不猜测额外通道含义')
                pixels = page.asarray()
                if int(page.planarconfig) == 2: pixels = pixels.transpose(1,2,0)
                if pixels.shape != (h,w,page.samplesperpixel): raise ValueError('TIFF 像素布局不符')
                pixels = pixels.astype(np.uint16 if page.dtype.itemsize==2 else np.uint8,copy=False)
                if page.samplesperpixel == 4:
                    alpha = pixels[:,:,3].copy(); pixels = pixels[:,:,:3]
                pixels = _orient(pixels,orientation)
                if alpha is not None: alpha = _orient(alpha,orientation)
                pixels = _colour_manage(pixels,source_icc)
            else:
                if bits > 8: raise ValueError('高位深 TIFF 背景要求 RGB/RGBA；不静默降位')
                if has_alpha: raise ValueError('带透明通道的 TIFF 背景要求 RGB/RGBA，不丢弃灰度或其它额外通道')
                pixels = _decode_pillow_snapshot(content,suffix,S.MAX_ASSET_PIXELS)
    else:
        if has_alpha:
            from PIL import ImageOps
            with Image.open(BytesIO(content)) as picture:
                picture = ImageOps.exif_transpose(picture)
                alpha = np.asarray(picture.convert('RGBA').getchannel('A'),dtype=np.uint8).copy()
                pixels = _colour_manage(np.asarray(picture.convert('RGB'),dtype=np.uint8),source_icc)
        else:
            pixels = _decode_pillow_snapshot(content,suffix,S.MAX_ASSET_PIXELS)
    if pixels.dtype not in (np.uint8,np.uint16) or pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError('背景素材没有生成真实 RGB 像素')
    if bits > 8 and pixels.dtype != np.uint16:
        raise ValueError('高位深背景素材被降位；拒绝继续')
    original_bits = 16 if pixels.dtype == np.uint16 else 8
    value = pixels.astype(np.float32) / (65535. if original_bits == 16 else 255.)
    linear = np.where(value <= .04045,value/12.92,((value+.055)/1.055)**2.4).astype('<f4')
    # bytes-backed array cannot regain WRITEABLE via setflags(True).
    raw_pixels = np.ascontiguousarray(linear).tobytes()
    linear = np.frombuffer(raw_pixels,dtype='<f4').reshape(linear.shape)
    if alpha is not None:
        af = np.ascontiguousarray(alpha.astype(np.float32)/(65535. if original_bits==16 else 255.),dtype='<f4')
        alpha = np.frombuffer(af.tobytes(),dtype='<f4').reshape(af.shape)
    binding = S.asset({'path':path,'sha256':digest,'width':pixels.shape[1],'height':pixels.shape[0],
        'bits':original_bits,'working_color':'linear-srgb-f32',
        'icc_sha256':sha256(source_icc).hexdigest() if source_icc else None,
        'alpha_sha256':sha256(alpha.tobytes()).hexdigest() if alpha is not None else None,
        'pixels_sha256':sha256(raw_pixels).hexdigest()})
    if expected is not None and binding != expected:
        raise ValueError('背景素材颜色管理、位深、尺寸或像素摘要不一致')
    if cancelled(): raise InterruptedError('背景素材读取已取消')
    return IDBackgroundAsset(binding,linear,content,stamp,alpha)


def _orient(array,orientation):
    if orientation not in range(1,9): raise ValueError('背景素材方向标签无效')
    if orientation == 2: return array[:,::-1]
    if orientation == 3: return array[::-1,::-1]
    if orientation == 4: return array[::-1]
    if orientation == 5: return array.swapaxes(0,1)
    if orientation == 6: return np.rot90(array,-1)
    if orientation == 7: return array.swapaxes(0,1)[::-1,::-1]
    if orientation == 8: return np.rot90(array,1)
    return array


def _colour_manage(pixels,icc):
    if not icc: return np.ascontiguousarray(pixels)
    if pixels.dtype == np.uint16:
        from .color16 import convert_rgb16
        from .export import _srgb_bytes
        return convert_rgb16(np.ascontiguousarray(pixels),icc,_srgb_bytes())
    from PIL import Image
    from .decode import _to_working_srgb
    return np.ascontiguousarray(_to_working_srgb(Image.fromarray(pixels),icc),dtype=np.uint8)


def _decode_pillow_snapshot(content,suffix,max_pixels):
    from .decode import load_full
    with tempfile.TemporaryDirectory(prefix='lrt-id-background-') as directory:
        frozen = os.path.join(directory,'asset'+suffix)
        with open(frozen,'xb') as stream: stream.write(content)
        return load_full(frozen,max_px=max_pixels,want_bits=8).rgb


def flatten(value,base):
    """Linear-light source-over; selected base is explicit and never baked in the bundle."""
    if not isinstance(value,IDBackgroundAsset): raise ValueError('需要验证后的背景素材')
    base = np.asarray(S.colour(base),dtype=np.float32)/255.
    base = np.where(base<=.04045,base/12.92,((base+.055)/1.055)**2.4)
    if value.alpha is None: return value.pixels
    return np.ascontiguousarray(value.pixels*value.alpha[:,:,None]+base*(1-value.alpha[:,:,None]),dtype=np.float32)


def read(path,*,expected=None,cancelled=lambda:False):
    before = inspect_path(path)
    with open(path,'rb') as stream: content = stream.read(S.MAX_ASSET_BYTES+1)
    if M.file_stamp(path) != before: raise ValueError('背景素材读取期间发生变化')
    return _decode(content,path,expected=expected,cancelled=cancelled,stamp=before)


def pack(value):
    if not isinstance(value,IDBackgroundAsset): raise ValueError('需要已经验证的背景素材')
    return check_bundle({'binding':value.binding,'content':[value.content[i:i+CHUNK] for i in range(0,len(value.content),CHUNK)]})


def check_bundle(raw):
    if raw is None: return None
    if type(raw) is not dict or set(raw) != {'binding','content'}:
        raise ValueError('背景素材持久化包字段无效')
    binding = S.asset(raw['binding'])
    chunks = raw['content']
    if (binding is None or type(chunks) is not list or not 1 <= len(chunks) <= 2
            or any(type(v) is not bytes or not 0 < len(v) <= CHUNK for v in chunks)
            or sum(map(len,chunks)) > S.MAX_ASSET_BYTES
            or (len(chunks)==2 and len(chunks[0]) != CHUNK)):
        raise ValueError('背景素材持久化原始字节或分块预算无效')
    h = sha256()
    for chunk in chunks: h.update(chunk)
    if h.hexdigest() != binding['sha256']:
        raise ValueError('背景素材持久化字节摘要不一致')
    return {'binding':binding,'content':chunks[:]}


def unpack(raw,*,cancelled=lambda:False):
    value = check_bundle(raw)
    if value is None: return None
    return _decode(b''.join(value['content']),value['binding']['path'],expected=value['binding'],cancelled=cancelled)


def verify(raw):
    value = S.asset(raw)
    if value is None: return None
    before = inspect_path(value['path'])
    if M.source_digest(value['path']) != value['sha256'] or M.file_stamp(value['path']) != before:
        raise ValueError('外部背景素材改变；不会以同名文件替换项目冻结素材')
    return before


def relink(raw,path,*,cancelled=lambda:False):
    old = S.asset(raw)
    if old is None: raise ValueError('没有需要重新定位的背景素材')
    new = read(path,cancelled=cancelled)
    if {k:v for k,v in old.items() if k!='path'} != {k:v for k,v in new.binding.items() if k!='path'}:
        raise ValueError('重新定位的素材不是相同原件；请选择新素材')
    return new
