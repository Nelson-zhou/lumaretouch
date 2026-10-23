"""AUTHORED / UNRUN: mocked subprocess/worker transport, not model execution."""
from copy import deepcopy
import json
import os
from pathlib import Path

import numpy as np
import pytest

from lumaretouch_engine.sky_semantic import immutable_input as I
from lumaretouch_engine.sky_semantic import job as J
from lumaretouch_engine.sky_semantic import predict as P
from lumaretouch_engine.sky_semantic import worker as W


SOURCE = {'sha256': 'd' * 64, 'width': 37, 'height': 19}


def packet():
    pixels = np.linspace(0, 1, 19 * 37 * 3, dtype=np.float32).reshape(19, 37, 3)
    return I.from_pixels(pixels, SOURCE)


def returned(value):
    return {'source': deepcopy(SOURCE), 'device': 'cpu',
            'input_sha256': value['input_sha256'], 'input_size': list(value['input_size']),
            '_immutable_input': I.metadata(value),
            'source_image': 'data:image/png;base64,' + W.png(I.array(value))}


class Process:
    pid = 123456
    returncode = None

    def poll(self):
        return self.returncode

    def wait(self):
        self.returncode = -9
        return self.returncode


def process_fixture(monkeypatch):
    from lumaretouch_engine import cpu_memory_budget
    launches = []
    process = Process()
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 16 * 1024**3)
    def launch(command, **kwargs):
        launches.append((command, kwargs))
        return process
    monkeypatch.setattr(J.subprocess, 'Popen', launch)
    return process, launches


def test_derived_job_writes_real_bounded_bytes_with_no_original_path(monkeypatch):
    process, launches = process_fixture(monkeypatch)
    value = packet()
    owner = J.SemanticJob(None, SOURCE, 'cpu', immutable_input=value)
    try:
        request = json.loads((owner.root / 'request.json').read_bytes())
        assert set(request) == {'source', 'device', 'immutable_input'}
        assert request['source'] == SOURCE and request['immutable_input'] == I.metadata(value)
        assert I.read_packet(owner.root, request['immutable_input'], SOURCE) == value
        assert len(launches) == 1 and launches[0][1]['start_new_session'] is True
        value['source']['sha256'] = 'e' * 64
        assert owner.immutable_input['source'] == SOURCE
    finally:
        process.returncode = 0
        owner.cancel()


@pytest.mark.parametrize('path,has_packet', [('/physical-original.png', True), (None, False), ('', False)])
def test_job_input_modes_are_exclusive_before_launch(monkeypatch, path, has_packet):
    _, launches = process_fixture(monkeypatch)
    with pytest.raises(ValueError):
        J.SemanticJob(path, SOURCE, 'cpu', immutable_input=packet() if has_packet else None)
    assert not launches


def test_original_job_keeps_original_decode_request(monkeypatch):
    process, _ = process_fixture(monkeypatch)
    owner = J.SemanticJob('/original.png', SOURCE, 'cpu')
    try:
        assert json.loads((owner.root / 'request.json').read_bytes()) == {
            'path': '/original.png', 'source': SOURCE, 'device': 'cpu'}
        assert not (owner.root / 'input.rgb').exists()
    finally:
        process.returncode = 0
        owner.cancel()


@pytest.mark.parametrize('change', [
    lambda r: r['source'].update(sha256='a' * 64),
    lambda r: r.update(input_sha256='b' * 64),
    lambda r: r.update(device='cuda'),
    lambda r: r.pop('_immutable_input'),
])
def test_job_rejects_misbound_result_and_discards_it(monkeypatch, change):
    process, _ = process_fixture(monkeypatch)
    value = packet()
    owner = J.SemanticJob(None, SOURCE, 'cpu', immutable_input=value)
    root = owner.root
    response = returned(value)
    change(response)
    (root / 'result.json').write_text(json.dumps(response))
    process.returncode = 0
    assert owner.poll() == 'failed' and owner.result is None and owner.error
    assert not root.exists()


def test_job_accepts_exact_input_response_and_cleans_owned_files(monkeypatch):
    process, _ = process_fixture(monkeypatch)
    value = packet()
    owner = J.SemanticJob(None, SOURCE, 'cpu', immutable_input=value)
    root = owner.root
    response = returned(value)
    (root / 'result.json').write_text(json.dumps(response))
    process.returncode = 0
    assert owner.poll() == 'ready' and owner.result == response and not root.exists()


def test_packet_job_preserves_owned_process_timeout_cancellation(monkeypatch):
    process, _ = process_fixture(monkeypatch)
    killed = []
    monkeypatch.setattr(J.os, 'killpg', lambda pid, signal: killed.append((pid, signal)))
    owner = J.SemanticJob(None, SOURCE, 'cpu', immutable_input=packet())
    monkeypatch.setattr(J.time, 'monotonic', lambda: owner.started + 181)
    assert owner.poll() == 'failed' and owner.result is None
    assert killed == [(process.pid, J.signal.SIGKILL)] and not owner.root.exists()


