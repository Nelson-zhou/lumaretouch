# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared immutable pixels for independent proof families of the SAME cohort.

Each public read wrapper must first validate its own family. Sharing bytes is
not permission to substitute a coverage proof for a portrait-cohort proof.
"""


def records(plan):
    from .batch_preflight import collarbone_required, portrait_cohort_records
    from .eye_bag_cohort_review import records as eye_records
    portrait = portrait_cohort_records(plan); eye = eye_records(plan); families = []
    if portrait is not None: families.append({row['document_id']: row for row in portrait})
    if eye is not None: families.append({item['visual']['document_id']: item['visual'] for item in eye})
    if collarbone_required(plan):
        from .collarbone_visual_store import _records
        families.append(_records(plan))
    if not families: raise ValueError('Shared image cache requires actual complete cohort evidence')
    result = families[0]
    keys = ('version', 'document_id', 'revision', 'source_proof', 'before_state_sha256', 'candidate_state_sha256',
            'before_people_sha256', 'candidate_people_sha256', 'source_size', 'before_output_size', 'after_output_size', 'before', 'after')
    for other in families[1:]:
        if set(other) != set(result) or any(any(row[key] != other[doc][key] for key in keys) for doc, row in result.items()):
            raise ValueError('Every cohort family must describe exactly the same complete source and image pair')
    return result


def cache(store):
    from .collarbone_visual_store import _Images
    existing=[getattr(store,key,None) for key in ('_cohort_review_images','_collarbone_visual_images','_portrait_cohort_images','_eye_bag_cohort_images')]
    existing=[value for value in existing if value is not None]
    if existing and any(value is not existing[0] for value in existing):
        raise ValueError('Independent live image caches cannot be silently merged; finish existing reviews first')
    value=existing[0] if existing else _Images(records=records)
    value.records=records
    store._cohort_review_images=value
    store._collarbone_visual_images=value
    store._portrait_cohort_images=value
    store._eye_bag_cohort_images=value
    return value
