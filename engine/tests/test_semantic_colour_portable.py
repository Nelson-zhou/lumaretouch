# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-only acceptance fixtures. All runtime acceptance is UNRUN here.

Qoder should execute these alongside the frozen single-photo tests. Synthetic
frames check ownership/integrity, never photographic quality or model accuracy.
No inference, native fit, downloaded model or licensed photograph is a fixture.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from lumaretouch_engine import reference_color_assets as A
from lumaretouch_engine import semantic_colour_portable as P
from lumaretouch_engine import semantic_colour_preset as E
from lumaretouch_engine import semantic_colour_state as S
from lumaretouch_engine.semantic_colour_analysis import MODEL, PINNED_SHA


def binding(digit='1', document='target'):
    return {'source': {'sha256': digit * 64, 'width': 64, 'height': 64},
            'render_sha256': digit * 64, 'geometry_sha256': digit * 64,
            'state_key': digit * 64, 'document_id': document, 'revision': '1',
            'width': 64, 'height': 64, 'stage': S.STAGE}


def recipe(classes=S.CLASSES, *, committed=True, target_digit='1'):
    target = binding(target_digit)
    reference_binding = binding('2', 'reference')
    reference = {'source': reference_binding['source'], 'render_sha256': '2' * 64, 'asset_id': '3' * 64}
    groups = [{'id': 'global', 'name': 'Global', 'enabled': True, 'mask_id': None,
               'baseline': S.neutral(), 'parameters': S.neutral()}]
    masks = []
    for ident in classes:
        mid = 'semantic_' + ident
        groups.append({'id': ident, 'name': ident, 'enabled': True, 'mask_id': mid,
                       'baseline': S.neutral(), 'parameters': S.neutral()})
        masks.append({'id': mid, 'name': ident, 'domain': S.DOMAIN, 'binding': deepcopy(target),
                      'base': {'width': 16, 'height': 16, 'sha256': target_digit * 64,
                               'encoding': 'asset-float32-le-v1'}, 'objects': []})
    out = S.empty()
    out.update(enabled=True, target=target, reference=reference, groups=groups, masks=masks,
               analysis={'backend': MODEL, 'model_sha256': PINNED_SHA, 'runtime': 'fixture-not-executed',
                         'target_input_sha256': target_digit * 64, 'reference_input_sha256': '2' * 64,
                         'classes': list(S.CLASSES),
                         'analysis_policy': 'bounded-rgb8-view-full-float-spatial-samples-v1'})
    if committed:
        coverage = [{'class': c, 'usable_pixels': 64, 'weighted_coverage': .1} for c in S.CLASSES]
        out['last_review'] = {'proof': '4' * 64, 'reference_binding': reference_binding,
                              'diagnostics': [[0.] * 9 + [1.] for _ in range(7)],
                              'coverage': {'reference': deepcopy(coverage), 'target': deepcopy(coverage)},
                              'warnings': ['Synthetic contract fixture; not photographic acceptance.'],
                              'quality_acceptance': 'UNRUN',
                              'owned_fields': [S.KEY, '_semantic_colour_bundle', '_semantic_colour_mask_assets']}
    return out


def transport_fixture(raw=b'opaque transport fixture, not an authentic image'):
    intent = P.extract(recipe())
    chunks = [np.frombuffer(raw, np.uint8)]
    asset = sha256(raw).hexdigest()
    intent['reference']['asset_id'] = asset
    return {'schema': E.SCHEMA, 'intent': intent,
            'reference_resource': {'included': True, 'asset_id': asset, 'bytes': len(raw),
                                   'chunks': [{'bytes': len(raw), 'sha256': asset}]},
            'chunks': chunks}


