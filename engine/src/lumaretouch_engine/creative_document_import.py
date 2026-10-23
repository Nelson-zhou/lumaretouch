"""Real local image import retaining immutable source bytes and transparency.

8-bit Pillow inputs and genuine RGB/RGBA PNG16/TIFF16 are supported. TIFF16
uses tifffile and existing LittleCMS16, never Pillow RGB staging. Unknown/high-bit
formats fail closed; full-resolution caller-supplied linear HDR has a separate
explicit port. No browser images, thumbnails, mock bitmaps or AI provenance.
"""
from io import BytesIO
from pathlib import Path
from .creative_document_assets import make_asset, MAX_ORIGINAL_BYTES, MAX_ICC_BYTES, MAX_PIXELS


def _orient(pixels, orientation):
    import numpy as np
    if orientation == 1: return pixels
    if orientation == 2: return pixels[:,::-1]
    if orientation == 3: return pixels[::-1,::-1]
    if orientation == 4: return pixels[::-1]
    if orientation == 5: return pixels.transpose(1,0,2)
    if orientation == 6: return np.rot90(pixels,3)
    if orientation == 7: return pixels.transpose(1,0,2)[::-1,::-1]
    if orientation == 8: return np.rot90(pixels,1)
    raise ValueError('Unsupported source orientation')


def _tiff(original, max_bytes):
    import numpy as np
    import tifffile
    from .color16 import convert_rgb16
    from .export import _srgb_bytes
    with tifffile.TiffFile(BytesIO(original)) as tf:
        if len(tf.pages) != 1: raise ValueError('Select a TIFF page explicitly; creative import will not discard pages')
        page = tf.pages[0]
        if (int(page.photometric) != 2 or page.samplesperpixel not in (3,4)
                or page.dtype.kind != 'u' or page.dtype.itemsize not in (1,2)):
            raise ValueError('Creative TIFF import requires RGB/RGBA uint8 or uint16')
        w,h = int(page.imagewidth),int(page.imagelength)
        if w*h > MAX_PIXELS or len(original)*2+w*h*96 > max_bytes:
            raise ValueError('Creative TIFF decode exceeds pixel/memory budget before allocation')
        if page.samplesperpixel == 4 and tuple(int(x) for x in page.extrasamples) != (2,):
            raise ValueError('TIFF alpha must be explicitly unassociated; associated/unknown alpha is not silently reinterpreted')
        icc_tag = page.tags.get(34675); icc = bytes(icc_tag.value) if icc_tag else b''
        if len(icc) > MAX_ICC_BYTES: raise ValueError('Creative ICC budget exceeded')
        orientation_tag = page.tags.get(274); orientation = int(orientation_tag.value) if orientation_tag else 1
        pixels = page.asarray()
        if int(page.planarconfig) == 2: pixels = pixels.transpose(1,2,0)
        if pixels.shape != (h,w,page.samplesperpixel): raise ValueError('Creative TIFF sample layout mismatch')
        pixels = _orient(pixels,orientation)
        if pixels.dtype.itemsize == 2:
            rgb = np.ascontiguousarray(pixels[:,:,:3],dtype=np.uint16)
            if icc: rgb = convert_rgb16(rgb,icc,_srgb_bytes())
            alpha = pixels[:,:,3].astype(np.float32)/65535 if pixels.shape[2] == 4 else np.ones(pixels.shape[:2],dtype=np.float32)
            return rgb.astype(np.float32)/65535,alpha,icc
        # 8-bit ICC uses the same existing colour-managed Pillow path.
        from PIL import Image
        from .decode import _to_working_srgb
        rgb = np.asarray(_to_working_srgb(Image.fromarray(pixels[:,:,:3].astype(np.uint8)),icc or None),dtype=np.uint8)
        alpha = pixels[:,:,3].astype(np.float32)/255 if pixels.shape[2] == 4 else np.ones(pixels.shape[:2],dtype=np.float32)
        return rgb.astype(np.float32)/255,alpha,icc


