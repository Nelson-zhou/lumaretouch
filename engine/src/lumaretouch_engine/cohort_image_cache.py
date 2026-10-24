# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared immutable pixels for independent proof families of the SAME cohort.

Each public read wrapper must first validate its own family. Sharing bytes is
not permission to substitute a coverage proof for a portrait-cohort proof.
"""


def records(plan):
    from .batch_preflight import collarbone_required,portrait_cohort_records
    portrait=portrait_cohort_records(plan)
    if portrait is None:
        from .collarbone_visual_store import _records
        return _records(plan)
    result={row['document_id']:row for row in portrait}
    if collarbone_required(plan):
        from .collarbone_visual_store import _records
        clavicle=_records(plan)
        if set(clavicle)!=set(result):raise ValueError('Dual cohort image member sets differ')
        keys=('version','document_id','revision','source_proof','before_state_sha256','candidate_state_sha256',
              'before_people_sha256','candidate_people_sha256','source_size','before_output_size','after_output_size','before','after')
        if any(any(row[key]!=clavicle[doc][key] for key in keys) for doc,row in result.items()):
            raise ValueError('Dual cohort reviews must describe exactly the same source and image pair')
    return result


def cache(store):
    from .collarbone_visual_store import _Images
    existing=[getattr(store,key,None) for key in ('_cohort_review_images','_collarbone_visual_images','_portrait_cohort_images')]
    existing=[value for value in existing if value is not None]
    if existing and any(value is not existing[0] for value in existing):
        raise ValueError('Independent live image caches cannot be silently merged; finish existing reviews first')
    value=existing[0] if existing else _Images(records=records)
    value.records=records
    store._cohort_review_images=value
    store._collarbone_visual_images=value
    store._portrait_cohort_images=value
    return value
