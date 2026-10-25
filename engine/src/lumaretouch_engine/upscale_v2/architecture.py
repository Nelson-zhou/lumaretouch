"""Pinned RRDBNet parameter topology, independent of optional tensor packages.

Source of architecture facts: BasicSR 651835a1b9d38dbbdaf45750f56906be2364f01a.
This is a compatibility target, not evidence that any checkpoint was loaded.
"""

from dataclasses import dataclass
from math import prod

BASICSR_REVISION = "651835a1b9d38dbbdaf45750f56906be2364f01a"
REALESRGAN_REVISION = "fa4c8a03ae3dbc9ea6ed471a6ab5da94ac15c2ea"
CONTRACT_VERSION = "lrt.upscale-v2.native-candidate.v1"


@dataclass(frozen=True)
class Architecture:
    model_id: str
    scale: int
    input_unshuffle: int
    features: int = 64
    blocks: int = 23
    growth: int = 32


def architecture_for(model_id: str) -> Architecture:
    """Only the two inspected general-image candidates, not anime or x4v3."""
    if type(model_id) is not str:
        raise ValueError("model_id must be an explicit candidate identifier")
    if model_id == "RealESRGAN_x2plus":
        return Architecture(model_id, scale=2, input_unshuffle=2)
    if model_id == "RealESRGAN_x4plus":
        return Architecture(model_id, scale=4, input_unshuffle=1)
    raise ValueError(f"unsupported AI clarity model: {model_id!r}")


def expected_parameter_shapes(model_id: str) -> dict[str, tuple[int, ...]]:
    """Exact names/shapes; deliberately no key renaming or partial loading."""
    spec = architecture_for(model_id)
    shapes: dict[str, tuple[int, ...]] = {}

    def conv(name: str, inputs: int, outputs: int) -> None:
        shapes[f"{name}.weight"] = (outputs, inputs, 3, 3)
        shapes[f"{name}.bias"] = (outputs,)

    conv("conv_first", 3 * spec.input_unshuffle ** 2, spec.features)
    for block in range(spec.blocks):
        for dense in range(1, 4):
            for layer in range(1, 6):
                conv(
                    f"body.{block}.rdb{dense}.conv{layer}",
                    spec.features + (layer - 1) * spec.growth,
                    spec.features if layer == 5 else spec.growth,
                )
    for name in ("conv_body", "conv_up1", "conv_up2", "conv_hr"):
        conv(name, spec.features, spec.features)
    conv("conv_last", spec.features, 3)
    return shapes


def parameter_payload_bytes(model_id: str) -> int:
    """FP32 tensor payload only; neither checkpoint-file size nor peak memory."""
    return 4 * sum(prod(shape) for shape in expected_parameter_shapes(model_id).values())