def fake_prediction(pixels, packet=None):
    if packet is None:
        pixels, digest = P.prepare_image(pixels, None)
    else:
        pixels, digest = I.array(packet), packet['input_sha256']
    fields = {key: np.zeros(pixels.shape[:2], np.uint8) for key in ('sky', 'person', 'water')}
    value = {'pixels': pixels, 'input_sha256': digest,
             'input_size': [pixels.shape[1], pixels.shape[0]], 'fields': fields,
             'supports': {key: field.copy() for key, field in fields.items()}, 'device': 'cpu'}
    if packet is not None:
        value['_immutable_input'] = I.metadata(packet)
    return value


def test_worker_derived_route_never_decodes_original_or_resizes(monkeypatch, tmp_path):
    from lumaretouch_engine import prompted_mask_source
    value = packet()
    request = {'source': SOURCE, 'device': 'cpu', 'immutable_input': I.write_packet(tmp_path, value)}
    (tmp_path / 'request.json').write_text(json.dumps(request))
    calls = []
    def forbidden(*args, **kwargs):
        raise AssertionError('The derived route must not use original decoding or preprocessing')
    def predict(pixels, device, *, installation, immutable_input=None):
        assert pixels is None and device == 'cpu' and installation == tmp_path
        assert immutable_input == value
        calls.append(immutable_input)
        return fake_prediction(None, immutable_input)
    monkeypatch.setattr(P, 'activate', lambda: (tmp_path, {}))
    monkeypatch.setattr(P, 'predict', predict)
    monkeypatch.setattr(P, 'prepare_image', forbidden)
    monkeypatch.setattr(prompted_mask_source, 'decode_source', forbidden)
    W.run(tmp_path)
    response = json.loads((tmp_path / 'result.json').read_bytes())
    assert len(calls) == 1 and I.validate_result(value, response) == response
    assert response['proposal_only'] is True and response['review_required'] is True
    assert response['horizon_automatic'] is False and set(response['_fields']) == {'sky', 'person', 'water'}


def test_worker_original_route_keeps_bound_full_decode(monkeypatch, tmp_path):
    from lumaretouch_engine import prompted_mask_source
    original = np.full((19, 37, 3), 12345, np.uint16)
    request = {'path': '/original.png', 'source': SOURCE, 'device': 'cpu'}
    (tmp_path / 'request.json').write_text(json.dumps(request))
    calls = []
    def decode(path, binding, *, device):
        calls.append((path, binding, device))
        return original
    def predict(pixels, device, *, installation):
        assert pixels is original and device == 'cpu' and installation == tmp_path
        return fake_prediction(pixels)
    monkeypatch.setattr(P, 'activate', lambda: (tmp_path, {}))
    monkeypatch.setattr(P, 'predict', predict)
    monkeypatch.setattr(prompted_mask_source, 'decode_source', decode)
    W.run(tmp_path)
    response = json.loads((tmp_path / 'result.json').read_bytes())
    assert calls == [('/original.png', SOURCE, 'cpu')] and '_immutable_input' not in response


def test_worker_dual_route_rejected_before_install_activation(monkeypatch, tmp_path):
    value = packet()
    request = {'path': '/original.png', 'source': SOURCE, 'device': 'cpu',
               'immutable_input': I.write_packet(tmp_path, value)}
    (tmp_path / 'request.json').write_text(json.dumps(request))
    def forbidden():
        raise AssertionError('Malformed requests must fail before installation activation')
    monkeypatch.setattr(P, 'activate', forbidden)
    with pytest.raises(ValueError):
        W.run(tmp_path)


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'directory', 'oversized'])
def test_regular_transport_reader_refuses_unsafe_or_unbounded_files(tmp_path, kind):
    path = tmp_path / 'request.json'
    if kind == 'symlink':
        other = tmp_path / 'other.json'
        other.write_bytes(b'{}')
        path.symlink_to(other)
    elif kind == 'fifo':
        os.mkfifo(path)
    elif kind == 'directory':
        path.mkdir()
    else:
        path.write_bytes(b'x' * 1025)
    with pytest.raises((ValueError, OSError)):
        I.read_regular_bytes(path, 1024)


@pytest.mark.parametrize('name,returncode', [('error.json', 1), ('result.json', 0)])
def test_job_response_reader_refuses_symlinks(monkeypatch, tmp_path, name, returncode):
    process, _ = process_fixture(monkeypatch)
    value = packet()
    owner = J.SemanticJob(None, SOURCE, 'cpu', immutable_input=value)
    outside = tmp_path / name
    outside.write_text(json.dumps({'error': 'wrong file'} if returncode else returned(value)))
    (owner.root / name).symlink_to(outside)
    process.returncode = returncode
    assert owner.poll() == 'failed' and owner.result is None
