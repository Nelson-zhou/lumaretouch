"""AUTHORED / UNRUN: FORMAT-001 receipt propagation, not codec acceptance.

The adapter plan below is a test double. No codec/version is inferred from it.
The worker already copies actual writer quality facts into export_done; these
fixtures cover the previously lossy task and Original receipt boundaries.
"""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from lumaretouch_engine import tasks as T
from lumaretouch_engine import project as PJ
from lumaretouch_engine import export_destination_runtime as R
from lumaretouch_engine import export_format_plan as F


def task_item_method():
    # Isolate the real ledger method without starting/importing the server.
    source = Path(__file__).parents[1] / 'src/lumaretouch_engine/server.py'
    tree = ast.parse(source.read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == '_task_item_locked')
    namespace = {'T': T}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['_task_item_locked']


@pytest.mark.parametrize('outcome', ['succeeded', 'skipped', 'failed'])
@pytest.mark.parametrize('version', ['lrt.quality.v1', None, 'absent'])
def test_task_receipt_survives_project_save_reopen(tmp_path, outcome, version):
    task = T.new_task('export', {'format': 'jpg', 'quality': 91}, ['source'], task_id='quality')
    record = {'out': 'result.jpg', 'format': 'jpg', 'encoder_quality': 91, 'bytes': 7}
    if version != 'absent':
        record['quality_mapping_version'] = version
    record['outputs'] = [{'path': 'result.jpg', 'format': 'jpg',
                          'encoder_quality': 83, 'quality_mapping_version': 'variant-version'}]
    if outcome == 'failed':
        record['error'] = 'fixture failure after encode'
    elif outcome == 'skipped':
        record['out_skipped'] = True
    emitted = []
    owner = SimpleNamespace(_emit_task=lambda value, note: emitted.append(deepcopy(value)))
    task_item_method()(owner, task, 'source', record)
    project = PJ.new_project('quality receipt fixture')
    project['tasks'] = [T.for_json(task)]
    destination = str(tmp_path / 'quality.lrt')
    PJ.save(project, destination)
    restored = T.from_json(PJ.load(destination)['tasks'][0])
    for item in (task['items'][0], emitted[0]['items'][0], restored['items'][0]):
        assert item['state'] == outcome
        assert item['encoder_quality'] == 91
        assert item['outputs'] == record['outputs']
        assert ('quality_mapping_version' in item) == (version != 'absent')
        if version != 'absent':
            assert item['quality_mapping_version'] == version


@pytest.mark.parametrize('codec', ['jpg', None])
@pytest.mark.parametrize('version', ['lrt.quality.v1', None, 'absent'])
def test_original_ordinary_receipt_only_copies_reported_facts(monkeypatch, codec, version):
    entry = SimpleNamespace(item_id='source', target='result.jpg', renamed_from=None)
    plan = SimpleNamespace(plan_id='plan', entries=[entry], settings_json='{}')
    monkeypatch.setattr(R, 'restore', lambda payload: plan)
    monkeypatch.setattr(F, 'validate_settings', lambda settings, entries:
                        {'entries': {'source': {'codec': 'jpg'}}})
    monkeypatch.setattr(F, 'receipt_fields', lambda decision: {'requested_format': 'original'})
    record = {'out': 'result.jpg', 'format': codec, 'bits': 8,
              'encoder_quality': 91, 'bytes': 0}
    if version != 'absent':
        record['quality_mapping_version'] = version
    R.decorate(record, {}, 'source')
    output = record['outputs'][0]
    assert output['format'] == codec  # No codec invented from the plan.
    assert output['encoder_quality'] == 91
    assert ('quality_mapping_version' in output) == (version != 'absent')
    if version != 'absent':
        assert output['quality_mapping_version'] == version


def test_original_existing_variant_receipts_are_not_relabelled(monkeypatch):
    entry = SimpleNamespace(item_id='source', target='result.jpg', renamed_from=None)
    plan = SimpleNamespace(plan_id='plan', entries=[entry], settings_json='{}')
    monkeypatch.setattr(R, 'restore', lambda payload: plan)
    monkeypatch.setattr(F, 'validate_settings', lambda settings, entries:
                        {'entries': {'source': {'codec': 'jpg'}}})
    monkeypatch.setattr(F, 'receipt_fields', lambda decision: {'requested_format': 'original'})
    record = {'quality_mapping_version': 'top-level-not-a-variant-default',
              'outputs': [{'path': 'result.jpg', 'format': 'jpg', 'bytes': 0,
                           'encoder_quality': 83, 'quality_mapping_version': 'reported-version'}]}
    R.decorate(record, {}, 'source')
    assert record['outputs'][0]['quality_mapping_version'] == 'reported-version'
    assert record['outputs'][0]['encoder_quality'] == 83
