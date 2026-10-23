"""Session ordering and explicit identity lookup, never path deduplication of copies."""
import os


def index_of(rows, path, document_id=None):
    if document_id is not None:
        found = next((i for i,r in enumerate(rows) if r.get('document_id')==document_id),-1)
        if found < 0: raise ValueError('文档身份已失效，请刷新')
        if path and rows[found]['path'] != os.path.abspath(str(path)):
            raise ValueError('文档来源路径已变化，请刷新')
        return found
    if not path: return -1
    wanted = os.path.abspath(str(path))
    matches = [i for i,r in enumerate(rows) if r['path']==wanted]
    if len(matches)>1: raise ValueError('同源图有多个版本，请按文档身份选择')
    return matches[0] if matches else -1


def rows_from(engine, paths):
    with engine._doclock:
        current = engine._docs[engine._doc_index] if 0 <= engine._doc_index < len(engine._docs) else None
        groups = {}
        for row in engine._docs: groups.setdefault(row['path'],[]).append(row)
        rows, seen = [], set()
        for path in paths:
            path = os.path.abspath(str(path))
            if path in seen: continue
            seen.add(path)
            rows.extend(groups.get(path) or [engine._new_row(path)])
        # Retain a complete family, never an orphaned copy on an unsaved scan.
        roots = {r['root_document_id'] for r in engine._docs if r.get('copy_number',0) or r is current}
        # Project records, including trash/copies, cannot disappear on rescan.
        for row in engine._docs:
            if row['path'] not in seen and (engine._project is not None or row['root_document_id'] in roots):
                rows.append(row)
        engine._docs = rows
        engine._doc_index = next((i for i,r in enumerate(rows) if r is current),-1)
        return rows
