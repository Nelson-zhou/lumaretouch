"""Local import provenance survives source relocation and virtual copying."""
import os
from pathlib import Path
from .export_destination_policy import absolute, component


def origin(path, root=None, *, kind='file'):
    path = absolute(os.path.abspath(path))
    root = absolute(os.path.abspath(root)) if root is not None else path.parent
    relative = path.relative_to(root)
    for part in relative.parts: component(part)
    return {'schema_version': 1, 'root': str(root), 'relative': str(relative), 'kind': kind}


def validate(value):
    if not isinstance(value, dict) or set(value) != {'schema_version','root','relative','kind'} or value['schema_version'] != 1:
        raise ValueError('导入目录记录格式无效')
    absolute(value['root'])
    relative = value['relative']
    if not isinstance(relative,str) or relative.startswith('/') or not relative:
        raise ValueError('导入相对路径无效')
    for part in relative.split('/'): component(part)
    if value['kind'] not in ('file','directory','legacy_parent'):
        raise ValueError('导入目录来源无效')
    return value


def expand(paths, extensions, limit):
    """Explicit folder imports, recursive without symlink traversal; all or nothing."""
    found, origins = [], {}
    for raw in paths:
        path = absolute(os.path.abspath(raw))
        if path.is_symlink(): raise ValueError('导入目录或文件不能为符号链接')
        if path.is_dir():
            candidates = []
            for directory, dirs, names in os.walk(path, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not Path(directory,d).is_symlink())
                for name in sorted(names):
                    candidate = Path(directory,name)
                    if candidate.is_symlink(): continue
                    if candidate.suffix.lower() in extensions and candidate.is_file():
                        candidates.append(candidate)
                        if len(candidates) + len(found) > limit: raise ValueError('导入数量超过上限，请分批选择')
            kind, root = 'directory', path
        elif path.is_file():
            candidates, kind, root = [path], 'file', path.parent
        else: raise ValueError('导入来源不存在')
        for candidate in candidates:
            key = str(candidate)
            record = origin(key, str(root), kind=kind)
            if key in origins and origins[key] != record:
                raise ValueError('同一文件通过重叠目录重复导入，请只选一个层级')
            if key not in origins:
                found.append(key); origins[key] = record
    if not found: raise ValueError('选择的目录没有可导入图片')
    if len(found) > limit: raise ValueError('导入数量超过上限')
    return found, origins
