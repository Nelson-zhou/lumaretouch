# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit reference-family command ports inside the existing people owner."""
from . import skin_reference_match_host as FACE, skin_reference_body_host as BODY
from . import skin_reference_choice_host as CHOICE

ACTIONS = FACE.ACTIONS | BODY.ACTIONS | CHOICE.ACTIONS
READS = FACE.READS | BODY.READS | CHOICE.READS
WRITES = ACTIONS - READS


def module(action):
    if action in FACE.ACTIONS:
        return FACE
    if action in BODY.ACTIONS:
        return BODY
    if action in CHOICE.ACTIONS:
        return CHOICE
    raise ValueError('Unknown reviewed reference family')


def read_only(raw):
    return FACE.read_only(raw) or BODY.read_only(raw) or CHOICE.read_only(raw)


def check_action(action, payload, target):
    return module(action).check_action(action, payload, target)


def bound_receipt_images(records):
    FACE.bound_receipt_images(records)
    BODY.bound_receipt_images(records)


def request_marker(action):
    if action in CHOICE.ACTIONS:
        return 'skin_reference_choice_request'
    return 'skin_reference_body_request' if action in BODY.ACTIONS else 'skin_reference_match_request'