class IntentContracts(unittest.TestCase):
    def test_extract_exact_fields_offsets_only_and_canonical_order(self):
        source = recipe()
        source['groups'][0]['baseline'][0] = .25
        source['groups'][0]['parameters'][0] = .75
        source['groups'].reverse()
        intent = P.extract(source)
        self.assertEqual(set(intent), P.FIELDS)
        self.assertEqual([g['id'] for g in intent['groups']], list(P.GROUPS))
        self.assertEqual(intent['groups'][0]['offsets'][0], .5)
        self.assertEqual(set(intent['reference']), {'source', 'render_sha256', 'asset_id'})
        for group in intent['groups']:
            self.assertEqual(set(group), {'id', 'enabled', 'offsets'})
        self.assertNotIn('target', intent)
        self.assertNotIn('baseline', json.dumps(intent))
        self.assertNotIn('mask', json.dumps(intent))

    def test_disabled_state_and_groups_are_explicit_intent_not_bypass(self):
        source = recipe(('hair',))
        source['enabled'] = False
        source['groups'][1]['enabled'] = False
        intent = P.extract(source)
        self.assertFalse(intent['enabled'])
        self.assertFalse(intent['groups'][1]['enabled'])
        with self.assertRaisesRegex(ValueError, 'hair'):
            P.apply_offsets(recipe((), committed=False), intent)

    def test_deleted_groups_do_not_reappear_and_keep_only_target_masks(self):
        intent = P.extract(recipe(('face_skin',)))
        fresh = recipe(committed=False, target_digit='5')
        before = deepcopy(fresh)
        applied = P.apply_offsets(fresh, intent)
        self.assertEqual(fresh, before)
        self.assertEqual([g['id'] for g in applied['groups']], ['global', 'face_skin'])
        self.assertEqual([m['id'] for m in applied['masks']], ['semantic_face_skin'])
        self.assertEqual(applied['masks'][0]['binding'], before['target'])
        self.assertEqual(applied['masks'][0]['base']['sha256'], '5' * 64)
        self.assertEqual(applied['analysis'], before['analysis'])
        self.assertIsNone(applied['last_review'])

    def test_each_target_uses_own_baseline_and_retains_it(self):
        source = recipe(())
        source['groups'][0]['baseline'][0] = .25
        source['groups'][0]['parameters'][0] = .75
        source['strengths'] = [123., 60., 180.]
        intent = P.extract(source)
        for base in (-.5, .75):
            fresh = recipe((), committed=False, target_digit='5')
            fresh['groups'][0]['baseline'][0] = base
            fresh['groups'][0]['parameters'][0] = base
            result = P.apply_offsets(fresh, intent)
            self.assertEqual(result['groups'][0]['parameters'][0], base + .5)
            self.assertEqual(result['groups'][0]['baseline'][0], base)
            self.assertEqual(result['strengths'], source['strengths'])

    def test_requires_committed_review_global_and_matching_reference_review(self):
        with self.assertRaises(ValueError):
            P.extract(recipe(committed=False))
        for mutation in ('global', 'reference', 'support', 'analysis'):
            source = recipe()
            if mutation == 'global':
                source['groups'] = source['groups'][1:]
            elif mutation == 'reference':
                source['last_review']['reference_binding']['render_sha256'] = '8' * 64
            elif mutation == 'support':
                source['last_review']['diagnostics'][1][9] = 0.
            else:
                source['analysis'] = None
                source['enabled'] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                P.extract(source)

    def test_local_mode_and_every_user_primitive_refused_even_disabled(self):
        source = recipe(('hair',))
        source['local_only'] = True
        source['groups'] = source['groups'][1:]
        with self.assertRaises(ValueError):
            P.extract(source)
        primitives = [
            {'kind': 'brush', 'points': [[.1, .1]], 'axes': [[.1, 0.], [0., .1]]},
            {'kind': 'linear', 'start': [0., 0.], 'end': [1., 0.], 'cross': [0., 1.]},
            {'kind': 'radial', 'center': [.5, .5], 'axes': [[.1, 0.], [0., .1]]},
            {'kind': 'semantic', 'channel': 'hair'},
        ]
        for primitive in primitives:
            source = recipe(('hair',))
            source['enabled'] = source['groups'][1]['enabled'] = False
            source['masks'][0]['objects'] = [{'id': 'manual', 'name': 'Manual', 'enabled': False,
                                             'operation': 'add', 'opacity': 1., 'feather': 0., **primitive}]
            with self.subTest(kind=primitive['kind']), self.assertRaises(ValueError):
                P.extract(source)

    def test_orphan_mask_wrong_class_mask_and_absent_base_are_refused(self):
        for mutation in ('orphan', 'wrong_class', 'no_base'):
            source = recipe(('hair',))
            if mutation == 'orphan':
                extra = deepcopy(source['masks'][0])
                extra['id'] = 'semantic_clothes'
                source['masks'].append(extra)
            elif mutation == 'wrong_class':
                source['masks'][0]['id'] = 'semantic_face_skin'
                source['groups'][1]['mask_id'] = 'semantic_face_skin'
            else:
                source['masks'][0]['base'] = None
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                P.extract(source)

    def test_difference_budgets_and_invalid_values_are_strict(self):
        for index, maximum in ((0, 4.), (4, 200.), (6, 1.), (26, 120.), (27, 200.)):
            intent = P.extract(recipe(()))
            intent['groups'][0]['offsets'][index] = maximum
            P.check(intent)
            intent['groups'][0]['offsets'][index] = maximum + .01
            with self.subTest(index=index), self.assertRaises(ValueError):
                P.check(intent)
        for bad in (float('nan'), float('inf'), True, '1', 10 ** 1000):
            intent = P.extract(recipe(()))
            intent['groups'][0]['offsets'][0] = bad
            with self.subTest(value=type(bad).__name__), self.assertRaises(ValueError):
                P.check(intent)

    def test_unknown_fields_groups_duplicates_and_bool_version_are_refused(self):
        for mutation in ('field', 'group', 'duplicate', 'version', 'no_global'):
            intent = P.extract(recipe(()))
            if mutation == 'field':
                intent['baseline'] = S.neutral()
            elif mutation == 'group':
                intent['groups'][0]['id'] = 'sky'
            elif mutation == 'duplicate':
                intent['groups'].append(deepcopy(intent['groups'][0]))
            elif mutation == 'version':
                intent['version'] = True
            else:
                intent['groups'] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                P.check(intent)

    def test_offset_conflict_refuses_entire_target_without_clamping(self):
        intent = P.extract(recipe(('hair',)))
        intent['groups'][0]['offsets'][0] = .5
        intent['groups'][1]['offsets'][6] = -1.
        intent['groups'][1]['enabled'] = False
        fresh = recipe(committed=False)
        before = deepcopy(fresh)
        with self.assertRaisesRegex(ValueError, 'hair'):
            P.apply_offsets(fresh, intent)
        self.assertEqual(fresh, before)

    def test_intentional_nonmonotone_manual_curves_match_native_policy(self):
        source = recipe(())
        source['groups'][0]['parameters'][6:11] = [0., .8, .2, .9, 1.]
        result = P.apply_offsets(recipe((), committed=False), P.extract(source))
        self.assertEqual(result['groups'][0]['parameters'][6:11], [0., .8, .2, .9, 1.])
        self.assertEqual(result['groups'][0]['baseline'][6:11], list(S.KNOTS))

    def test_wrong_mode_reference_and_already_edited_fits_are_refused(self):
        intent = P.extract(recipe(()))
        for mutation in ('mode', 'reference', 'edited'):
            fresh = recipe((), committed=False)
            if mutation == 'mode':
                fresh['mode'] = 'extreme'
            elif mutation == 'reference':
                fresh['reference']['asset_id'] = '8' * 64
            else:
                fresh['groups'][0]['parameters'][0] = .1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                P.apply_offsets(fresh, intent)


