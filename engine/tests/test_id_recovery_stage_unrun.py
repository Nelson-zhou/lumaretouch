"""AUTHORED / UNRUN: ID-only attenuation and post-deformation alignment.

These fixtures have not been imported or executed. They require the local
product tensor environment; no CPU/GPU numerical acceptance is claimed.
"""
import numpy as np
import pytest
import torch
from lumaretouch_engine.effect_recovery_stage import EffectRecoveryStage


def stage(weight):
    result = EffectRecoveryStage('cpu', weight.shape)
    result.set([{'target': 'id_background', 'weight': weight}])
    return result


def test_id_recovery_endpoints_preserve_upstream_edited_input():
    before = torch.tensor([[[[.21, .43]], [[.37, .59]], [[.71, .83]]]], dtype=torch.float32)
    after = torch.zeros_like(before) + .12
    recovery = stage(np.array([[0, 255]], np.uint8))
    result = recovery.apply('id_background', before, after, align=lambda value: value)
    assert torch.equal(result[:, :, :, :1], after[:, :, :, :1])
    assert torch.equal(result[:, :, :, 1:], before[:, :, :, 1:])
    assert torch.equal(recovery.apply('background_replace', before, after), after)


def test_id_recovery_aligns_source_coverage_once_not_pixels():
    before = torch.ones((1, 3, 1, 2), dtype=torch.float32) * .8
    after = torch.ones_like(before) * .2
    recovery = stage(np.array([[0, 255]], np.uint8)); calls = []
    def align(value):
        calls.append(value.clone())
        return value.flip(-1)
    result = recovery.apply('id_background', before, after, align=align)
    assert len(calls) == 1 and calls[0].shape == (1, 1, 1, 2)
    assert torch.equal(result[:, :, :, :1], before[:, :, :, :1])
    assert torch.equal(result[:, :, :, 1:], after[:, :, :, 1:])
    with pytest.raises(ValueError): recovery.apply('id_background', before, after)


def test_id_recovery_suspension_disables_only_id_contribution():
    before = torch.ones((1, 3, 2, 2), dtype=torch.float32) * .6
    after = torch.zeros_like(before)
    recovery = stage(np.full((2, 2), 128, np.uint8))
    recovery.suspended = 'source changed'
    assert torch.equal(recovery.apply('id_background', before, after, align=lambda x: x), before)
    assert torch.equal(recovery.apply('background_replace', before, after), after)


def test_id_fractional_recovery_does_not_quantize_edited_pixels():
    before = torch.ones((1, 3, 1, 1), dtype=torch.float32) * .614321
    after = torch.ones_like(before) * .172839
    recovery = stage(np.array([[128]], np.uint8))
    result = recovery.apply('id_background', before, after, align=lambda x: x)
    expected = after + (before - after) * (128 / 255)
    assert torch.equal(result, expected)
