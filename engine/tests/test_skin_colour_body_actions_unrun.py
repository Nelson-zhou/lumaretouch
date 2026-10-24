# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: exact command admission, never a runtime acceptance claim."""
import unittest
from lumaretouch_engine.skin_colour_body_actions import check_action


class BodySkinActionContracts(unittest.TestCase):
    def setUp(self):
        self.ref = {'asset_sha256': 'a'*64, 'face_instance_id': 'face_a',
                    'analysis_revision': 0}
        self.target = {'scope': 'face', 'target_id': 'face_a', 'face_ref': self.ref}

    def test_reference_accepts_no_source_override(self):
        check_action('skin_body_reference', {}, self.target)
        with self.assertRaises(ValueError):
            check_action('skin_body_reference', {'source': 'another'}, self.target)

    def test_detach_needs_no_fresh_body_or_mask(self):
        # Removing a stale pointer must remain possible without inventing new
        # body evidence. The host still checks current document/FaceRef fences.
        check_action('skin_body_detach', {}, self.target)
        with self.assertRaises(ValueError):
            check_action('skin_body_detach', {'body_ref': {}}, self.target)

    def test_confirm_requires_exact_visual_acknowledgment(self):
        check_action('skin_body_confirm', {'preview_id': 'preview_a', 'reviewed': True}, self.target)
        for payload in ({'preview_id': 'preview_a'},
                        {'preview_id': 'preview_a', 'reviewed': 1},
                        {'preview_id': 'preview_a', 'reviewed': False},
                        {'preview_id': 'preview_a', 'reviewed': True, 'source_override': {}}):
            with self.assertRaises(ValueError):
                check_action('skin_body_confirm', payload, self.target)

    def test_shared_scope_cannot_attach_one_persons_body_review(self):
        for scope in ('all_people', 'person', 'group'):
            with self.assertRaises(ValueError):
                check_action('skin_body_reference', {}, {**self.target, 'scope': scope})

    def test_unknown_action_and_incomplete_review_refuse(self):
        with self.assertRaises(ValueError):
            check_action('skin_body_apply_without_review', {}, self.target)
        for payload in ({}, {'review': {}}, {'review': None}, {'review': {}, 'bypass': True}):
            with self.assertRaises(ValueError):
                check_action('skin_body_preview', payload, self.target)
