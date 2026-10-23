"""AUTHORED / UNRUN. Real image/IO tests require separately authorized Qoder execution."""
from pathlib import Path
import pytest
from lumaretouch_engine.export_target_size_writer import publish_no_clobber, LimitedBuffer
from lumaretouch_engine.export_target_size_search import TargetSizeCancelled, EncodedBudgetExceeded


def test_collision_never_replaces(tmp_path):
    p = tmp_path/'photo.jpg'
    p.write_bytes(b'original')
    result = publish_no_clobber(str(p), b'new', policy='skip_and_report', cancelled=lambda: False)
    assert result['skipped'] and p.read_bytes() == b'original'
    assert not list(tmp_path.glob('.lrt-export-*'))


def test_recheck_names_and_receipts(tmp_path):
    p = tmp_path/'photo.jpg'
    p.write_bytes(b'original')
    result = publish_no_clobber(str(p), b'new', policy='recheck', cancelled=lambda: False)
    assert Path(result['path']).name == 'photo-0001.jpg'
    assert result['renamed_from'] == str(p) and p.read_bytes() == b'original'


def test_cancel_before_commit_cleans_staging(tmp_path):
    with pytest.raises(TargetSizeCancelled):
        publish_no_clobber(str(tmp_path/'a.jpg'), b'new', policy='recheck', cancelled=lambda: True)
    assert list(tmp_path.iterdir()) == []


def test_encoded_buffer_is_bounded():
    buffer = LimitedBuffer(4)
    buffer.write(b'abcd')
    with pytest.raises(EncodedBudgetExceeded):
        buffer.write(b'e')
    assert buffer.getvalue() == b'abcd'


def test_real_jpeg_final_bytes_and_metadata(tmp_path):
    import numpy as np
    from PIL import Image
    from lumaretouch_engine.export_target_size_writer import write_target_size
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = 'target-size regression'
    p = tmp_path/'real.jpg'
    result = write_target_size(np.full((32, 48, 3), 100, dtype=np.uint8), str(p),
        source_exif=exif, target_size={'target_bytes': 100000, 'tolerance_bytes': 100000,
                                    'min_quality': 95, 'max_quality': 95})
    assert result['bytes'] == p.stat().st_size == result['target_size']['actual_bytes']
    assert result['target_size']['within_tolerance'] and result['target_size']['published']
    with Image.open(p) as image:
        image.load()
        assert image.size == (48, 32) and image.format == 'JPEG'
        assert 274 not in image.getexif() and 34853 not in image.getexif()
        assert image.getexif()[270] == 'target-size regression'
        assert image.info['icc_profile']


def test_all_attempts_use_one_detached_frame(tmp_path, monkeypatch):
    import numpy as np
    from PIL import Image
    from lumaretouch_engine.export_target_size_writer import write_target_size, TargetSizeUnmet
    pixels = np.full((16, 16, 3), 80, dtype=np.uint8)
    saved = Image.Image.save
    seen = []
    def observe(image, *args, **kwargs):
        seen.append(image.tobytes())
        pixels[:] = 240  # Mutate caller's live array after detached snapshot.
        return saved(image, *args, **kwargs)
    monkeypatch.setattr(Image.Image, 'save', observe)
    with pytest.raises(TargetSizeUnmet) as error:
        write_target_size(pixels, str(tmp_path/'none.jpg'), output_profile='none',
            target_size={'target_bytes': 1, 'tolerance_bytes': 0,
                         'min_quality': 90, 'max_quality': 92, 'max_attempts': 3})
    assert len(seen) == 3 and all(frame == seen[0] for frame in seen)
    assert error.value.target_size['status'] == 'unreachable'
    assert not error.value.target_size['published'] and not (tmp_path/'none.jpg').exists()
