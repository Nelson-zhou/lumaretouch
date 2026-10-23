"""Bounded XMP library admission; inspection never saves or applies pixels."""
from . import xmp_document as X, xmp_adaptation as A


def source_document(path):
    if path.lower().endswith('.json'):
        from .preset_store import load_file
        import base64
        preset = load_file(path)
        retained = preset.get('xmp_import')
        if retained is None: raise ValueError('This JSON preset contains no original XMP; use normal JSON import')
        return X.parse(base64.b64decode(retained['source_base64'], validate=True), basename=retained['filename'])
    if not path.lower().endswith('.xmp'): raise ValueError('Choose a local XMP or a native portable XMP preset')
    return X.read(path)


def inspect(path):
    document = source_document(path)
    report, _ = A.analyse(document)
    return {'path': path, 'xmp_report': report}


def load(path, acknowledgment):
    document = source_document(path)
    modules, retained = A.retained(document, acknowledgment)
    name = document['basename'].rsplit('.', 1)[0][:80] or 'XMP adaptation'
    identity = A.digest({'source': document['sha256'], 'selected': retained['selected']})
    return {'schema': 'lrt.preset.v1', 'id': 'xmp-' + identity[:32], 'name': name,
            'kind': 'color', 'author': '',
            'note': 'Explicit native parameter adaptation, not Adobe rendering. Unsupported settings are retained in the compatibility report; current-photo review is mandatory.',
            'modules': modules, 'xmp_import': retained}


def acknowledgment(value, record):
    """A client cannot substitute hashes from another reviewed target/report."""
    report = record['preset']['xmp_import']['report']; preview = record['xmp']
    expected = {'source_sha256': report['source_sha256'], 'report_sha256': report['report_sha256'],
                'before_sha256': preview['before']['sha256'], 'after_sha256': preview['after']['sha256']}
    if type(value) is not dict or value != expected:
        raise ValueError('View both verified target images and acknowledge this exact XMP adaptation before applying')