def _png(original):
    """Reuse the existing imagecodecs + ID-background ICC/orientation contract."""
    import numpy as np
    import imagecodecs
    from PIL import Image
    from .id_background_assets import _colour_manage, _orient as orient
    if len(original) < 29 or original[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid PNG header')
    bits = original[24]
    if bits not in (1,2,4,8,16): raise ValueError('Unsupported PNG source precision')
    with Image.open(BytesIO(original)) as header:
        if getattr(header,'n_frames',1) != 1: raise ValueError('Animated PNG requires explicit frame selection')
        width,height = header.size
        icc = header.info.get('icc_profile') or b''
        if type(icc) is not bytes or len(icc) > MAX_ICC_BYTES: raise ValueError('Invalid PNG ICC profile')
        orientation = int(header.getexif().get(274,1) or 1)
    pixels = imagecodecs.png_decode(original)
    dtype = np.uint16 if bits == 16 else np.uint8
    if pixels.dtype != dtype or pixels.shape[:2] != (height,width):
        raise ValueError('PNG decoder precision/size does not match source header')
    if pixels.ndim == 2: pixels = np.repeat(pixels[:,:,None],3,axis=2)
    if pixels.ndim != 3 or pixels.shape[2] not in (2,3,4):
        raise ValueError('Unsupported PNG sample layout')
    alpha = pixels[:,:,-1] if pixels.shape[2] in (2,4) else None
    rgb = pixels[:,:,:-1] if alpha is not None else pixels
    if rgb.shape[2] == 1: rgb = np.repeat(rgb,3,axis=2)
    rgb = _colour_manage(orient(rgb,orientation),icc or None)
    maximum = 65535.0 if bits == 16 else 255.0
    if rgb.dtype != dtype: raise ValueError('PNG source precision changed during colour conversion')
    coverage = orient(alpha,orientation).astype(np.float32)/maximum if alpha is not None else np.ones(rgb.shape[:2],dtype=np.float32)
    return rgb.astype(np.float32)/maximum,coverage,icc


def _pillow(original):
    import numpy as np
    from PIL import Image, ImageOps
    from .decode import _source_bits, _to_working_srgb
    if original.startswith(b'\x89PNG\r\n\x1a\n') and len(original) > 24 and original[24] > 8:
        raise ValueError('High-bit PNG needs a true high-bit decoder; no Pillow downconversion')
    with Image.open(BytesIO(original)) as image:
        if getattr(image,'n_frames',1) != 1: raise ValueError('Creative import requires explicit frame selection for animated/multipage inputs')
        if image.width*image.height > MAX_PIXELS: raise ValueError('Creative image pixel budget exceeded')
        if _source_bits(image) > 8 or image.mode in ('I','F') or image.mode.startswith('I;16'):
            raise ValueError('High-bit source requires a lossless high-bit decoder; no 8-bit fallback')
        icc = image.info.get('icc_profile') or b''
        if type(icc) is not bytes or len(icc) > MAX_ICC_BYTES: raise ValueError('Invalid creative ICC profile')
        image.load(); oriented = ImageOps.exif_transpose(image)
        alpha = np.asarray(oriented.convert('RGBA').getchannel('A'),dtype=np.float32)/255
        rgb_image = _to_working_srgb(oriented,icc or None)
        rgb = np.asarray(rgb_image,dtype=np.float32)/255
        return rgb,alpha,icc


def import_file(path, assets, *, max_bytes=512_000_000, cancelled=lambda:False):
    """Read the user-selected source once, decode those exact retained bytes.

    max_bytes includes conservative decode/normalization/native staging buffers,
    not the existing store. File/network selection permission belongs to host.
    """
    import numpy as np
    from .creative_layer_native import linearize_rgba
    if type(max_bytes) is not int or not 1 <= max_bytes <= 4_000_000_000:
        raise ValueError('Invalid creative import memory budget')
    if cancelled(): raise InterruptedError('Creative import cancelled')
    source = Path(path)
    if not source.is_file(): raise ValueError('Creative source must be a regular file')
    size = source.stat().st_size
    if size > MAX_ORIGINAL_BYTES or size*2 > max_bytes: raise ValueError('Creative source exceeds file/memory budget')
    with source.open('rb') as handle: original = handle.read(min(MAX_ORIGINAL_BYTES,max_bytes//2)+1)
    if len(original) > min(MAX_ORIGINAL_BYTES,max_bytes//2): raise ValueError('Creative source grew past byte budget')
    return import_bytes(original,assets,max_bytes=max_bytes,cancelled=cancelled)


def import_bytes(original,assets,*,max_bytes=512_000_000,cancelled=lambda:False):
    import numpy as np
    from .creative_layer_native import linearize_rgba
    if type(original) is not bytes or not 0 < len(original) <= MAX_ORIGINAL_BYTES:
        raise ValueError('Invalid creative source bytes')
    if type(max_bytes) is not int or not 1 <= max_bytes <= 4_000_000_000:
        raise ValueError('Invalid creative import memory budget')
    if cancelled(): raise InterruptedError('Creative import cancelled')
    # Header preflight precedes full decoder allocation. TIFF uses its own header
    # reader so BigTIFF never depends on Pillow's limited TIFF mode support.
    is_tiff = original[:4] in (b'II*\x00',b'MM\x00*',b'II+\x00',b'MM\x00+')
    if not is_tiff:
        from PIL import Image
        with Image.open(BytesIO(original)) as header:
            pixels = header.width*header.height
            if pixels > MAX_PIXELS or len(original)*2+pixels*96 > max_bytes:
                raise ValueError('Creative decode exceeds memory budget before allocation')
    if is_tiff: rgb,alpha,icc = _tiff(original,max_bytes)
    elif original.startswith(b'\x89PNG\r\n\x1a\n'): rgb,alpha,icc = _png(original)
    else: rgb,alpha,icc = _pillow(original)
    if cancelled(): raise InterruptedError('Creative import cancelled')
    rgba = np.empty((*alpha.shape,4),dtype=np.float32); rgba[:,:,:3] = rgb; rgba[:,:,3] = alpha
    linear = linearize_rgba(rgba,cancelled=cancelled)
    record = make_asset('rgba',linear.shape[1],linear.shape[0],linear.astype('<f4',copy=False).tobytes(),original=original,icc=icc)
    if cancelled(): raise InterruptedError('Creative import cancelled')
    return assets.intern(record)


def import_linear_rgba(width,height,content,assets,*,original=b'',icc=b'',encoding,alpha):
    """Host full-resolution HDR/RAW port: explicit converted colour contract only."""
    if encoding != 'linear-srgb-d65' or alpha != 'premultiplied':
        raise ValueError('Host must colour-convert full pixels before creative import')
    return assets.intern(make_asset('rgba',width,height,content,original=original,icc=icc))


def import_mask(width,height,content,assets):
    """Real raster coverage in local image coordinates, not a decorative mask flag."""
    return assets.intern(make_asset('mask',width,height,content))


def import_mask_bytes(original,assets,*,max_bytes=512_000_000):
    """Coverage files are numeric grayscale, not ICC-managed image colour."""
    import numpy as np
    from PIL import Image, ImageOps
    if type(original) is not bytes or not 0 < len(original) <= 128*1024*1024:
        raise ValueError('Invalid creative mask bytes')
    with Image.open(BytesIO(original)) as image:
        if getattr(image,'n_frames',1) != 1: raise ValueError('Mask must have one frame')
        w,h = image.size
        if w*h > MAX_PIXELS or w*h*32+len(original)*2 > max_bytes:
            raise ValueError('Creative mask decode budget exceeded')
        orientation = int(image.getexif().get(274,1) or 1)
        if image.format == 'PNG':
            import imagecodecs
            pixels = imagecodecs.png_decode(original)
        elif image.format == 'TIFF':
            import tifffile
            with tifffile.TiffFile(BytesIO(original)) as tf:
                if len(tf.pages) != 1: raise ValueError('Mask TIFF must have one page')
                pixels = tf.pages[0].asarray()
        else:
            from .decode import _source_bits
            if _source_bits(image)>8: raise ValueError('Unsupported high-bit coverage codec')
            pixels = np.asarray(image)
    if pixels.dtype not in (np.uint8,np.uint16) or pixels.shape[:2] != (h,w):
        raise ValueError('Mask requires exact unsigned 8/16-bit grayscale pixels')
    if pixels.ndim == 3:
        if pixels.shape[2] not in (1,3) or (pixels.shape[2] == 3 and (not np.array_equal(pixels[:,:,0],pixels[:,:,1]) or not np.array_equal(pixels[:,:,0],pixels[:,:,2]))):
            raise ValueError('Mask must be grayscale without ambiguous colour/alpha channels')
        pixels = pixels[:,:,0]
    if pixels.ndim != 2: raise ValueError('Unsupported coverage sample layout')
    from .id_background_assets import _orient as orient
    coverage = orient(pixels,orientation).astype('<f4')/(65535 if pixels.dtype == np.uint16 else 255)
    return assets.intern(make_asset('mask',coverage.shape[1],coverage.shape[0],coverage.astype('<f4').tobytes(),original=original))
