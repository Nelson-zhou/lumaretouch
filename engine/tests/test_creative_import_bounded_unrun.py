"""AUTHORED / UNRUN. Header arithmetic is not 24MP decoding or RSS evidence.

Native parity cases need the packaged existing creative-layer ABI. Missing
native/codec dependencies are explicit skips, not successful image acceptance.
"""
import ast
from io import BytesIO
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib

from lumaretouch_engine import creative_document_import_bounded as bounded
from lumaretouch_engine.creative_document_assets import AssetStore


def _chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(payload, zlib.crc32(kind)) & 0xffffffff))


def _exif(orientation):
    return (b'II*\0' + struct.pack('<I', 8) + struct.pack('<H', 1)
            + struct.pack('<HHI', 274, 3, 1) + struct.pack('<H', orientation)
            + b'\0\0' + struct.pack('<I', 0))


def _png(width, height, bits, kind, raw=b'', ancillary=()):
    """Container fixtures only. Callers supply real filter+sample rows for decode."""
    header = struct.pack('>IIBBBBB', width, height, bits, kind, 0, 0, 0)
    return (bounded.PNG_SIGNATURE + _chunk(b'IHDR', header)
            + b''.join(_chunk(key, value) for key, value in ancillary)
            + _chunk(b'IDAT', zlib.compress(raw)) + _chunk(b'IEND', b''))


def _text(kind, key, value, *, compressed=False):
    if isinstance(value, str):
        value = value.encode('utf-8' if kind == b'iTXt' else 'latin-1')
    prefix = key.encode('latin-1') + b'\0'
    if kind == b'zTXt':
        return kind, prefix + b'\0' + zlib.compress(value)
    if kind == b'iTXt':
        return kind, prefix + bytes((int(compressed), 0)) + b'\0\0' + (zlib.compress(value) if compressed else value)
    return kind, prefix + value


def _xmp(orientation):
    return ('<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description xmlns:tiff="http://ns.adobe.com/tiff/1.0/" '
            f'tiff:Orientation="{orientation}"/></rdf:RDF></x:xmpmeta>')


def _raw_exif(orientation):
    value = b'Exif\0\0' + _exif(orientation)
    return f'\nexif\n{len(value):8d}\n{value.hex()}\n'


