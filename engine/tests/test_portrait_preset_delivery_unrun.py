# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No runtime acceptance is implied by these specifications."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from lumaretouch_engine.portrait_preset_delivery import GroupDelivery, command

TOKEN = 'a' * 32


def request(action, **extra):
    return dict(cmd='batch', action=action, request_id='request',
                preflight_token=TOKEN, batch_id='batch', **extra)


class GroupDeliverySpecificationsUnrun(TestCase):
    def owner(self):
        events = []
        group = SimpleNamespace(engine=SimpleNamespace(), batch=SimpleNamespace(
            preflight=SimpleNamespace(emit_result=lambda req, value: events.append((req, value)))))
        result = GroupDelivery(group)
        result.proofs[TOKEN] = {'batch_id': 'batch'}
        return result, events

    def test_exact_keys_do_not_allow_target_override_unrun(self):
        self.assertTrue(command(request('portrait_preset_save')))
        self.assertFalse(command(request('portrait_preset_save', docs=['other'])))
        self.assertFalse(command(request('portrait_preset_export_start', plan_id='p', intent_revision=True)))

    def test_unknown_save_blocks_new_output_even_without_recovery_owner_unrun(self):
        owner, _ = self.owner()
        owner.saves[TOKEN] = {'outcome_unknown': True}
        with self.assertRaises(ValueError):
            owner.run(request('portrait_preset_export_preview', export_options={}, policy={}, intent_revision=1))
        self.assertEqual(owner.export.records, {})

    def test_read_only_status_does_not_exhaust_mutation_receipts_unrun(self):
        owner, _ = self.owner()
        owner.receipts = {str(i): ('hash', {}) for i in range(256)}
        with patch.object(owner.export, 'observe', return_value={'export_status': 'unknown', 'export_task_id': 'task'}):
            result = owner.run(request('portrait_preset_export_status', task_id='task'))
        self.assertTrue(result['outcome_unknown'])
        self.assertEqual(len(owner.receipts), 256)

    def test_known_task_reconciles_only_original_start_identity_unrun(self):
        owner, events = self.owner()
        owner.export.records[TOKEN] = {'request_id': 'original-start',
            'destination': {'plan_id': 'b' * 64, 'intent_revision': 7}}
        observed = {'success': True, 'portrait_preset': True, 'outcome_unknown': False,
            'export_status': 'running', 'export_task_id': 'exact-task', 'task_id': 'exact-task'}
        owner._reconcile_start(TOKEN, observed)
        original, reply = events[0]
        self.assertEqual(original['request_id'], 'original-start')
        self.assertEqual(original['action'], 'portrait_preset_export_start')
        self.assertEqual(reply['export_task_id'], 'exact-task')
        self.assertTrue(reply['export_reconciled'])
        self.assertNotIn('task_id', reply)
        self.assertEqual(reply['plan_id'], 'b' * 64)

    def test_save_replay_does_not_invoke_another_disk_write_unrun(self):
        owner, _ = self.owner()
        owner.saves[TOKEN] = {'success': True, 'portrait_preset': True, 'outcome_unknown': False,
            'save_status': 'saved', 'saved_project_sha256': 'c' * 64}
        with patch.object(owner, 'verify', side_effect=AssertionError('must not re-save')):
            result = owner.run(request('portrait_preset_save'))
        self.assertTrue(result['replayed'])
        self.assertEqual(result['saved_project_sha256'], 'c' * 64)