class EnvelopeContracts(unittest.TestCase):
    def test_explicit_inclusion_permission_precedes_any_resource_read(self):
        with patch.object(A, 'bundle') as read:
            for include in (False, None, 1, 'yes'):
                with self.assertRaises(ValueError):
                    E.build(recipe(), include_reference=include)
            read.assert_not_called()

    def test_integrity_checks_individual_chunks_full_hash_and_sizes(self):
        good = transport_fixture()
        self.assertEqual(E.check(good)['intent'], good['intent'])
        for mutation in ('chunk_hash', 'full_hash', 'size', 'missing', 'extra', 'float', 'corrupt'):
            bad = deepcopy(good)
            if mutation == 'chunk_hash':
                bad['reference_resource']['chunks'][0]['sha256'] = '0' * 64
            elif mutation == 'full_hash':
                bad['reference_resource']['asset_id'] = bad['intent']['reference']['asset_id'] = '0' * 64
            elif mutation == 'size':
                bad['reference_resource']['bytes'] += 1
            elif mutation == 'missing':
                bad['chunks'] = []
            elif mutation == 'extra':
                bad['source_parameters'] = S.neutral()
            elif mutation == 'float':
                bad['chunks'] = [bad['chunks'][0].astype(np.float32)]
            else:
                bad['chunks'][0] = bad['chunks'][0].copy()
                bad['chunks'][0][0] ^= 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                E.check(bad)

    def test_mutable_chunk_input_is_snapshotted_and_cannot_be_made_writeable(self):
        envelope = transport_fixture()
        mutable = envelope['chunks'][0].copy()
        envelope['chunks'][0] = mutable
        checked = E.check(envelope)
        old = checked['chunks'][0].tobytes()
        mutable[0] ^= 1
        self.assertEqual(checked['chunks'][0].tobytes(), old)
        with self.assertRaises(ValueError):
            checked['chunks'][0].setflags(write=True)

    def test_resource_budgets_and_contiguous_byte_type_are_not_coerced(self):
        for mutation in ('count', 'size', 'strided', 'list', 'bool_size'):
            bad = transport_fixture()
            if mutation == 'count':
                bad['chunks'] *= E.MAX_CHUNKS + 1
            elif mutation == 'size':
                bad['reference_resource']['bytes'] = A.MAX_BYTES + 1
            elif mutation == 'strided':
                bad['chunks'] = [bad['chunks'][0][::2]]
            elif mutation == 'list':
                bad['chunks'] = [bad['chunks'][0].tolist()]
            else:
                bad['reference_resource']['chunks'][0]['bytes'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                E.check(bad)

    def test_valid_transport_hash_does_not_bypass_authentic_image_validation(self):
        envelope = transport_fixture()
        with tempfile.TemporaryDirectory() as root, patch.object(A, 'cache_root', return_value=Path(root)):
            with self.assertRaises((ValueError, zipfile.BadZipFile)):
                E.hydrate(envelope)

    def test_authentic_full_float_reference_round_trip_and_small_prepared_metadata(self):
        from lumaretouch_engine.reference_color_review import ColorInput
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source_root = root / 'source'
            target_root = root / 'target'
            source_root.mkdir()
            target_root.mkdir()
            rgb = np.linspace(-.5, 2., 64 * 64 * 3, dtype=np.float32).reshape(64, 64, 3)
            rgb[0, 0] = [-0., -.25, 4.]
            authentic = np.ones((64, 64), np.bool_)
            authentic[4:8, 4:8] = False
            frame = ColorInput('reference', '1', binding('2')['source'], '6' * 64, rgb, authentic)
            reference = A.save(source_root, frame)
            source = recipe(())
            source['reference'] = reference
            source['last_review']['reference_binding']['source'] = reference['source']
            source['last_review']['reference_binding']['render_sha256'] = reference['render_sha256']
            A._bundle.cache_clear()
            prepared = None
            try:
                with patch.object(A, 'cache_root', return_value=source_root):
                    prepared = E.prepare_export(source, include_reference=True)
                metadata = prepared.metadata
                self.assertTrue(metadata['reference_included'])
                self.assertEqual(metadata['reference_sha256'], reference['asset_id'])
                self.assertEqual(metadata['quality_acceptance'], 'UNRUN')
                self.assertLess(len(json.dumps(metadata)), 2048)
                self.assertNotIn('chunks', metadata)
                self.assertNotIn('path', metadata)
                detached = prepared.metadata
                detached['file_sha256'] = '0' * 64
                self.assertEqual(prepared.metadata, metadata)
                with self.assertRaises(TypeError):
                    prepared._metadata['file_sha256'] = '0' * 64
                exported = root / 'export.lrtcolour'
                self.assertEqual(E.write_prepared(prepared, exported), metadata)
                self.assertEqual(sha256(exported.read_bytes()).hexdigest(), metadata['file_sha256'])
                self.assertEqual(exported.stat().st_size, metadata['file_bytes'])
                envelope = E.load_file(exported)
                with patch.object(A, 'cache_root', return_value=target_root):
                    intent = E.hydrate(envelope)
                    restored = A.load(target_root, intent['reference'])
                np.testing.assert_array_equal(restored.rgb.view(np.uint32), rgb.view(np.uint32))
                np.testing.assert_array_equal(restored.authentic_mask, authentic)
                self.assertEqual((target_root / (reference['asset_id'] + '.npz')).read_bytes(),
                                 (source_root / (reference['asset_id'] + '.npz')).read_bytes())
            finally:
                if prepared is not None:
                    prepared.close()
                A._bundle.cache_clear()

    def test_staged_tamper_and_unrequested_overwrite_are_refused(self):
        from lumaretouch_engine.preset_store import PresetStorageError
        with patch.object(E, 'build', return_value=transport_fixture()):
            prepared = E.prepare_export(recipe(), include_reference=True)
        try:
            with tempfile.TemporaryDirectory() as root:
                destination = Path(root) / 'exists.lrtcolour'
                destination.write_bytes(b'keep existing bytes')
                with self.assertRaises(PresetStorageError):
                    E.write_prepared(prepared, destination)
                self.assertEqual(destination.read_bytes(), b'keep existing bytes')
                Path(prepared._path).write_bytes(b'tampered after preparation')
                with self.assertRaises(ValueError):
                    E.write_prepared(prepared, Path(root) / 'new.lrtcolour')
                self.assertFalse((Path(root) / 'new.lrtcolour').exists())
        finally:
            prepared.close()

    def test_explicit_overwrite_publishes_exact_staged_hash(self):
        with patch.object(E, 'build', return_value=transport_fixture()):
            prepared = E.prepare_export(recipe(), include_reference=True)
        try:
            with tempfile.TemporaryDirectory() as root:
                destination = Path(root) / 'existing.lrtcolour'
                destination.write_bytes(b'old file')
                metadata = E.write_prepared(prepared, destination, overwrite=True)
                self.assertEqual(sha256(destination.read_bytes()).hexdigest(), metadata['file_sha256'])
                self.assertEqual(E.load_file(destination)['intent'], transport_fixture()['intent'])
        finally:
            prepared.close()

    def test_archive_unknown_paths_duplicate_json_and_compressed_entries_refused(self):
        envelope = transport_fixture()
        manifest = {k: envelope[k] for k in ('schema', 'intent', 'reference_resource')}
        for mutation in ('path', 'json', 'compression', 'duplicate'):
            with tempfile.TemporaryDirectory() as root:
                path = Path(root) / 'bad.lrtcolour'
                with zipfile.ZipFile(path, 'w') as archive:
                    raw = json.dumps(manifest)
                    if mutation == 'json':
                        raw = raw.replace('"schema":', '"schema": "duplicate", "schema":', 1)
                    archive.writestr('manifest.json', raw)
                    name = '../reference.bin' if mutation == 'path' else 'reference/00.bin'
                    archive.writestr(name, envelope['chunks'][0].tobytes(),
                                     compress_type=zipfile.ZIP_DEFLATED if mutation == 'compression' else zipfile.ZIP_STORED)
                    if mutation == 'duplicate':
                        archive.writestr('manifest.json', raw)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    E.load_file(path)


if __name__ == '__main__':
    unittest.main()
