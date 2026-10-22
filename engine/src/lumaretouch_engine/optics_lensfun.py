"""Real optional Lensfun calibration, deterministic local DB, no network access.

Lensfun creates inverse per-channel coordinates and source-linear gains. The
Rust raster core consumes those coordinates; a database match alone is never
reported as applied correction. Missing/ambiguous metadata remains visible.
"""
import importlib
import importlib.metadata
import os
from pathlib import Path
from hashlib import sha256
import numpy as np
from . import optics_state as S

MAX_DB_BYTES = 32*1024*1024


def database():
    directory = os.environ.get('LRT_LENSFUN_DB')
    if not directory: raise RuntimeError('镜头数据库未配置；可使用手动畸变/暗角。需要显式安装 Lensfun 数据包并设置 LRT_LENSFUN_DB')
    root = Path(directory)
    if not root.is_dir() or root.is_symlink(): raise ValueError('镜头数据库必须是本地真实目录')
    files = sorted(root.glob('*.xml'))
    if not files or len(files) > 4096: raise ValueError('镜头数据库缺少 XML 或超过数量限制')
    digest = sha256(); total = 0
    stamps = []
    for path in files:
        if path.is_symlink() or not path.is_file(): raise ValueError('镜头数据库不接受符号链接')
        before = path.stat(); total += before.st_size
        if before.st_size > 8*1024*1024 or total > MAX_DB_BYTES: raise ValueError('镜头数据库超过 32 MiB 预算')
        data = path.read_bytes()
        digest.update(path.name.encode()); digest.update(b'\0'); digest.update(data)
        stamps.append((path, before.st_size, before.st_mtime_ns))
    try: module = importlib.import_module('lensfunpy')
    except ImportError as error: raise RuntimeError('Lensfun 可选库未安装；手动调整仍可使用，不会自动安装') from error
    db = module.Database(paths=[str(p) for p in files], load_common=False, load_bundled=False)
    if any((p.stat().st_size, p.stat().st_mtime_ns) != (size, stamp) for p,size,stamp in stamps):
        raise ValueError('镜头数据库在加载时变化')
    version = 'lensfun:'+'.'.join(str(v) for v in module.lensfun_version)+';lensfunpy:'+importlib.metadata.version('lensfunpy')
    return module, db, digest.hexdigest(), version


def metadata(decoded, path=None):
    """Read only lens/camera tags; RAW can use explicitly installed ExifTool."""
    raw = getattr(decoded,'raw',None) or {}
    is_raw = bool(raw) and raw.get('source')!='tiff16'
    result = {'is_raw':is_raw,'camera_maker':'','camera_model':'','lens_maker':'','lens_model':'',
              'focal':None,'aperture':None,'distance':None,'orientation':1,'note':''}
    if is_raw and raw.get('used_preview'): result['note'] = '当前为内嵌预览，不能证明未做过相机镜头校正'
    tags = {}
    if getattr(decoded,'source_exif',None):
        from PIL import Image
        try:
            exif = Image.Exif(); exif.load(decoded.source_exif)
            tags = {**dict(exif), **exif.get_ifd(0x8769)}
        except (ValueError,TypeError,KeyError): result['note'] += ' EXIF 镜头字段无法完整读取'
    if is_raw and path:
        try:
            from .optics_metadata import read
            found = read(path)
            for key,tag in (('Make',271),('Model',272),('LensMake',42035),('LensModel',42036),('FocalLength',37386),('FNumber',33437),('SubjectDistance',37382),('Orientation',274)):
                if key in found: tags[tag] = found[key]
        except Exception as error: result['note'] += str(error)
    for key,tag in (('camera_maker',271),('camera_model',272),('lens_maker',42035),('lens_model',42036)):
        if tags.get(tag): result[key] = str(tags[tag]).strip('\0 ')[:512]
    for key,tag in (('focal',37386),('aperture',33437),('distance',37382)):
        try:
            value = float(tags.get(tag,0))
            if np.isfinite(value) and value>0: result[key] = value
        except (TypeError,ValueError,ZeroDivisionError): pass
    if tags.get(274) in range(1,9): result['orientation'] = int(tags[274])
    return result


