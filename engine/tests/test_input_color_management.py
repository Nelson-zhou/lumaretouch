"""Input profiles must transform pixels into the common sRGB working space."""
import io
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageCms
from lumaretouch_engine.decode import load_rgb, load_full
from lumaretouch_engine.export import write_file

PROFILE = Path('/usr/share/color/icc/compatibleWithAdobeRGB1998.icc')

@pytest.fixture
def sample(tmp_path):
    if not PROFILE.exists():
        pytest.skip('Adobe-compatible reference profile unavailable')
    profile = PROFILE.read_bytes()
    im = Image.new('RGB', (32, 32), (180, 90, 60))
    p = tmp_path / 'input.png'
    im.save(p, icc_profile=profile)
    expected = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
        ImageCms.createProfile('sRGB'), outputMode='RGB', renderingIntent=1, flags=8192)
    return p, profile, np.asarray(expected)

@pytest.mark.parametrize('loader', [load_rgb, load_full])
def test_embedded_rgb_profile_is_applied(loader, sample):
    p, profile, expected = sample
    result = loader(str(p))
    assert np.array_equal(result.rgb, expected)
    assert result.source_icc == profile


def test_source_output_transforms_working_pixels_back(sample, tmp_path):
    p, profile, expected = sample
    result = load_full(str(p))
    out = tmp_path / 'output.png'
    write_file(result.rgb, str(out), output_profile='source', source_icc=profile)
    with Image.open(out) as im:
        back = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
            ImageCms.createProfile('sRGB'), outputMode='RGB', renderingIntent=1, flags=8192)
        assert np.max(np.abs(np.asarray(back).astype(int) - expected.astype(int))) <= 2

@pytest.mark.parametrize('loader', [load_rgb, load_full])
def test_invalid_embedded_profile_is_not_silently_ignored(loader, tmp_path):
    p = tmp_path / 'bad.png'
    Image.new('RGB', (16, 16), (120, 70, 30)).save(p, icc_profile=b'broken ICC')
    with pytest.raises(ValueError, match='ICC'):
        loader(str(p))
