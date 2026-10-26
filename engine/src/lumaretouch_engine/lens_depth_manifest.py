# SPDX-License-Identifier: GPL-3.0-or-later
"""Bundled v1 depth admission evidence, not an installer or a ready-model claim.

Only the official Small Transformers checkpoint is in scope. Exact raw revision
config bytes were researched on 2026-10-25. A version or mutable receipt alone
does not authenticate optional runtime code; see lens_depth_setup.
"""
from dataclasses import dataclass


CONTRACT_VERSION = 1
ADAPTER_ID = "lnx.lens_depth.depth_anything_v2_small_hf.v1"
MODEL_ID = "depth-anything-v2-small-hf"
MODEL_REPOSITORY = "depth-anything/Depth-Anything-V2-Small-hf"
MODEL_REVISION = "5426e4f0f36572d16453bbda7a8389317b1bef99"
MODEL_LICENSE = "Apache-2.0"
CODE_LICENSE = "Apache-2.0"
MODEL_CARD_URL = "https://huggingface.co/" + MODEL_REPOSITORY
MODEL_REVISION_URL = MODEL_CARD_URL + "/commit/" + MODEL_REVISION
PAPER_URL = "https://arxiv.org/html/2406.09414v2"
LICENSE_SCOPE_URL = "https://github.com/DepthAnything/Depth-Anything-V2#license"


@dataclass(frozen=True)
class FilePin:
    filename: str
    size_bytes: int | None
    sha256: str | None
    revision_membership_verified: bool
    evidence_url: str


MODEL_FILES = (
    FilePin("model.safetensors", 99_173_660,
            "3152477ce0d8d6978d76b995120de97cb5b928701fd0f817769f59e249a16b70",
            True, MODEL_CARD_URL + "/blob/" + MODEL_REVISION + "/model.safetensors"),
    FilePin("config.json", 950, "c56698d3643dde1f83ea2212759e6b31a22b8f827246a36dd007ee8a22b3ff75", True,
            MODEL_CARD_URL + "/resolve/" + MODEL_REVISION + "/config.json"),
    FilePin("preprocessor_config.json", 775, "d41175c0d889477ca8fc67191e540faef14baf6275157b3fdecf78469e6bbf84", True,
            MODEL_CARD_URL + "/resolve/" + MODEL_REVISION + "/preprocessor_config.json"),
)

# Historical source-review evidence ONLY. These are NOT install requirements,
# compatibility approval, or a security-cleared runtime. The PyPI metadata also
# reports later security advisories, so do not turn this into an activation pin.
RESEARCH_TRANSFORMERS_VERSION = "4.45.2"
RESEARCH_TRANSFORMERS_WHEEL = "transformers-4.45.2-py3-none-any.whl"
RESEARCH_TRANSFORMERS_WHEEL_BYTES = 9_881_312
RESEARCH_TRANSFORMERS_WHEEL_SHA256 = (
    "c551b33660cfc815bae1f9f097ecfd1e65be623f13c6ee0dda372bd881460210"
)
RESEARCH_TRANSFORMERS_METADATA_URL = "https://pypi.org/pypi/transformers/4.45.2/json"
RESEARCH_SOURCE_BASE = (
    "https://raw.githubusercontent.com/huggingface/transformers/v4.45.2/src/transformers/"
)
ARCHITECTURE_SOURCE_URL = RESEARCH_SOURCE_BASE + "models/depth_anything/modeling_depth_anything.py"
PREPROCESSOR_SOURCE_URL = RESEARCH_SOURCE_BASE + "models/dpt/image_processing_dpt.py"

# Conditional installed optional-wheel verification and actual CPU readiness.
# The chosen base app runtime is trusted, not auto-installed or authenticated by us.
RUNTIME_ADMISSION = "pinned-optional-wheels-and-bounded-cpu-readiness"
INFERENCE_ACCEPTANCE = "UNRUN"

# Reviewed semantic constraints supplement exact model byte hashes above.
# The adapter uses the upstream classes, not an architecture reconstructed here.
ARCHITECTURE = "DepthAnythingForDepthEstimation"
BACKBONE = "dinov2"
BACKBONE_WIDTH = 384
BACKBONE_ATTENTION_HEADS = 6
BACKBONE_STAGES = (3, 6, 9, 12)
PATCH_SIZE = 14
NECK_WIDTHS = (48, 96, 192, 384)
FUSION_WIDTH = 64
PREPROCESSOR = "DPTImageProcessor"
PREPROCESS_SIZE = 518
IMAGE_MEAN = (0.485, 0.456, 0.406)
IMAGE_STD = (0.229, 0.224, 0.225)
RAW_CONVENTION = "affine-invariant-inverse-depth-larger-nearer"
OUTPUT_CONVENTION = "near-zero-far-one"


def admission_gaps_v1() -> tuple[str, ...]:
    """Return release blockers without I/O, optional imports, or discovery."""
    gaps = []
    for pin in MODEL_FILES:
        if pin.size_bytes is None or pin.sha256 is None:
            gaps.append("upstream-file-pin:" + pin.filename)
        if not pin.revision_membership_verified:
            gaps.append("revision-membership:" + pin.filename)
    gaps.extend(("installed-optional-runtime-and-cpu-readiness-must-be-checked",
                 "real-photo-and-native-integration-acceptance-UNRUN"))
    return tuple(gaps)