def candidates(meta):
    module, db, digest, version = database()
    if not meta.get('camera_model'): raise ValueError('照片没有可识别的相机型号，请手动选择相机/镜头')
    cameras = db.find_cameras(meta.get('camera_maker') or None, meta['camera_model'], loose_search=False)
    result = []
    for cam in cameras:
        for lens in db.find_lenses(cam, meta.get('lens_maker') or None, meta.get('lens_model') or None, loose_search=False):
            if len(result) >= 100: raise ValueError('匹配过多，请填写更完整的镜头型号')
            result.append({'camera_maker': cam.maker, 'camera_model': cam.model, 'camera_variant': cam.variant or '',
                           'lens_maker': lens.maker, 'lens_model': lens.model, 'crop': float(cam.crop_factor),
                           'database_sha256': digest, 'library_version': version})
    return result


def resolve(candidate, meta, shape):
    """Probe real calibration branches before retaining any active profile."""
    module, db, digest, version = database()
    if candidate.get('database_sha256') != digest or candidate.get('library_version') != version:
        raise ValueError('镜头库或版本已变化，请重新选择配置')
    cams = [c for c in db.find_cameras(candidate['camera_maker'],candidate['camera_model']) if
            c.maker == candidate['camera_maker'] and c.model == candidate['camera_model'] and (c.variant or '') == candidate['camera_variant']]
    if len(cams) != 1: raise ValueError('相机配置不唯一，不能自动选择')
    lenses = [l for l in db.find_lenses(cams[0],candidate['lens_maker'],candidate['lens_model']) if
              l.maker == candidate['lens_maker'] and l.model == candidate['lens_model']]
    if len(lenses) != 1: raise ValueError('镜头配置缺失或不唯一，不能猜测匹配')
    lens = lenses[0]
    focal = S.number(meta.get('focal'),.1,10000)
    aperture = None if meta.get('aperture') is None else S.number(meta['aperture'],.1,128)
    distance = None if meta.get('distance') is None else S.number(meta['distance'],.01,100000)
    if not lens.min_focal <= focal <= lens.max_focal: raise ValueError('焦距不在此镜头范围内')
    flags = []
    if lens.interpolate_distortion(focal) is not None: flags.append('distortion')
    if lens.interpolate_tca(focal) is not None: flags.append('tca')
    if aperture is not None and distance is not None and lens.interpolate_vignetting(focal,aperture,distance) is not None: flags.append('vignette')
    if not flags: raise ValueError('匹配镜头没有当前拍摄参数的有效标定；请手动调整')
    value = S.profile({**candidate, 'focal':focal, 'aperture':aperture, 'distance':distance, 'orientation':meta.get('orientation',1), 'flags':flags})
    LensProfile(value,shape)  # fail now on missing calibration, not at final export
    return value


