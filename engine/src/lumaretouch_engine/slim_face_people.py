# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned corrected slim-face policy on the existing contour boundary.

AUTHORED / UNRUN. This adapter owns no topology, Rust kernel, TPS solver, sampler
or anatomical substitute. The original contour append authenticates the exact
retained face evidence and source, guards every foreign retained face, and
returns its composition-time source-footprint guard unchanged. The common
people renderer still owns the only combined map and final source sampler.
"""
from . import slim_face_state as S


def append(field, state, face_ref, analysis, source, recipe, legacy_amount, contour_recipe):
    recipe = S.check_coexistence(recipe, legacy_amount, contour_recipe)
    if not S.active(recipe):
        return field, None
    from . import face_contour_people as C
    compound = S.contour_recipe(recipe)
    # Do not copy/rebuild this result as plain FaceGeometry: ContouredFace retains
    # the actual composed-coordinate foreign-face and genuine-source guards.
    # All refusal exceptions and their diagnostic facts propagate unchanged.
    result, facts = C.append(field, state, face_ref, analysis, source, compound)
    return result, {
        'operation_id': S.OP, 'version': S.VERSION, 'recipe': recipe,
        'policy': S.POLICY,
        'profile': {
            'contour_operation_id': 'lnx.face_contour.v1',
            'region_gain_of_face_width': S.REGION_GAIN_OF_FACE_WIDTH,
            'legacy_operation_id': 'lnx.deform.v1',
            'legacy_peak_of_face_width': S.LEGACY_PEAK_OF_FACE_WIDTH,
            'legacy_numeric_or_appearance_equivalent': False,
        },
        'contour_recipe': compound,
        'contour_facts': facts,
    }
