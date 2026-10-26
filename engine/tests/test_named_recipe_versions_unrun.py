"""AUTHORED / UNRUN. No runtime, rendering or persistence acceptance claimed."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import named_recipe_versions as N
from lumaretouch_engine import history_navigation as H


def view():
    return dict(workspace='workspace', document_id='doc', load_id='load', revision='7',
                digest='a'*64, cursor=1, undo_steps=1, redo_steps=0, history_max=64)


def request(action='named_create'):
    value = dict(cmd='history_navigation', action=action, request_id='history-nav-v1:named',
                 view=view(), catalog_digest='b'*64)
    if action != 'named_select': value['name'] = '自然光方案'
    if action != 'named_create': value['version_id'] = 'named-id'
    return value


def test_exact_tagged_variants_do_not_loosen_old_navigation():
    for action in ('named_create', 'named_rename', 'named_select'):
        assert H.plan(request(action)) == ('named', 1)
        bad = request(action); bad['snapshot'] = {}
        with pytest.raises(ValueError): H.plan(bad)
        bad = request(action); bad['request_id'] = 'unreserved'
        with pytest.raises(ValueError): H.plan(bad)
    bad = request(); bad['action'] = 'navigate'
    with pytest.raises(ValueError): H.plan(bad)


def test_names_are_bounded_without_silent_normalization():
    for bad in ('', ' padded ', 'line\nbreak', '\0', '好'*54):
        with pytest.raises(ValueError): N.name(bad)
    assert N.name('好'*53) == '好'*53


def test_catalog_never_relabels_a_named_checkpoint_as_working_or_another_copy():
    row = dict(document_id='doc', source_asset_id='source', recipe_version_id='working')
    version = dict(id='named-id', name='Version', recipe={}, named_recipe_snapshot=dict(
        version=1, document_id='doc', source_asset_id='source', frame={}))
    project = dict(docs=[dict(row, versions=[version], active_version='working')], assets={})
    engine = SimpleNamespace(_project=project, _image_loaded=True, _doc_index=0, _docs=[row])
    assert N.catalog(engine)['versions'] == [dict(id='named-id', name='Version')]
    first = N.catalog(engine)['catalog_digest']
    version['name'] = 'Renamed'
    assert N.catalog(engine)['catalog_digest'] != first
    row['_project_version_id'] = 'named-id'
    with pytest.raises(ValueError): N.catalog(engine)
    row.pop('_project_version_id')
    version[N.TAG]['document_id'] = 'same-source-other-copy'
    with pytest.raises(ValueError): N.catalog(engine)


def test_wire_budget_counts_ascii_escapes_and_full_original_identity():
    packet = H.packet(request())
    packet.update(error='𐀀' * 5000)
    assert N.wire_size(packet) > 32768
    N.bound_error(packet)
    assert N.wire_size(packet) <= 32760
    assert packet['original_request'] == request()
    with pytest.raises(ValueError): N._metadata([dict(id=str(i), name='好' * 53) for i in range(128)])