class LensProfile:
    def __init__(self, value, shape):
        self.value = value = S.profile(value)
        if value is None: raise ValueError('镜头配置缺失')
        module, db, digest, version = database()
        if (digest, version) != (value['database_sha256'],value['library_version']):
            raise ValueError('原镜头库/算法版本缺失或变化，已暂停自动校正；重新选择配置或关闭后手动调整')
        self.db = db; self.shape = tuple(shape)
        self.sensor_shape = tuple(reversed(shape)) if value['orientation']>=5 else tuple(shape)
        cams = [c for c in db.find_cameras(value['camera_maker'],value['camera_model']) if c.maker == value['camera_maker'] and c.model == value['camera_model'] and (c.variant or '') == value['camera_variant']]
        if len(cams) != 1: raise ValueError('保存的相机配置不唯一或缺失')
        cam = cams[0]
        if abs(cam.crop_factor-value['crop']) > 1e-6: raise ValueError('相机裁切因子与保存配置不符')
        lenses = [l for l in db.find_lenses(cam,value['lens_maker'],value['lens_model']) if l.maker == value['lens_maker'] and l.model == value['lens_model']]
        if len(lenses) != 1: raise ValueError('保存的镜头配置不唯一或缺失')
        self.mod = module.Modifier(lenses[0],value['crop'],self.sensor_shape[1],self.sensor_shape[0])
        names = {'distortion':'DISTORTION','tca':'TCA','vignette':'VIGNETTING'}
        requested = sum(int(getattr(module.ModifyFlags,names[k])) for k in value['flags'])
        self.mod.initialize(value['focal'],value['aperture'] or 0.,value['distance'] or 1000.,scale=1.,pixel_format=np.float64,flags=requested)
        if 'distortion' in value['flags'] and self.mod.apply_geometry_distortion(0.,0.,1,1) is None:
            raise ValueError('Lensfun 未实际启用保留的畸变标定')
        if 'tca' in value['flags'] and self.mod.apply_subpixel_distortion(0.,0.,1,1) is None:
            raise ValueError('Lensfun 未实际启用保留的色差标定')
        self.gain = None

    def _to_sensor(self, xy):
        h,w = self.shape; u,v = np.moveaxis((xy+.5)/[w,h],-1,0)
        kind = self.value['orientation']
        if kind==1: x,y=u,v
        elif kind==2: x,y=1-u,v
        elif kind==3: x,y=1-u,1-v
        elif kind==4: x,y=u,1-v
        elif kind==5: x,y=v,u
        elif kind==6: x,y=v,1-u
        elif kind==7: x,y=1-v,1-u
        else: x,y=1-v,u
        sh,sw = self.sensor_shape
        return np.stack([x*sw-.5,y*sh-.5],axis=-1)

    def _from_sensor(self, xy):
        sh,sw = self.sensor_shape; u,v = np.moveaxis((xy+.5)/[sw,sh],-1,0)
        kind = self.value['orientation']
        if kind==1: x,y=u,v
        elif kind==2: x,y=1-u,v
        elif kind==3: x,y=1-u,1-v
        elif kind==4: x,y=u,1-v
        elif kind==5: x,y=v,u
        elif kind==6: x,y=1-v,u
        elif kind==7: x,y=1-v,1-u
        else: x,y=v,1-u
        h,w = self.shape
        return np.stack([x*w-.5,y*h-.5],axis=-1)

    def points(self, xy):
        mapped = []
        for x,y in self._to_sensor(np.asarray(xy,np.float64)):
            value = self.mod.apply_subpixel_geometry_distortion(float(x),float(y),1,1)
            if value is None: raise ValueError('镜头裁剪锁定缺少标定映射')
            mapped.append(value[0,0])
        return self._from_sensor(np.asarray(mapped))

    def coordinates(self, xy):
        """Evaluate a bounded local Lensfun grid, then interpolate its geometry.

        RGB is sampled only once after all transforms have been composed. Only
        Lensfun's coordinate field is interpolated here, never proxy RGB.
        """
        if not any(k in self.value['flags'] for k in ('distortion','tca')): return np.repeat(xy[...,None,:],3,axis=-2)
        from .optics_native import sample
        xy = self._to_sensor(xy); h,w = self.sensor_shape
        x0 = max(0,min(w-1,int(np.floor(xy[...,0].min())))); x1 = max(x0+1,min(w,int(np.ceil(xy[...,0].max()))+2))
        y0 = max(0,min(h-1,int(np.floor(xy[...,1].min())))); y1 = max(y0+1,min(h,int(np.ceil(xy[...,1].max()))+2))
        if (x1-x0)*(y1-y0)*120 > 512*1024*1024: raise ValueError('镜头坐标局部网格超过内存预算；未替换为代理场')
        coords = self.mod.apply_subpixel_geometry_distortion(float(x0),float(y0),x1-x0,y1-y0)
        if coords is None or coords.shape != (y1-y0,x1-x0,3,2) or not np.isfinite(coords).all(): raise ValueError('Lensfun 未生成有效的真实坐标场')
        mapped = sample(coords.reshape(y1-y0,x1-x0,6),xy-np.array([x0,y0])).reshape(*xy.shape[:-1],3,2)
        valid = (xy[...,0]>=-.5)&(xy[...,0]<=w-.5)&(xy[...,1]>=-.5)&(xy[...,1]<=h-.5)
        mapped = self._from_sensor(mapped); mapped[~valid] = -1e12
        return mapped

    def gains(self):
        if 'vignette' not in self.value['flags']: return None
        if self.gain is None:
            from .cpu_memory_budget import available_estimate
            h,w = self.sensor_shape
            if h*w*48+128*1024*1024 > available_estimate(): raise ValueError('镜头暗角增益场内存不足，不会跳过配置')
            self.gain = np.ones((h,w,3),np.float64)
            if not self.mod.apply_color_modification(self.gain): raise ValueError('Lensfun 没有实际应用暗角标定')
            kind = self.value['orientation']
            if kind==2: self.gain=self.gain[:,::-1]
            elif kind==3: self.gain=self.gain[::-1,::-1]
            elif kind==4: self.gain=self.gain[::-1]
            elif kind==5: self.gain=self.gain.transpose(1,0,2)
            elif kind==6: self.gain=np.rot90(self.gain,-1)
            elif kind==7: self.gain=self.gain.transpose(1,0,2)[::-1,::-1]
            elif kind==8: self.gain=np.rot90(self.gain,1)
            self.gain = np.ascontiguousarray(self.gain)
            if not np.isfinite(self.gain).all() or np.any(self.gain<=0) or np.any(self.gain>64): raise ValueError('Lensfun 暗角增益无效或超过安全范围')
        return self.gain
