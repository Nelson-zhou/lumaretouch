# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit reference-family command ports inside the existing people owner."""
from . import skin_reference_match_host as FACE, skin_reference_body_host as BODY

ACTIONS = FACE.ACTIONS | BODY.ACTIONS
READS = FACE.READS | BODY.READS
WRITES = ACTIONS - READS


def module(action):
    if action in FACE.ACTIONS:
        return FACE
    if action in BODY.ACTIONS:
        return BODY
    raise ValueError('Unknown reviewed reference family')


def read_only(raw):
    return FACE.read_only(raw) or BODY.read_only(raw)


def check_action(action, payload, target):
    return module(action).check_action(action, payload, target)


def bound_receipt_images(records):
    FACE.bound_receipt_images(records)
    BODY.bound_receipt_images(records)
