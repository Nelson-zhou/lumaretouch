"""Source-boundary fixtures authored only, UNRUN; no product imports here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def source(name):
    return (ENGINE / name).read_text()


def test_choice_has_readonly_port_inside_existing_people_owner():
    dispatch = source('people_reference_dispatch.py')
    assert 'skin_reference_choice_host as CHOICE' in dispatch
    assert 'ACTIONS = FACE.ACTIONS | BODY.ACTIONS | CHOICE.ACTIONS' in dispatch
    assert 'READS = FACE.READS | BODY.READS | CHOICE.READS' in dispatch
    assert 'WRITES = ACTIONS - READS' in dispatch
    assert "return 'skin_reference_choice_request'" in dispatch
    host = source('people_host_commands.py')
    assert "reference_review.propose if action=='skin_reference_choice'" in host
    assert "reference_request_marker(p.get('action'))" in host


def test_proposal_does_not_bypass_effective_source_or_recovery_dispatch():
    assert 'people_reference_dispatch import check_action' in source('creative_derived_effects.py')
    assert 'people_reference_dispatch import read_only' in source('project_recovery_runtime.py')
    assert '"skin_reference_choice_protocol": 1' in source('server.py')


def test_same_solo_queue_and_no_automatic_reference_selection_on_receipt():
    workflow = (ROOT / 'ui/src/people/workflow.ts').read_text()
    for fragment in ('skinReferenceChoice.prepare(command, current)',
                     'skinReferenceChoice.validate(command, result, () => current)',
                     'skinReferenceChoice.complete(command)', 'skinReferenceChoice.update(value)',
                     'lastSkinReferenceChoiceResult', 'isSkinReferenceChoiceRead(command)'):
        assert fragment in workflow
    hook = (ROOT / 'ui/src/people/usePeopleWorkflow.ts').read_text()
    assert "action === 'skin_reference_choice'" in hook
    assert 'skin_reference_choice_protocol !== 1' in hook


def test_global_census_disclaimer_is_not_a_retained_measurement_blocker():
    helper = source('skin_reference_choice.py')
    assert "'census_complete': False" in helper
    assert "'candidate_scope': 'all-enabled-retained-same-source-faces'" in helper
    assert "'brightest-measurements-too-close'" in helper
    assert "'enabled-face-measurement-unavailable'" in helper
    assert "'detector-limit-reached'" in helper
    assert "limits=(0., 0.)" in helper
