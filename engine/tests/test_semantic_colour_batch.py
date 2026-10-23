# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic batch contracts, authored but entirely UNRUN in this session.

No photographic acceptance is implied. Tests mock inference/native fit and the
authentic image decoder where that boundary is not under test. Small ZIP member
payloads below are transport fixtures, not photographs or valid NPY images.
"""
from copy import deepcopy
from hashlib import sha256
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import numpy as np

from lumaretouch_engine import semantic_colour_analysis as Analysis
from lumaretouch_engine import semantic_colour_batch_assets as Assets
from lumaretouch_engine import semantic_colour_batch_fit as Fit
from lumaretouch_engine import semantic_colour_batch_ledger as Ledger
from lumaretouch_engine import semantic_colour_batch_reference as Reference
from lumaretouch_engine import semantic_colour_state as S
from lumaretouch_engine.semantic_colour_host import OWNED
from lumaretouch_engine.semantic_colour_project import BUNDLE
from lumaretouch_engine.semantic_colour_assets import KEY as MASK_ASSETS


def _binding(digit='1', document='reference'):
    return {'source': {'sha256': digit * 64, 'width': 64, 'height': 64},
            'render_sha256': '3' * 64, 'geometry_sha256': digit * 64,
            'state_key': digit * 64, 'document_id': document, 'revision': '1',
            'width': 64, 'height': 64, 'stage': S.STAGE}


def _reference_cache():
    binding = _binding()
    out = {'version': 1,
           'reference': {'source': deepcopy(binding['source']), 'render_sha256': binding['render_sha256'],
                         'asset_id': '4' * 64},
           'binding': binding,
           'analysis': {'backend': Analysis.MODEL, 'model_sha256': Analysis.PINNED_SHA,
                        'runtime': 'synthetic-contract-runtime', 'target_input_sha256': '2' * 64,
                        'reference_input_sha256': '2' * 64, 'classes': list(S.CLASSES),
                        'analysis_policy': 'bounded-rgb8-view-full-float-spatial-samples-v1'},
           'samples': [[-.125 + i / 128., .25, 1.5, 0., .8] for i in range(32)],
           'coverage': [{'class': c, 'usable_pixels': 32 if i == 0 else 0,
                         'weighted_coverage': .8 if i == 0 else 0.}
                        for i, c in enumerate(S.CLASSES)]}
    out['proof'] = Fit.cache_proof(out)
    return out


def _reproof(value):
    value['proof'] = Fit.cache_proof(value)
    return value


def _intent(cache):
    return {'version': 1, 'algorithm': S.ALGORITHM, 'reference': deepcopy(cache['reference']),
            'mode': 'harmonious', 'strengths': [100., 100., 100.], 'enabled': True,
            'offset_policy': 'recompute-then-user-offset-v1',
            'class_policy': 'require-requested-support-v1',
            'groups': [{'id': 'global', 'enabled': True, 'offsets': [0.] * S.PARAMS}]}


def _archive_chunks(names=('rgb.npy', 'authentic.npy', 'metadata.npy')):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name in names:
            archive.writestr(name, b'not an image: bounded admission fixture')
    raw = stream.getvalue()
    chunks = [np.frombuffer(raw[:11], np.uint8), np.frombuffer(raw[11:53], np.uint8),
              np.frombuffer(raw[53:], np.uint8)]
    reference = {'source': _binding()['source'], 'render_sha256': '3' * 64,
                 'asset_id': sha256(raw).hexdigest()}
    return reference, chunks


class ReferenceCacheContracts(unittest.TestCase):
    def test_exact_owned_identity_and_detached_full_float_samples(self):
        original = _reference_cache()
        checked = Fit.check_reference(original)
        self.assertEqual(checked, original)
        self.assertEqual(set(checked), {'version', 'reference', 'binding', 'analysis',
                                       'samples', 'coverage', 'proof'})
        self.assertEqual(checked['samples'][0][:3], [-.125, .25, 1.5])
        checked['samples'][0][0] = .9
        checked['binding']['source']['sha256'] = '8' * 64
        self.assertNotEqual(checked, original)
        self.assertEqual(original['samples'][0][0], -.125)
        self.assertEqual(original['binding']['source']['sha256'], '1' * 64)

    def test_tampering_without_new_proof_is_refused(self):
        for key in ('samples', 'coverage', 'runtime', 'asset_id'):
            value = _reference_cache()
            if key == 'samples':
                value['samples'][0][0] = .4
            elif key == 'coverage':
                value['coverage'][0]['usable_pixels'] += 1
            elif key == 'runtime':
                value['analysis']['runtime'] = 'changed-runtime'
            else:
                value['reference']['asset_id'] = '8' * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                Fit.check_reference(value)

    def test_new_proof_cannot_make_reference_binding_or_model_evidence_valid(self):
        for kind in ('source', 'render', 'model', 'backend', 'runtime', 'classes', 'target_input'):
            value = _reference_cache()
            if kind == 'source':
                value['binding']['source']['sha256'] = '7' * 64
            elif kind == 'render':
                value['binding']['render_sha256'] = '7' * 64
            elif kind == 'model':
                value['analysis']['model_sha256'] = '7' * 64
            elif kind == 'backend':
                value['analysis']['backend'] = 'pretend-model'
            elif kind == 'runtime':
                value['analysis']['runtime'] = ''
            elif kind == 'classes':
                value['analysis']['classes'].reverse()
            else:
                value['analysis']['target_input_sha256'] = '7' * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                Fit.check_reference(_reproof(value))

    def test_bounded_rgb_class_weight_and_coverage_contracts(self):
        for kind in ('short', 'long', 'columns', 'sample_bool', 'sample_string', 'rows_tuple',
                     'rgb', 'class_fraction', 'class_range',
                     'weight_zero', 'weight_large', 'coverage_class', 'coverage_count',
                     'coverage_bool', 'extra_field', 'bool_version'):
            value = _reference_cache()
            if kind == 'short':
                value['samples'] = value['samples'][:31]
            elif kind == 'long':
                value['samples'] = value['samples'] * 193
            elif kind == 'columns':
                value['samples'] = [row[:-1] for row in value['samples']]
            elif kind == 'sample_bool':
                value['samples'][0][0] = True
            elif kind == 'sample_string':
                value['samples'][0][0] = '0.1'
            elif kind == 'rows_tuple':
                value['samples'] = tuple(value['samples'])
            elif kind == 'rgb':
                value['samples'][0][0] = 16.01
            elif kind == 'class_fraction':
                value['samples'][0][3] = .5
            elif kind == 'class_range':
                value['samples'][0][3] = 6.
            elif kind == 'weight_zero':
                value['samples'][0][4] = 0.
            elif kind == 'weight_large':
                value['samples'][0][4] = 1.01
            elif kind == 'coverage_class':
                value['coverage'][0]['class'] = 'sky'
            elif kind == 'coverage_count':
                value['coverage'][0]['usable_pixels'] = Analysis.LIMIT + 1
            elif kind == 'coverage_bool':
                value['coverage'][0]['usable_pixels'] = True
            elif kind == 'extra_field':
                value['target_masks'] = []
            else:
                value['version'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                Fit.check_reference(_reproof(value))

    def test_nonfinite_sample_values_never_get_an_accepted_cache_proof(self):
        for bad in (float('nan'), float('inf'), float('-inf')):
            value = _reference_cache()
            value['samples'][0][0] = bad
            with self.subTest(value=str(bad)), self.assertRaises(ValueError):
                Fit.check_reference(value)

    def test_reference_builder_uses_mocked_actual_receipt_and_samples_only(self):
        expected = _reference_cache()
        image = np.zeros((16, 16, 3), np.uint8)
        rgb = np.zeros((16, 16, 3), np.float32)
        probabilities = np.zeros((16, 16, 6), np.float32)
        rows = np.asarray(expected['samples'], np.float64)
        receipt = {'model_sha256': Analysis.PINNED_SHA, 'runtime': expected['analysis']['runtime'],
                   'input_sha256': expected['analysis']['reference_input_sha256']}
        with patch.object(Analysis, 'infer', return_value=(probabilities, receipt)) as infer, \
                patch.object(Analysis, 'samples', return_value=(rows, probabilities, expected['coverage'])) as samples:
            actual = Fit.reference({'reference': expected['reference'], 'binding': expected['binding']}, image, rgb)
        self.assertEqual(actual, expected)
        infer.assert_called_once()
        samples.assert_called_once()
        self.assertIs(infer.call_args.args[0], image)
        self.assertIs(samples.call_args.args[0], rgb)
        self.assertIs(samples.call_args.args[1], probabilities)

    def test_target_refuses_different_reference_before_any_inference(self):
        cache = _reference_cache()
        intent = _intent(cache)
        intent['reference']['asset_id'] = '9' * 64
        with patch.object(Analysis, 'infer') as infer:
            with self.assertRaises(ValueError):
                Fit.target({'intent': intent, 'reference_analysis': cache,
                            'binding': _binding('5', 'target')}, None, None)
            infer.assert_not_called()

    def test_target_refuses_changed_actual_model_or_runtime_before_fit(self):
        from lumaretouch_engine import semantic_colour_native as Native
        cache = _reference_cache()
        for kind in ('model', 'runtime'):
            receipt = {'model_sha256': Analysis.PINNED_SHA, 'runtime': cache['analysis']['runtime'],
                       'input_sha256': '5' * 64}
            receipt['model_sha256' if kind == 'model' else 'runtime'] = 'changed'
            with self.subTest(kind=kind), patch.object(Analysis, 'infer', return_value=(None, receipt)), \
                    patch.object(Analysis, 'samples') as samples, patch.object(Native, 'fit') as fit:
                with self.assertRaises(ValueError):
                    Fit.target({'intent': _intent(cache), 'reference_analysis': cache,
                                'binding': _binding('5', 'target')}, None, None)
                samples.assert_not_called()
                fit.assert_not_called()


class PrivateProposalContracts(unittest.TestCase):
    def setUp(self):
        self.assets = Assets.ProposalAssets()
        self.addCleanup(self.assets.close)
        self.record = {'proof': '1' * 64, 'note': 'synthetic fixture', 'quality_acceptance': 'UNRUN'}

    def test_exact_descriptor_round_trip_does_not_return_shared_mutable_record(self):
        descriptor = self.assets.put(self.record)
        self.assertEqual(set(descriptor), {'id', 'sha256', 'bytes', 'proof'})
        path = self.assets.root / (descriptor['id'] + '.json')
        self.assertEqual(path.stat().st_size, descriptor['bytes'])
        self.assertEqual(sha256(path.read_bytes()).hexdigest(), descriptor['sha256'])
        first = self.assets.get(descriptor)
        first['note'] = 'changed copy'
        self.assertEqual(self.assets.get(descriptor), self.record)
        self.assertEqual(self.assets.used, descriptor['bytes'])

    def test_changed_descriptor_identity_is_refused(self):
        descriptor = self.assets.put(self.record)
        for key, value in (('id', '0' * 32), ('sha256', '0' * 64), ('bytes', descriptor['bytes'] + 1),
                           ('proof', '0' * 64), ('extra', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.assets.get({**descriptor, key: value})

    def test_same_size_content_tamper_and_truncation_are_refused(self):
        for same_size in (True, False):
            descriptor = self.assets.put(self.record)
            path = self.assets.root / (descriptor['id'] + '.json')
            raw = path.read_bytes()
            changed = raw.replace(b'fixture', b'fixturE') if same_size else raw[:-1]
            self.assertNotEqual(raw, changed)
            path.write_bytes(changed)
            with self.subTest(same_size=same_size), self.assertRaises(ValueError):
                self.assets.get(descriptor)

    def test_symlink_is_not_followed(self):
        descriptor = self.assets.put(self.record)
        path = self.assets.root / (descriptor['id'] + '.json')
        other = self.assets.root / 'other.json'
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
        with self.assertRaises(ValueError):
            self.assets.get(descriptor)

    def test_full_record_reservation_and_record_size_limits_are_enforced(self):
        with patch.object(Assets, 'LIMIT', Assets.RECORD_LIMIT):
            descriptor = self.assets.put(self.record)
            used = self.assets.used
            with self.assertRaises(ValueError):
                self.assets.put(self.record)
            self.assertEqual(self.assets.used, used)
            self.assertEqual(list(self.assets.entries), [descriptor['id']])
        self.assets.drop(descriptor['id'])
        with patch.object(Assets, 'RECORD_LIMIT', 16):
            with self.assertRaises(ValueError):
                self.assets.put(self.record)
        self.assertEqual(self.assets.used, 0)
        self.assertEqual(self.assets.entries, {})
        self.assertEqual(list(self.assets.root.iterdir()), [])

    def test_release_drops_only_bound_plan_and_is_idempotent(self):
        one = self.assets.put(self.record)
        two = self.assets.put({**self.record, 'note': 'second fixture'})
        self.assets.bind('one', [one])
        self.assets.bind('two', [two])
        self.assets.release('one')
        self.assets.release('one')
        with self.assertRaises(ValueError):
            self.assets.get(one)
        self.assertEqual(self.assets.get(two)['note'], 'second fixture')
        self.assertEqual(self.assets.used, two['bytes'])
        self.assertFalse((self.assets.root / (one['id'] + '.json')).exists())

    def test_prune_obeys_existing_store_eviction_and_close_releases_all_files(self):
        expired = self.assets.put(self.record)
        live = self.assets.put(self.record)
        self.assets.bind('expired', [expired])
        self.assets.bind('live', [live])
        store = SimpleNamespace(pending={'expired': object(), 'live': object()}, clock=Mock(return_value=10.))
        store._prune = Mock(side_effect=lambda now: store.pending.pop('expired'))
        self.assets.prune(store)
        store._prune.assert_called_once_with(10.)
        self.assertEqual(set(self.assets.plans), {'live'})
        self.assertEqual(self.assets.get(live), self.record)
        with self.assertRaises(ValueError):
            self.assets.get(expired)
        root = self.assets.root
        self.assets.close()
        self.assertFalse(root.exists())
        self.assertEqual((self.assets.used, self.assets.entries, self.assets.plans), (0, {}, {}))


class ChunkAdmissionContracts(unittest.TestCase):
    def test_cross_chunk_reads_and_bounded_absolute_relative_end_seeks(self):
        chunks = [np.frombuffer(part, np.uint8) for part in (b'abc', b'defgh', b'ij')]
        with Reference.ChunkReader(chunks) as reader:
            self.assertTrue(reader.readable())
            self.assertTrue(reader.seekable())
            self.assertEqual(reader.read(4), b'abcd')
            self.assertEqual(reader.tell(), 4)
            self.assertEqual(reader.read(2), b'ef')
            self.assertEqual(reader.seek(-2, 1), 4)
            self.assertEqual(reader.read(0), b'')
            self.assertEqual(reader.tell(), 4)
            self.assertEqual(reader.seek(-3, 2), 7)
            self.assertEqual(reader.read(100), b'hij')
            self.assertEqual(reader.read(), b'')
            self.assertEqual(reader.seek(0), 0)
            self.assertEqual(reader.read(None), b'abcdefghij')

    def test_invalid_seek_does_not_change_position(self):
        with Reference.ChunkReader([np.frombuffer(b'abc', np.uint8)]) as reader:
            reader.seek(1)
            for offset, whence in ((-1, 0), (4, 0), (-2, 1), (1, 2), (0, 3)):
                with self.subTest(offset=offset, whence=whence), self.assertRaises(ValueError):
                    reader.seek(offset, whence)
                self.assertEqual(reader.tell(), 1)

    def test_fractional_and_other_noninteger_seek_or_read_fail_without_advancing(self):
        with Reference.ChunkReader([np.frombuffer(b'abcd', np.uint8)]) as reader:
            reader.seek(1)
            for offset, whence in ((.5, 0), ('1', 0), (True, 0), (None, 0),
                                   (0, .5), (0, '0'), (0, True)):
                with self.subTest(offset=offset, whence=whence), self.assertRaises(TypeError):
                    reader.seek(offset, whence)
                self.assertEqual(reader.tell(), 1)
            for size in (.5, '1', True):
                with self.subTest(size=size), self.assertRaises(TypeError):
                    reader.read(size)
                self.assertEqual(reader.tell(), 1)
            self.assertEqual(reader.read(2), b'bc')

    def test_admission_passes_exact_chunks_to_authentic_decoder_only_after_checks(self):
        reference, chunks = _archive_chunks()
        with patch.object(Reference, 'available_estimate', return_value=1 << 40), \
                patch.object(Reference.A, 'hydrate') as hydrate:
            Reference.hydrate(reference, chunks)
        hydrate.assert_called_once()
        self.assertEqual(hydrate.call_args.args[0], reference)
        self.assertIs(hydrate.call_args.args[1], chunks)

    def test_wrong_digest_or_zip_directory_never_reaches_authentic_decoder(self):
        for kind in ('digest', 'directory', 'raw_budget'):
            reference, chunks = _archive_chunks(('rgb.npy', 'wrong.npy', 'metadata.npy')
                                                if kind == 'directory' else ('rgb.npy', 'authentic.npy', 'metadata.npy'))
            if kind == 'digest':
                reference['asset_id'] = '0' * 64
            with self.subTest(kind=kind), patch.object(Reference, 'available_estimate', return_value=1 << 40), \
                    patch.object(Reference.A, 'hydrate') as hydrate, \
                    patch.object(Reference.A, 'MAX_RAW_BYTES', 1 if kind == 'raw_budget' else Reference.A.MAX_RAW_BYTES):
                with self.assertRaises(ValueError):
                    Reference.hydrate(reference, chunks)
                hydrate.assert_not_called()

    def test_compressed_and_expanded_memory_guards_precede_decoder(self):
        reference, chunks = _archive_chunks()
        compressed = sum(part.size for part in chunks)
        for available in (0, 2 * compressed + 128 * 1024 * 1024):
            with self.subTest(available=available), patch.object(Reference, 'available_estimate', return_value=available), \
                    patch.object(Reference.A, 'hydrate') as hydrate:
                with self.assertRaises(ValueError):
                    Reference.hydrate(reference, chunks)
                hydrate.assert_not_called()

    def test_invalid_chunk_types_counts_sizes_and_total_are_rejected(self):
        reference, chunks = _archive_chunks()
        for bad in ([], chunks * 14, [chunks[0].astype(np.float32)], [chunks[0][::2]],
                    [chunks[0].tolist()], [np.empty(0, np.uint8)]):
            with self.subTest(type=type(bad[0]).__name__ if bad else 'empty'), \
                    patch.object(Reference.A, 'hydrate') as hydrate:
                with self.assertRaises(ValueError):
                    Reference.hydrate(reference, bad)
                hydrate.assert_not_called()
        with patch.object(Reference.A, 'MAX_BYTES', 1), patch.object(Reference.A, 'hydrate') as hydrate:
            with self.assertRaises(ValueError):
                Reference.hydrate(reference, chunks)
            hydrate.assert_not_called()

    def test_existing_cache_path_is_admitted_before_authentic_hydration(self):
        from lumaretouch_engine import semantic_colour_canvas as Canvas
        reference, _ = _archive_chunks()
        calls = []
        with patch.object(Canvas, 'reference_admission', side_effect=lambda ref: calls.append(('admit', ref))), \
                patch.object(Reference.A, 'hydrate', side_effect=lambda ref, chunks: calls.append(('hydrate', ref, chunks))):
            Reference.hydrate(reference, None)
        self.assertEqual(calls, [('admit', reference), ('hydrate', reference, None)])


def _state(amount=100., exposure=0.):
    recipe = S.empty()
    recipe['strengths'][0] = amount
    return {S.KEY: recipe, BUNDLE: None, MASK_ASSETS: {}, '_exposure': [exposure]}


class _Versions:
    def __init__(self):
        self.checked = []

    def check_advance(self, row):
        self.checked.append(row['document_id'])

    def advance(self, row):
        row['revision'] += 1

    def version(self, row):
        return SimpleNamespace(document_id=row['document_id'], revision=row['revision'])

    def find(self, rows, document_id):
        return next(((i, row) for i, row in enumerate(rows) if row['document_id'] == document_id), None)


def _owner(count=1):
    rows = [{'path': f'/synthetic/{i}.png', 'document_id': f'document-{i}', 'revision': 1,
             'state': _state(), 'undo': [], 'redo': []} for i in range(count)]
    documents = SimpleNamespace(rows=lambda: rows, current_index=lambda: -1, remember_current=Mock())
    editor = SimpleNamespace(replay=Mock(), invalidate=Mock(), mark_dirty=Mock(),
                             status=Mock(return_value={'fixture': True}))
    return SimpleNamespace(documents=documents, editor=editor, versions=_Versions(),
                           sequence=0, ledger={}, clock=lambda: 10., monotonic=lambda: 20,
                           history_limit=10, emit=Mock(), last_result=None)


def _publish(owner):
    planned = []
    for index, row in enumerate(owner.documents.rows()):
        before = deepcopy(row['state'])
        after = _state(75. - index)
        planned.append((index, row, before, after))
    bid, frame = Ledger.publish(owner, planned, policy='synthetic-contract-policy')
    return bid, frame


class OwnedRestoreContracts(unittest.TestCase):
    def test_undo_and_redo_restore_only_owned_fields_preserving_later_ordinary_edits(self):
        owner = _owner()
        bid, frame = _publish(owner)
        self.assertIsNone(frame)
        row = owner.documents.rows()[0]
        later = {'crop': [.1, .2, .8, .9]}
        row['state'] = {**row['state'], '_exposure': [1.25], '_later_ordinary_edit': later}
        ordinary = {key: value for key, value in row['state'].items() if key not in OWNED}
        before_write = Mock()
        undo = Ledger.restore(owner, {'batch_id': bid, 'action': 'undo'}, before_write=before_write)
        before_write.assert_called_once()
        self.assertEqual(undo['restored'], [0])
        self.assertEqual(row['state'][S.KEY]['strengths'][0], 100.)
        self.assertEqual({key: value for key, value in row['state'].items() if key not in OWNED}, ordinary)
        self.assertIs(row['state']['_later_ordinary_edit'], later)
        self.assertTrue(owner.ledger[bid]['undone'])
        row['state']['_exposure'] = [1.75]
        redo = Ledger.restore(owner, {'batch_id': bid, 'action': 'redo'})
        self.assertEqual(redo['event'], 'batch_redone')
        self.assertEqual(row['state'][S.KEY]['strengths'][0], 75.)
        self.assertEqual(row['state']['_exposure'], [1.75])
        self.assertIs(row['state']['_later_ordinary_edit'], later)
        self.assertFalse(owner.ledger[bid]['undone'])
        owner.editor.replay.assert_not_called()

    def test_subsequent_owned_edit_refuses_the_entire_multi_target_restore(self):
        owner = _owner(2)
        bid, _ = _publish(owner)
        rows = owner.documents.rows()
        rows[0]['state'] = {**rows[0]['state'], '_exposure': [2.]}
        rows[1]['state'] = deepcopy(rows[1]['state'])
        rows[1]['state'][S.KEY]['strengths'][0] = 22.
        before = deepcopy(rows)
        before_write = Mock()
        owner.editor.mark_dirty.reset_mock()
        with self.assertRaisesRegex(ValueError, '整组未修改'):
            Ledger.restore(owner, {'batch_id': bid, 'action': 'undo'}, before_write=before_write)
        self.assertEqual(rows, before)
        self.assertFalse(owner.ledger[bid]['undone'])
        before_write.assert_not_called()
        owner.editor.mark_dirty.assert_not_called()
        owner.editor.replay.assert_not_called()
        owner.emit.assert_not_called()

    def test_redo_conflicts_with_owned_edit_made_after_undo(self):
        owner = _owner()
        bid, _ = _publish(owner)
        Ledger.restore(owner, {'batch_id': bid, 'action': 'undo'})
        row = owner.documents.rows()[0]
        row['state'] = deepcopy(row['state'])
        row['state'][S.KEY]['mode'] = 'extreme'
        before = deepcopy(row)
        with self.assertRaisesRegex(ValueError, '整组未修改'):
            Ledger.restore(owner, {'batch_id': bid, 'action': 'redo'})
        self.assertEqual(row, before)
        self.assertTrue(owner.ledger[bid]['undone'])

    def test_wrong_path_missing_target_or_wrong_undo_state_never_starts_write(self):
        for mutation in ('path', 'missing', 'redo_before_undo'):
            owner = _owner()
            bid, _ = _publish(owner)
            row = owner.documents.rows()[0]
            if mutation == 'path':
                row['path'] = '/synthetic/different.png'
            elif mutation == 'missing':
                owner.documents.rows().clear()
            before_write = Mock()
            action = 'redo' if mutation == 'redo_before_undo' else 'undo'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                Ledger.restore(owner, {'batch_id': bid, 'action': action}, before_write=before_write)
            before_write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
