"""Reviewed Kandinsky 2.2 pack identity, not an installer or model implementation.

Missing exact upstream metadata is deliberately represented as None. It cannot be
filled by an owner pack manifest. Until reviewed pins are complete, no pack is ready.
Model cards declare Apache-2.0; no model/code bytes are redistributed here.
"""
from dataclasses import dataclass

MODEL_ID = "kandinsky-2.2-inpaint"
DIFFUSERS_VERSION = "0.29.0"
CODE_REVISION = "39aa3909e8e2dfe30f4807aedaadf42c1d8b1a8f"
PRIOR_REVISION = "9fc51ad5732afc5d031724219d22e6c42179c5a8"
DECODER_REVISION = "db790ad5cbcabed886f069ef2710774657621702"
NAMESPACE = f"{MODEL_ID}/{PRIOR_REVISION}-{DECODER_REVISION}/{CODE_REVISION}"
CODE_BLOBS = {
    "pipeline_kandinsky2_2_inpainting.py": "b5ba7a0011a14058a01f53c34ef5dfe476e28708",
    "pipeline_kandinsky2_2_prior.py": "f2134b22b40b70ab26e3225de08cead28542f34f",
}
# These are metadata requirements, never imports or installation instructions.
# None is an unresolved compatibility pin, not an arbitrary version wildcard.
RUNTIME_VERSIONS = {
    "diffusers": DIFFUSERS_VERSION,
    "transformers": None,
    "safetensors": None,
    "torch": None,
    "huggingface-hub": None,
}

@dataclass(frozen=True)
class FilePin:
    path: str
    sha256: str | None
    size: int | None
    evidence_url: str


def _pin(component: str, path: str, sha256: str | None = None) -> FilePin:
    repo = "kandinsky-2-2-prior" if component == "prior" else "kandinsky-2-2-decoder-inpaint"
    # Weight digests were visible on main blob pages. Pinned revision membership
    # and exact sizes still require independent metadata, so size stays unresolved.
    return FilePin(f"{component}/{path}", sha256, None,
                   f"https://huggingface.co/kandinsky-community/{repo}/blob/main/{path}")

FILES = (
    _pin("prior", "prior/diffusion_pytorch_model.safetensors", "ab139b2df9e40ed0b1eda8dc6270a139a796c5fa3af76cd6b0573f620dca6dde"),
    _pin("prior", "text_encoder/model.safetensors", "6eaafeea664d7ab87df17274d6114dfdf092c587c7cd56c13cf84aacdebc0332"),
    _pin("prior", "image_encoder/model.safetensors", "657723e09f46a7c3957df651601029f66b1748afb12b419816330f16ed45d64d"),
    _pin("decoder", "unet/diffusion_pytorch_model.safetensors", "098b846d2378b4b44a33e0bd47f89f2886b72a10200cbf9e96d5fae3c471543f"),
    _pin("decoder", "movq/diffusion_pytorch_model.safetensors", "43a5860fea195a7116f2471396c5cc9535fade9b63c4857d8a192ffd924b7002"),
    *(_pin("prior", path) for path in (
        "model_index.json", "prior/config.json", "image_encoder/config.json",
        "text_encoder/config.json", "image_processor/preprocessor_config.json",
        "scheduler/scheduler_config.json", "tokenizer/merges.txt",
        "tokenizer/special_tokens_map.json", "tokenizer/tokenizer_config.json", "tokenizer/vocab.json")),
    *(_pin("decoder", path) for path in (
        "model_index.json", "unet/config.json", "movq/config.json", "scheduler/scheduler_config.json")),
)
# Explicit independent review fence; filling a size alone cannot assert membership.
UPSTREAM_REVISION_MEMBERSHIP_VERIFIED = False

# Version strings alone do not authenticate installed code. A future reviewed
# admission contract must enumerate every runtime distribution artifact digest,
# its installed-file hashes and root, and verify the provenance before imports.
# CODE_BLOBS above are research evidence only, not proof of installed code.
RUNTIME_DISTRIBUTION_ARTIFACT_SHA256: dict[str, str | None] = {
    name: None for name in RUNTIME_VERSIONS
}
RUNTIME_INSTALLED_FILE_SHA256: dict[str, dict[str, str] | None] = {
    name: None for name in RUNTIME_VERSIONS
}