class BoundedImportPreflightContracts(unittest.TestCase):
    def test_edited_metadata_distinguishes_same_size_png16_text_flip(self):
        original = _png(3, 3, 16, 2, ancillary=(
            _text(b'iTXt', 'XML:com.adobe.xmp', _xmp(2)),))
        with patch.object(bounded, '_decode_png') as decode:
            info = bounded.inspect_encoded_source(original)
            decode.assert_not_called()
        self.assertEqual((info['width'], info['height']), (3, 3))
        self.assertEqual(info['orientation'], 2)
        self.assertEqual(info['working_orientation'], 1)
        self.assertEqual(info['original_bytes'], len(original))

    def test_edited_metadata_preserves_standard_png16_orientation(self):
        for orientation in range(1, 9):
            info = bounded.inspect_encoded_source(_png(2, 3, 16, 2,
                ancillary=((b'eXIf', _exif(orientation)),)))
            self.assertEqual(info['orientation'], orientation)
            self.assertEqual(info['working_orientation'], orientation)
        info = bounded.inspect_encoded_source(_png(2, 3, 8, 2, ancillary=(
            _text(b'iTXt', 'XML:com.adobe.xmp', _xmp(6)),)))
        self.assertEqual(info['working_orientation'], info['orientation'])

    def test_24mp_admission_charges_final_copy_and_does_not_use_96n(self):
        # Deliberately header-only sizing fixture. No pixel decode is alleged.
        original = _png(6000, 4000, 16, 6)
        plan = bounded.inspect_import(original, max_bytes=2_000_000_000)
        self.assertEqual(plan.decoded_sample_bytes, 24_000_000 * 8)
        overhead = bounded.METADATA_RESERVE + bounded.SAFETY_RESERVE
        self.assertEqual(dict(plan.phases)['freeze'], len(original) + 32 * 24_000_000 + overhead)
        self.assertLess(plan.peak_bytes, 2_000_000_000)
        self.assertFalse(plan.runtime_verified)
        self.assertIn('conservative-native-reserves', plan.bounds_kind)
        with self.assertRaisesRegex(bounded.ImportBudgetExceeded, 'working set'):
            bounded.inspect_import(original, max_bytes=plan.peak_bytes - 1)

    def test_only_validated_final_plan_can_raise_fallback_eligible_budget_error(self):
        for original, maximum in (
                (_png(1, 1, 8, 2), 1),
                (_png(6000, 4000, 16, 6, ancillary=((b'gAMA', struct.pack('>I', 100000)),)), 512_000_000),
                (_png(6000, 4000, 16, 6, ancillary=(_text(b'tEXt', 'XML:com.adobe.xmp', _xmp(9)),)), 512_000_000)):
            with self.assertRaises(ValueError) as caught:
                bounded.inspect_import(original, max_bytes=maximum)
            self.assertNotIsInstance(caught.exception, bounded.ImportBudgetExceeded)
        with patch.object(bounded, '_decode_png') as decode:
            with self.assertRaises(bounded.ImportBudgetExceeded):
                bounded.import_bytes(_png(6000, 4000, 16, 6), AssetStore())
            decode.assert_not_called()

    def test_original_global_pixel_and_work_caps_are_not_raised(self):
        with self.assertRaisesRegex(ValueError, '100,000,000'):
            bounded.inspect_import(_png(100_000_001, 1, 8, 2), max_bytes=2_000_000_000)
        with self.assertRaisesRegex(ValueError, '2,000,000,000'):
            bounded.inspect_import(_png(1, 1, 8, 2), max_bytes=2_000_000_001)
        for maximum in (True, 0, -1, 2_000_000_000.0):
            with self.assertRaises(ValueError):
                bounded.inspect_import(_png(1, 1, 8, 2), max_bytes=maximum)

    def test_pixels_are_not_decoded_during_inspection(self):
        with patch.object(bounded, '_decode_png') as decode:
            bounded.inspect_import(_png(2, 3, 16, 6))
            decode.assert_not_called()

    def test_all_exif_orientations_have_correct_extent(self):
        for orientation in range(1, 9):
            plan = bounded.inspect_import(_png(2, 3, 16, 6,
                ancillary=((b'eXIf', _exif(orientation)),)))
            self.assertEqual((plan.width, plan.height), (3, 2) if orientation >= 5 else (2, 3))
        with self.assertRaises(ValueError):
            bounded.inspect_import(_png(2, 3, 16, 6, ancillary=((b'eXIf', _exif(9)),)))

    def test_text_xmp_raw_exif_and_raw_tEXt_exif_do_not_decode_during_inspection(self):
        carriers = [_text(kind, key, value, compressed=compressed)
                    for key, value in (('XML:com.adobe.xmp', _xmp(6)),
                                       ('Raw profile type exif', _raw_exif(6)))
                    for kind, compressed in ((b'tEXt', False), (b'zTXt', True),
                                             (b'iTXt', False), (b'iTXt', True))]
        carriers.append(_text(b'tEXt', 'exif', b'Exif\0\0' + _exif(6)))
        with patch('PIL.PngImagePlugin.PngImageFile.load', side_effect=AssertionError('Metadata preflight decoded PNG')):
            for carrier in carriers:
                plan = bounded.inspect_import(_png(2, 3, 16, 6, ancillary=(carrier,)))
                self.assertEqual((plan.width, plan.height), (3, 2))
                # The full chunk scan also observes semantic text after IDAT.
                original = _png(2, 3, 16, 6)
                original = original[:-12] + _chunk(*carrier) + original[-12:]
                plan = bounded.inspect_import(original)
                self.assertEqual((plan.width, plan.height), (3, 2))

    def test_xmp_element_and_fallback_when_exif_has_no_orientation(self):
        empty_exif = b'II*\0' + struct.pack('<IHI', 8, 0, 0)
        element = '<tiff:Orientation>6</tiff:Orientation>'
        for value in (_xmp(6), element):
            original = _png(2, 3, 8, 2, ancillary=(
                (b'eXIf', empty_exif), _text(b'iTXt', 'XML:com.adobe.xmp', value)))
            plan = bounded.inspect_import(original)
            self.assertEqual((plan.width, plan.height), (3, 2))

    def test_early_exif_and_late_xmp_cannot_change_existing_import_canvas(self):
        empty_exif = b'II*\0' + struct.pack('<IHI', 8, 0, 0)
        early_carriers = ((b'eXIf', empty_exif),
                          _text(b'tEXt', 'exif', b'Exif\0\0' + empty_exif))
        for early in early_carriers:
            for kind, compressed in ((b'tEXt', False), (b'zTXt', True),
                                     (b'iTXt', False), (b'iTXt', True)):
                original = _png(2, 3, 16, 6, ancillary=(early,))
                late = _text(kind, 'XML:com.adobe.xmp', _xmp(6), compressed=compressed)
                original = original[:-12] + _chunk(*late) + original[-12:]
                with self.assertRaisesRegex(ValueError, 'existing importer canvas') as caught:
                    bounded.inspect_import(original)
                self.assertNotIsInstance(caught.exception, bounded.ImportBudgetExceeded)
        # Matching late orientation does not create a new unnecessary refusal.
        original = _png(2, 3, 16, 6, ancillary=((b'eXIf', _exif(6)),))
        late = _text(b'iTXt', 'XML:com.adobe.xmp', _xmp(6))
        plan = bounded.inspect_import(original[:-12] + _chunk(*late) + original[-12:])
        self.assertEqual((plan.width, plan.height), (3, 2))
        # The incompatible ordering refuses BEFORE a potentially eligible
        # final-plan budget refusal, so legacy retry cannot hide the mismatch.
        original = _png(6000, 4000, 16, 6, ancillary=((b'eXIf', empty_exif),))
        original = original[:-12] + _chunk(*late) + original[-12:]
        with self.assertRaisesRegex(ValueError, 'existing importer canvas') as caught:
            bounded.inspect_import(original, max_bytes=512_000_000)
        self.assertNotIsInstance(caught.exception, bounded.ImportBudgetExceeded)

    def test_repeated_exif_prefixes_are_normalized_before_every_pillow_read(self):
        from PIL import Image
        original_getexif = Image.Image.getexif
        prefix = b'Exif\0\0'
        repeated = prefix * 4096 + _exif(6)
        raw_profile = f'\nexif\n{len(repeated)}\n{repeated.hex()}\n'
        reads = []

        def inspect_metadata(image):
            for key, value in image.info.items():
                if key == 'exif':
                    blob = value
                elif key == 'Raw profile type exif':
                    blob = bytes.fromhex(''.join(value.split('\n')[3:]))
                else:
                    continue
                self.assertTrue(blob.startswith(prefix))
                self.assertFalse(blob.startswith(prefix + prefix))
                reads.append(key)
            return original_getexif(image)

        with patch.object(Image.Image, 'getexif', inspect_metadata):
            for key, value in (('exif', repeated), ('Raw profile type exif', raw_profile)):
                original = _png(2, 3, 16, 6, ancillary=(_text(b'tEXt', key, value),))
                plan = bounded.inspect_import(original)
                self.assertEqual((plan.width, plan.height), (3, 2))
        self.assertGreaterEqual(reads.count('exif'), 2)
        self.assertGreaterEqual(reads.count('Raw profile type exif'), 2)

    def test_duplicate_conflicting_or_unsupported_orientation_is_explicit(self):
        xmp6 = _text(b'tEXt', 'XML:com.adobe.xmp', _xmp(6))
        variants = (
            (xmp6, xmp6),
            ((b'eXIf', _exif(3)), xmp6),
            (_text(b'zTXt', 'Raw profile type exif', _raw_exif(3)), xmp6),
            ((b'eXIf', _exif(6)), _text(b'tEXt', 'exif', b'Exif\0\0' + _exif(6))),
            (_text(b'tEXt', 'XML:com.adobe.xmp', _xmp(9)),),
            (_text(b'tEXt', 'XML:com.adobe.xmp', '<tiff:Orientation>6</tiff:Orientation>' * 2),),
            (_text(b'tEXt', 'XML:com.adobe.xmp', '<rdf:Description tiff:Orientation = "6"/>'),),
        )
        for ancillary in variants:
            with self.assertRaises(ValueError):
                bounded.inspect_import(_png(2, 3, 16, 6, ancillary=ancillary))
        # Consistent distinct carriers need not reject or change orientation.
        plan = bounded.inspect_import(_png(2, 3, 16, 6, ancillary=(
            (b'eXIf', _exif(6)), _text(b'zTXt', 'Raw profile type exif', _raw_exif(6)), xmp6)))
        self.assertEqual((plan.width, plan.height), (3, 2))

    def test_orientation_text_inflation_is_strictly_bounded(self):
        for kind in (b'zTXt', b'iTXt'):
            carrier = _text(kind, 'XML:com.adobe.xmp', b'a' * (bounded.MAX_ORIENTATION_TEXT_BYTES + 1), compressed=True)
            with self.assertRaisesRegex(ValueError, '1 MiB'):
                bounded.inspect_import(_png(2, 3, 16, 6, ancillary=(carrier,)))
        compressed = zlib.compress(_xmp(6).encode())
        for data in (compressed[:-1], compressed + zlib.compress(b'extra')):
            carrier = (b'zTXt', b'XML:com.adobe.xmp\0\0' + data)
            with self.assertRaises(ValueError):
                bounded.inspect_import(_png(2, 3, 16, 6, ancillary=(carrier,)))
        with patch.object(bounded, 'MAX_ORIENTATION_METADATA_BYTES', 16):
            with self.assertRaisesRegex(ValueError, 'aggregate'):
                bounded.inspect_import(_png(2, 3, 16, 6, ancillary=(
                    _text(b'tEXt', 'XML:com.adobe.xmp', _xmp(6)),)))

    def test_apng_hdr_unknown_colour_and_invalid_crc_fail_before_decoder(self):
        originals = [
            _png(2, 3, 16, 6, ancillary=((b'acTL', struct.pack('>II', 2, 0)),)),
            _png(2, 3, 16, 6, ancillary=((b'cICP', b'\x09\x10\x00\x01'),)),
            _png(2, 3, 16, 6, ancillary=((b'gAMA', struct.pack('>I', 100000)),)),
        ]
        corrupt = bytearray(_png(2, 3, 16, 6))
        corrupt[-1] ^= 1
        originals.append(bytes(corrupt))
        for original in originals:
            with patch.object(bounded, '_decode_png') as decode:
                with self.assertRaises(ValueError):
                    bounded.import_bytes(original, AssetStore())
                decode.assert_not_called()

    def test_unused_compressed_text_is_not_forwarded_to_png_decoder(self):
        original = _png(2, 3, 8, 2, ancillary=((b'zTXt', b'title\0\0' + zlib.compress(b'notes')),))
        source, _ = bounded._prepare(original, 512_000_000, lambda: False)
        snapshot = b''.join(memoryview(original)[start:end] for start, end in source.png_parts)
        self.assertNotIn(b'zTXt', snapshot)
        self.assertIn(b'zTXt', original)

    def test_palette_and_transparency_remain_pixel_bearing(self):
        original = _png(2, 1, 1, 3, raw=b'\0\x40', ancillary=(
            (b'PLTE', b'\xff\0\0\0\xff\0'), (b'tRNS', b'\0\xff')))
        source, plan = bounded._prepare(original, 512_000_000, lambda: False)
        snapshot = b''.join(memoryview(original)[start:end] for start, end in source.png_parts)
        self.assertIn(b'PLTE', snapshot)
        self.assertIn(b'tRNS', snapshot)
        self.assertEqual(source.channels, 4)
        self.assertEqual(plan.decoded_sample_bytes, 8)

    def test_declared_alpha_cannot_be_silently_omitted_by_decoder(self):
        import numpy as np
        original = _png(2, 1, 16, 6)
        source, _ = bounded._prepare(original, 512_000_000, lambda: False)
        try:
            import imagecodecs
        except ImportError as exc:
            self.skipTest(f'Pinned PNG codec prerequisite unavailable: {exc}')
        with patch.object(imagecodecs, 'png_decode', return_value=np.zeros((1, 2, 3), dtype=np.uint16)):
            with self.assertRaisesRegex(ValueError, 'alpha layout'):
                bounded._decode_png(original, source, lambda: False)

    def test_wrong_png16_dtype_cannot_be_accepted_as_precision_preserving(self):
        import numpy as np
        original = _png(2, 1, 16, 6)
        source, _ = bounded._prepare(original, 512_000_000, lambda: False)
        try:
            import imagecodecs
        except ImportError as exc:
            self.skipTest(f'Pinned PNG codec prerequisite unavailable: {exc}')
        with patch.object(imagecodecs, 'png_decode', return_value=np.zeros((1, 2, 4), dtype=np.uint8)):
            with self.assertRaisesRegex(ValueError, 'precision'):
                bounded._decode_png(original, source, lambda: False)

    def test_native_unavailable_never_falls_back_or_publishes(self):
        from lumaretouch_engine.creative_layer_native import CreativeLayerNativeUnavailable
        import numpy as np
        store = AssetStore()
        with patch.object(bounded, '_decode_png', return_value=np.zeros((1, 2, 4), dtype=np.uint16)), patch(
                'lumaretouch_engine.creative_layer_native.native',
                side_effect=CreativeLayerNativeUnavailable('packaged native component unavailable')):
            with self.assertRaises(CreativeLayerNativeUnavailable):
                bounded.import_bytes(_png(2, 1, 16, 6), store)
        self.assertEqual(store._records, {})

    def test_jpeg_incomplete_icc_is_not_silently_relabelled_srgb(self):
        # Small marker container, not a claimed decodable photograph. The ICC
        # sequence defect must reject before Pillow attempts pixel decoding.
        frame = bytes((8, 0, 1, 0, 1, 3, 1, 0x11, 0, 2, 0x11, 0, 3, 0x11, 0))
        scan = bytes((3, 1, 0, 2, 0, 3, 0, 0, 63, 0))
        icc = b'ICC_PROFILE\0\x01\x02partial'
        segment = lambda marker, data: bytes((255, marker)) + struct.pack('>H', len(data) + 2) + data
        original = (b'\xff\xd8' + segment(0xe2, icc) + segment(0xc0, frame)
                    + segment(0xda, scan) + b'\xff\xd9')
        with self.assertRaisesRegex(ValueError, 'ICC sequence is incomplete'):
            bounded.inspect_import(original)

    def test_tiff_raw_and_mutable_source_do_not_fall_back(self):
        store = AssetStore()
        for original in (b'II*\0' + b'\0' * 20, b'RAW', bytearray(b'JPEG')):
            with self.assertRaises(ValueError):
                bounded.import_bytes(original, store)
        self.assertEqual(store._records, {})

    def test_cancel_before_decode_leaves_store_untouched(self):
        store = AssetStore()
        with patch.object(bounded, '_decode_png') as decode:
            with self.assertRaises(InterruptedError):
                bounded.import_bytes(_png(1, 1, 8, 2), store, cancelled=lambda: True)
            decode.assert_not_called()
        self.assertEqual(store._records, {})

    def test_source_does_not_replace_native_transfer_with_numpy_math(self):
        tree = ast.parse(Path(bounded.__file__).read_text())
        names = {node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertIn('lrt_creative_linearize_rgba', names)
        self.assertFalse(names & {'power', 'where', 'pow', 'linearize_rgba'})

    def test_fallback_eligible_exception_exists_only_in_final_predecode_plan(self):
        tree = ast.parse(Path(bounded.__file__).read_text())
        raising_functions = []
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            for node in ast.walk(function):
                if (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                        and isinstance(node.exc.func, ast.Name)
                        and node.exc.func.id == 'ImportBudgetExceeded'):
                    raising_functions.append(function.name)
        self.assertEqual(raising_functions, ['_plan'])


class BoundedImportNativeParity(unittest.TestCase):
    """Real source-code acceptance tests, never a fabricated native fallback."""
    @classmethod
    def setUpClass(cls):
        from lumaretouch_engine.creative_layer_native import native, CreativeLayerNativeUnavailable
        try:
            import imagecodecs
            cls.native_library = native()
        except (ImportError, CreativeLayerNativeUnavailable) as exc:
            raise unittest.SkipTest(f'Real native/PNG codec prerequisite unavailable: {exc}')

    def _compare(self, original):
        from lumaretouch_engine.creative_document_import import import_bytes as legacy_import
        legacy_store, bounded_store = AssetStore(), AssetStore()
        expected = legacy_store.get(legacy_import(original, legacy_store))
        actual = bounded_store.get(bounded.import_bytes(original, bounded_store))
        self.assertEqual(actual, expected)
        self.assertIs(actual['original'], original)
        self.assertIs(type(actual['content']), bytes)
        return actual

    def test_rgb_rgba_png16_low_bits_alpha_and_all_orientations(self):
        for channels, kind in ((3, 2), (4, 6)):
            values = ([1, 257, 65534], [65535, 3, 32769], [12345, 23456, 34567],
                      [0, 1, 2], [40000, 30000, 20000], [65534, 65533, 65532])
            alpha = (0, 1, 257, 32768, 65534, 65535)
            samples = [value + ([alpha[index]] if channels == 4 else [])
                       for index, value in enumerate(values)]
            raw = b''.join(b'\0' + b''.join(struct.pack('>' + 'H' * channels, *pixel)
                            for pixel in samples[row * 3:(row + 1) * 3]) for row in range(2))
            for orientation in range(1, 9):
                self._compare(_png(3, 2, 16, kind, raw, ((b'eXIf', _exif(orientation)),)))

    def test_gray_grayalpha_and_palette_png_preserve_coverage(self):
        self._compare(_png(3, 1, 16, 0, b'\0' + struct.pack('>3H', 1, 257, 65535)))
        self._compare(_png(2, 1, 16, 4, b'\0' + struct.pack('>4H', 12345, 1, 60000, 65534)))
        self._compare(_png(2, 1, 1, 3, b'\0\x40', (
            (b'PLTE', b'\xff\0\0\0\xff\0'), (b'tRNS', b'\0\xff'))))

    def test_png_text_orientation_is_bit_exact_to_legacy_pillow_semantics(self):
        raw = b''.join(b'\0' + struct.pack('>8H', row, 257, 50000, 65535,
                                         60000, row + 1, 32768, 12345) for row in range(3))
        for orientation in range(1, 9):
            for key, value in (('XML:com.adobe.xmp', _xmp(orientation)),
                               ('Raw profile type exif', _raw_exif(orientation))):
                for kind, compressed in ((b'tEXt', False), (b'zTXt', True),
                                         (b'iTXt', False), (b'iTXt', True)):
                    carrier = _text(kind, key, value, compressed=compressed)
                    self._compare(_png(2, 3, 16, 6, raw, (carrier,)))
                    original = _png(2, 3, 16, 6, raw)
                    self._compare(original[:-12] + _chunk(*carrier) + original[-12:])
            self._compare(_png(2, 3, 16, 6, raw, (
                _text(b'tEXt', 'exif', b'Exif\0\0' + _exif(orientation)),)))
        repeated = b'Exif\0\0' * 16 + _exif(6)
        for key, value in (('exif', repeated),
                           ('Raw profile type exif', f'\nexif\n{len(repeated)}\n{repeated.hex()}\n')):
            self._compare(_png(2, 3, 16, 6, raw, (_text(b'tEXt', key, value),)))

    def test_late_xmp_after_early_empty_exif_is_explicitly_incompatible(self):
        from lumaretouch_engine.creative_document_import import import_bytes as legacy_import
        empty_exif = b'II*\0' + struct.pack('<IHI', 8, 0, 0)
        raw = (b'\0' + struct.pack('>8H', 1, 2, 3, 65535, 4, 5, 6, 65535)) * 3
        original = _png(2, 3, 16, 6, raw, ((b'eXIf', empty_exif),))
        late = _text(b'iTXt', 'XML:com.adobe.xmp', _xmp(6))
        original = original[:-12] + _chunk(*late) + original[-12:]
        legacy_store, bounded_store = AssetStore(), AssetStore()
        existing = legacy_store.get(legacy_import(original, legacy_store))
        self.assertEqual((existing['width'], existing['height']), (2, 3))
        with self.assertRaisesRegex(ValueError, 'existing importer canvas'):
            bounded.import_bytes(original, bounded_store)
        self.assertEqual(bounded_store._records, {})

    def test_png_truecolour_trns_is_not_dropped(self):
        self._compare(_png(2, 1, 16, 2, b'\0' + struct.pack('>6H', 1, 2, 3, 1, 2, 4),
            ((b'tRNS', struct.pack('>3H', 1, 2, 3)),)))

    def test_png8_and_png16_use_existing_icc_transform(self):
        from PIL import ImageCms
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        metadata = ((b'iCCP', b'source\0\0' + zlib.compress(profile)),)
        self._compare(_png(2, 1, 8, 6, b'\0\x01\x20\xfe\x01\xff\x02\x03\x80', metadata))
        self._compare(_png(2, 1, 16, 6,
            b'\0' + struct.pack('>8H', 1, 257, 65534, 257, 65535, 32768, 12345, 65534), metadata))

    def test_jpeg_l_rgb_cmyk_and_progressive_are_exact_to_same_decoder(self):
        import numpy as np
        from PIL import Image, ImageCms
        for mode, channels in (('L', 1), ('RGB', 3), ('CMYK', 4)):
            shape = (3, 5) if mode == 'L' else (3, 5, channels)
            pixels = np.arange(15 * channels, dtype=np.uint8).reshape(shape)
            for progressive in (False, True):
                with Image.fromarray(pixels, mode=mode) as image, BytesIO() as stream:
                    exif = Image.Exif()
                    exif[274] = 6
                    kwargs = {'exif': exif, 'progressive': progressive}
                    if mode == 'RGB':
                        kwargs['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
                    image.save(stream, format='JPEG', **kwargs)
                    original = stream.getvalue()
                self._compare(original)

    def test_block_bound_and_cancel_never_publish_partial_asset(self):
        library = self.native_library
        state = {'calls': 0, 'cancel': False}

        class ObserveNative:
            def lrt_creative_linearize_rgba(self, source, destination, length):
                if length // 4 > 4:
                    raise AssertionError('Unbounded native input')
                result = library.lrt_creative_linearize_rgba(source, destination, length)
                state['calls'] += 1
                state['cancel'] = True
                return result

        original = _png(5, 2, 8, 2, (b'\0' + b'\x01\x02\x03' * 5) * 2)
        store = AssetStore()
        with patch.object(bounded, 'BLOCK_PIXELS', 4), patch(
                'lumaretouch_engine.creative_layer_native.native', return_value=ObserveNative()):
            with self.assertRaises(InterruptedError):
                bounded.import_bytes(original, store, cancelled=lambda: state['cancel'])
        self.assertEqual(state['calls'], 1)
        self.assertEqual(store._records, {})


if __name__ == '__main__':
    unittest.main()
