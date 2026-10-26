# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only ORIGINAL-photo clues inside already reviewed person associations.

Not a face matcher, expression classifier, quality score or authority to apply.
Fresh edited-source FaceRefs cannot be inferred from these original FaceRefs.
"""
from copy import deepcopy
import math
import os
from . import people_state as S, virtual_copy_people as V
from . import people_transfer_inventory as I, people_cross_owner as C
from .people_cross_owner_workflow import _capsule, _endpoint

MAX_COHORTS = 8
MAX_MEMBERS = 16


def filename(path):
    value = ''.join(c for c in os.path.basename(path) if ord(c) >= 32 and ord(c) != 127)
    return value.encode('utf-16-le')[:512].decode('utf-16-le', errors='ignore') or '(unnamed)'


def eyelid_evidence(face, record):
    """Only canonical, hash-verified per-face landmarks feed the existing metric."""
    from .people_binding import landmark_digest
    from .picks import eye_openness
    ev = face['evidence']
    if (face['manual'] or ev['status'] != 'verified' or ev['backend'] != 'mediapipe'
            or record is None or record.get('face_ref') != S.face_ref(face)
            or record.get('evidence') != ev):
        return None
    try:
        if landmark_digest(record['landmarks']) != ev['landmark_digest']:
            return None
        value = eye_openness(record['landmarks'], image_size=(ev['source_width'], ev['source_height']))
        return float(value) if value is not None and math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError, KeyError, OverflowError):
        return None


def ordered(candidates):
    """Explicit geometry-only descending ordering; missing measurements last."""
    return sorted(candidates, key=lambda x: (x['eye_aperture'] is None,
        -(x['eye_aperture'] or 0), x['document_id']))


def collect(engine, *, cancelled=lambda: False):
    result = {'version': 1, 'cohorts': [], 'unavailable': None}
    rows = engine._docs
    current = V.current_row(engine)
    graph = None if current is None else V.peek_graph(engine, current)
    if graph is None:
        result['unavailable'] = '没有当前照片已保留的明确人物关联；请使用手动素材路径。'
        return result
    local_id = engine._document_versions().version(current).document_id
    capsules = [C.check_descriptor(p['cross_owner']) for p in graph['persons'].values()
                if 'cross_owner' in p and p['cross_owner']['local_document_id'] == local_id]
    shared = shared_cohorts(engine, current, graph, cancelled=cancelled)
    result['cohorts'].extend(shared)
    if not capsules and not shared:
        result['unavailable'] = '没有独立照片之间已由用户确认的人物关联；不自动识别人。仍可手动选择素材。'
        return result
    if len(capsules) + len(shared) > MAX_COHORTS:
        result['cohorts'] = []
        result['unavailable'] = '关联超过本次只读建议预算；未截断或猜测，请使用手动路径。'
        return result
    for capsule in sorted(capsules, key=lambda x: x['association_id']):
        if cancelled(): raise InterruptedError('Expression donor hint acquisition cancelled')
        cohort = {'association_id': capsule['association_id'], 'target_ref': C.local_member(capsule)['ref'],
                  'candidates': [], 'blocked': None}
        result['cohorts'].append(cohort)
        try:
            endpoints = []
            member_ids = {m['document_id'] for m in capsule['members']}
            for row in rows:
                other = V.peek_graph(engine, row)
                if (other is not None and engine._document_versions().version(row).document_id not in member_ids
                        and _capsule(other, capsule['association_id'])[1] is not None):
                    raise ValueError('存在未纳入复核的关联副本，不能提供排序')
            for member in capsule['members']:
                if cancelled(): raise InterruptedError('Expression donor hint acquisition cancelled')
                found = engine._document_versions().find(rows, member['document_id'])
                if found is None: raise ValueError('关联照片不在当前工作区')
                _, row = found
                g = V.peek_graph(engine, row)
                if g is None: raise ValueError('关联照片尚无已审核的人脸来源')
                proof = I.proof(engine, row, g, source_row=I._source_row(engine, row))
                if proof['source_proof']['creative_source'] is not None:
                    raise ValueError('此建议只支持原片分析，不能把返回副本定位套到原文件')
                item = _endpoint(engine, rows, proof, member['ref'], reviewed_only=True)
                if item['member'] != member: raise ValueError('关联原文件或作用域已经改变')
                _, replica = _capsule(g, capsule['association_id'])
                if replica is None or replica['generation'] != capsule['generation'] or replica['members'] != capsule['members']:
                    raise ValueError('关联各照片的已确认版本不一致')
                face = g['faces'][member['ref']['face_instance_id']]
                if face['manual']: raise ValueError('手动定位没有可用于排序的实测人脸证据')
                endpoints.append(item)
                if member['document_id'] != local_id:
                    if member['original_sha256'] == C.local_member(capsule)['original_sha256']:
                        raise ValueError('关联素材与当前照片是同一原文件，不作为另一张表情素材')
                    record = V.peek_landmark_record(engine, row, member['ref'])
                    cohort['candidates'].append({'document_id': member['document_id'],
                        'filename': filename(row['path']), 'face_ref': deepcopy(member['ref']),
                        'eye_aperture': eyelid_evidence(face, record)})
            for item in endpoints:
                if cancelled(): raise InterruptedError('Expression donor hint acquisition cancelled')
                I.verify(engine, item['row'], V.peek_graph(engine, item['row']), item['proof'],
                         source_row=I._source_row(engine, item['row']))
            cohort['candidates'] = ordered(cohort['candidates'])
        except InterruptedError:
            raise
        except (ValueError, OSError, KeyError, TypeError) as error:
            cohort['candidates'] = []
            cohort['blocked'] = str(error)[:512]
    return result


def shared_cohorts(engine, current, graph, *, cancelled):
    """Ordinary shared-project confirmed links; no cross-owner reinterpretation."""
    if V.scope(current) != V.PROJECT: return []
    current_proof = I.proof(engine, current, graph, source_row=I._source_row(engine, current))
    if current_proof['source_proof']['creative_source'] is not None: return []
    asset = current_proof['source_proof']['asset_sha256']
    result = []
    for person_id, person in sorted(graph['persons'].items()):
        if 'cross_owner' in person: continue
        links = [x for x in graph['links'] if x['person_id'] == person_id and x['state'] == 'confirmed']
        faces = [graph['faces'][x['face_instance_id']] for x in links]
        local = [f for f in faces if f['asset_sha256'] == asset and f['enabled']]
        if not local: continue
        if len(result) >= MAX_COHORTS: raise ValueError('当前原片的关联超过只读预算')
        cohort = {'association_id': person_id, 'target_ref': S.face_ref(local[0]), 'candidates': [], 'blocked': None}
        result.append(cohort)
        try:
            if len(local) != 1: raise ValueError('当前原片同一人物关联有多个脸，需先明确修正关联')
            if not 2 <= len(faces) <= MAX_MEMBERS: raise ValueError('需有2至16个明确关联的人脸')
            if any(not f['enabled'] or f['manual'] or f['evidence']['status'] != 'verified' for f in faces):
                raise ValueError('关联中有停用或未实测人脸，需先复核')
            if len({f['asset_sha256'] for f in faces}) != len(faces):
                raise ValueError('同一原片有多个关联脸，不能猜测素材归属')
            endpoints = []
            for face in faces:
                if cancelled(): raise InterruptedError('Expression donor hint acquisition cancelled')
                matches = []
                for row in engine._docs:
                    if row.get('trashed') or V.scope(row) != V.PROJECT: continue
                    # Saved digest is routing only; independently rehash below.
                    routed = row.get('_people_source_sha256') or (row.get('fingerprint') or {}).get('sha256')
                    if row is current: routed = asset
                    if routed != face['asset_sha256']: continue
                    g = V.peek_graph(engine, row)
                    if g is None or I.graph_digest(g) != I.graph_digest(graph): continue
                    # Physical hashes, not filenames, establish exact source ownership.
                    proof = I.proof(engine, row, g, source_row=I._source_row(engine, row))
                    if proof['source_proof']['creative_source'] is None and proof['source_proof']['asset_sha256'] == face['asset_sha256']:
                        matches.append((row, proof))
                if len(matches) != 1: raise ValueError('关联原片缺失或存在多个文档别名；不猜测文件')
                row, proof = matches[0]
                endpoints.append((row, proof))
                if face['asset_sha256'] != asset:
                    cohort['candidates'].append({'document_id': proof['document']['document_id'],
                        'filename': filename(row['path']), 'face_ref': S.face_ref(face),
                        'eye_aperture': eyelid_evidence(face, V.peek_landmark_record(engine, row, S.face_ref(face)))})
            for row, proof in endpoints:
                I.verify(engine, row, V.peek_graph(engine, row), proof, source_row=I._source_row(engine, row))
            cohort['candidates'] = ordered(cohort['candidates'])
        except InterruptedError:
            raise
        except (ValueError, OSError, KeyError, TypeError) as error:
            cohort['candidates'] = []
            cohort['blocked'] = str(error)[:512]
    return result


def safe_collect(engine, *, cancelled=lambda: False):
    try:
        return collect(engine, cancelled=cancelled)
    except InterruptedError:
        raise
    except (ValueError, OSError, KeyError, TypeError, MemoryError, ImportError) as error:
        return {'version': 1, 'cohorts': [], 'unavailable': ('素材线索不可用，手动路径不变：' + str(error))[:512]}
