import uuid
import pytest
from lumaretouch_engine.frame_presentation import make,parse,Presentation
from lumaretouch_engine.shm import FrameShm,SLOT_HDR


def test_crop_presentation_is_not_proxy_raster_aspect_and_original_is_uncropped():
    edited=make('9007199254740993',(6000,4000),(1/6,0,5/6,1),0)
    original=make('9007199254740993',(6000,4000),kind='original')
    assert (edited.width,edited.height)==(4000,4000)
    assert (original.width,original.height)==(6000,4000)
    assert parse(edited.pack())==edited and edited.document==9007199254740993
    assert edited.geometry!=original.geometry


def test_geometry_identity_distinguishes_equal_sized_different_crops():
    a=make('1',(6000,4000),(0,0,.5,1),0)
    b=make('1',(6000,4000),(.5,0,1,1),0)
    assert (a.width,a.height)==(b.width,b.height) and a.geometry!=b.geometry
    rotated=make('1',(6000,4000),rotation=90)
    assert (rotated.width,rotated.height)==(4000,6000)


def test_unknown_extension_is_legacy_but_known_malformed_rejected():
    assert parse(bytes(36)) is None
    with pytest.raises(ValueError):parse(b'LPR1'+bytes(32))
    p=make('0',(4,3),kind='synthetic');assert parse(p.pack())==p
    with pytest.raises(ValueError):make('0',(4,3),kind='edited')
    b=bytearray(p.pack());b[-1]=1
    with pytest.raises(ValueError):parse(b)


def test_slot_commit_binds_metadata_to_its_own_pixels_even_after_new_frame():
    shm=FrameShm('lrt-present-'+uuid.uuid4().hex,4,3,create=True)
    try:
        a=make('1',(6000,4000),(1/6,0,5/6,1))
        seq,_,slot=shm.write_frame(bytes([11])*48,presentation=a)
        b=make('2',(4000,6000),kind='original')
        shm.write_frame(bytes([22])*48,presentation=b)
        with shm.frame_lock():
            old=SLOT_HDR.unpack_from(shm._buf,shm._slot_offset(slot))
            assert old[0]==seq and parse(old[-1])==a
            assert shm.read_pixels(slot)==bytes([11])*48
    finally:shm.close();shm.unlink()
