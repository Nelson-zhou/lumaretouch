# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: preset owner fences and exact planner integration.

No product import, fixture execution, rendering or history acceptance occurred
while authoring these tests. Text checks are not runtime proof.
"""
from pathlib import Path
from types import SimpleNamespace
import pytest
from lumaretouch_engine.preset_collarbone_lifecycle import CollarbonePresetReplay
from lumaretouch_engine.scope import ScopeError

SOURCE = Path(__file__).resolve().parents[1] / 'src/lumaretouch_engine'


def transaction():
    row = {'document_id': 'logical', 'path': 'original.png'}
    owner = {'row': row, 'load': 'load-one', 'revision': '4', 'state': {'amount': 0}}
    calls = []
    ports = SimpleNamespace(target_row=lambda: owner['row'], document_id=lambda: owner['load'],
        revision=lambda: owner['revision'], capture=lambda: owner['state'],
        collarbone_replay=lambda *args, **kwargs: calls.append(('replay', args, kwargs)) or {'frame': 'fixture'},
        verify_collarbone_applied=lambda *args, **kwargs: calls.append(('verify', args, kwargs)))
    value = CollarbonePresetReplay(ports, row, ('logical', 'original.png', 'load-one'), '4', {'proof': 'frozen'})
    return value, owner, ports, calls


def test_actual_replay_receives_frozen_wrapper_and_strict_full_gate():
    value, _, _, calls = transaction()
    frame = value.replay({'amount': .4}, mode='preset')
    assert frame == {'frame': 'fixture'} and value.started is True
    assert calls[0][1][-1] == {'proof': 'frozen'}
    assert calls[0][2] == {'rollback': False, 'mode': 'preset', 'strict_local': True}


def test_rollback_without_forward_write_is_not_a_stale_restore():
    value, _, _, calls = transaction()
    with pytest.raises(ScopeError, match='did not start'):
        value.replay({'amount': 0}, mode='preset_rollback')
    assert calls == []


@pytest.mark.parametrize('change', ['row_object', 'document', 'path', 'load', 'revision'])
def test_replay_cannot_move_to_new_owner_or_revision(change):
    value, owner, _, calls = transaction()
    if change == 'row_object': owner['row'] = dict(owner['row'])
    elif change == 'document': owner['row']['document_id'] = 'other'
    elif change == 'path': owner['row']['path'] = 'other.png'
    else: owner[change] = 'other'
    with pytest.raises(ScopeError): value.replay({'amount': .4}, mode='preset')
    assert calls == [] and value.started is False


def test_rollback_uses_same_owner_and_parent_exact_graph_port():
    value, _, _, calls = transaction()
    value.replay({'amount': .4}, mode='preset')
    value.replay({'amount': 0}, mode='preset_rollback')
    value.verify(rollback=True)
    assert calls[1][2]['rollback'] is True and calls[1][2]['strict_local'] is True
    assert calls[2][0] == 'verify' and calls[2][2]['rollback'] is True


def test_postverify_cannot_bless_callback_target_drift():
    value, owner, ports, _ = transaction()
    ports.verify_collarbone_applied = lambda *args, **kwargs: owner.update(load='other')
    with pytest.raises(ScopeError): value.verify()


def test_missing_exact_graph_ports_refuse_before_transaction():
    value, owner, ports, _ = transaction(); ports.collarbone_replay = None
    with pytest.raises(ScopeError, match='exact reviewed graph'):
        CollarbonePresetReplay(ports, owner['row'], value.identity, '4', {})


def test_final_mixed_candidate_is_prepared_before_collarbone_images():
    source = (SOURCE / 'local_grade_preset_review.py').read_text()
    prepare = source[source.index('    def prepare('):source.index('    def claim(')]
    assert prepare.index("if reference_record is not None:RC.apply_verified") < prepare.index('prepare_portrait(row,state,candidate')
    assert prepare.index('prepare_xmp(row,state,candidate') < prepare.index('prepare_portrait(row,state,candidate')
    assert "preset,prepared,**extra)" in prepare
    assert "**({portrait.wire:collarbone_public} if collarbone else {})" in prepare


def test_ack_and_real_images_are_verified_before_token_consumption():
    source = (SOURCE / 'local_grade_preset_review.py').read_text()
    claim = source[source.index('    def claim('):]
    assert claim.index("portrait.review.acknowledgment(") < claim.index('del self.pending[token]')
    assert claim.index('verify_available(self,token)') < claim.index('del self.pending[token]')
    assert claim.index('verify_portrait(row,state,candidate') < claim.index('del self.pending[token]')
    assert "self.targets.get(token) is not row" in claim


def test_apply_cannot_bypass_stored_collarbone_with_legacy_direct_route():
    source = (SOURCE / 'preset_controller.py').read_text()
    assert "if PORTRAIT.select(mods) is not None or family is not None" in source
    assert "portrait.ack:deepcopy(p[portrait.ack])" in source
    assert "collarbone_transaction.replay if collarbone" in source
    assert "if collarbone:collarbone_transaction.verify()" in source
    assert "if collarbone:collarbone_transaction.verify(rollback=True)" in source


def test_failed_and_oversized_receipts_keep_exact_preset_ack_identity():
    source = (SOURCE / 'preset_controller.py').read_text()
    assert "finally:\n            if action == 'apply':result.update(deepcopy(self._scalar_receipt))" in source
    assert "scalar_keys=('torso_review_ack','waist_review_ack','head_review_ack','collarbone_preset_ack','eye_bag_preset_ack')" in source
    assert '**review_fields' in source
    assert "'preflight_token':p['preflight_token']" in source


def test_image_reads_are_distinct_from_mutating_preset_actions():
    source = (SOURCE / 'preset_controller.py').read_text()
    assert '"collarbone_visual": {"id", "document_id", "revision", "side", "sha256", "preflight_token"}' in source
    assert "if action in ('collarbone_visual','eye_bag_visual') and not correlated" in source
    assert 'evidence = retrieve(self,p)' in source
    assert 'collarbone_review_ack' not in source  # Batch approval is not preset approval.


def test_workflow_ports_use_exact_adapter_not_generic_partial_overlay():
    source = (SOURCE / 'workflow_ports.py').read_text()
    for name in ('prepare', 'verify', 'replay', 'verify_applied'):
        assert 'from .collarbone_preset_review import '+name in source
    assert 'return prepare(self,row,before,candidate,document_id,str(revision),preset,modules)' in source


def test_missing_graph_ports_are_rejected_before_claim_or_revision_advance():
    source = (SOURCE / 'preset_controller.py').read_text()
    apply = source[source.index('    def apply(self, p):'):]
    assert apply.index('portrait.require_ports(self.ports)') < apply.index('self.reviews.claim(')
    assert apply.index('portrait.require_ports(self.ports)') < apply.index('self.ports.advance()')
    assert 'verify_after=verify_after if collarbone or source_proof is not None' in apply
