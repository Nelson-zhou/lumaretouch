"""Read-only immutable source checks for document operations and frozen exports."""


def fingerprint_for(row):
    from . import project as PJ
    from .local_mask_state import file_stamp
    before = file_stamp(row['path'])
    actual = PJ.fingerprint(row['path'],full=True)
    if file_stamp(row['path']) != before: raise ValueError('读取期间源文件变化')
    expected = row.get('fingerprint') or {}
    if expected.get('hash_level') != 'full' and row.get('_local_source_stamp') is not None and tuple(row['_local_source_stamp']) != before:
        raise ValueError('源文件在解码后变化，不能将旧配方绑定到新内容')
    for key in ('bytes','head_sha256'):
        if key == 'bytes' and expected.get(key) == -1 and expected.get('hash_level') == 'none': continue
        if expected.get(key) is not None and expected[key] != actual.get(key):
            raise ValueError('源文件与保留指纹不符')
    if expected.get('hash_level') == 'full' and expected.get('sha256') != actual.get('sha256'):
        raise ValueError('源文件完整内容已改变，不能沿用旧文档身份')
    return actual, before


def verify_entry(entry, cache):
    """Cache full hashing only while exact file stat and immutable identity match."""
    from .local_mask_state import file_stamp
    expected = entry.get('fingerprint')
    if expected is None: return file_stamp(entry['path'])
    stamp = file_stamp(entry['path'])
    key = (entry.get('source_asset_id'),entry['path'],expected.get('sha256'),stamp)
    if key not in cache:
        fingerprint_for({'path':entry['path'],'fingerprint':expected})
        cache.add(key)
    return stamp


def verify_decode(path, stamp):
    from .local_mask_state import file_stamp
    if file_stamp(path) != stamp: raise ValueError('源文件在导出解码期间改变')
