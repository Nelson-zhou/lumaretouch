"""Reviewed optional SAM 2.1 Tiny identity. No import-time I/O or downloads."""
MODEL_ID = "sam2.1-hiera-tiny"
SOURCE_REVISION = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
CODE_REVISION = SOURCE_REVISION
CHECKPOINT_REVISION = "36f406a75c9be63c7f429da63246273f028c6fd4"
CHECKPOINT_FILENAME = "sam2.1_hiera_tiny.pt"
CHECKPOINT_SIZE_BYTES = 156008466
CHECKPOINT_SHA256 = "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"
CHECKPOINT_URL = ("https://huggingface.co/facebook/sam2.1-hiera-tiny/resolve/"
                  + CHECKPOINT_REVISION + "/" + CHECKPOINT_FILENAME)
CONFIG_PATH = "configs/sam2.1/sam2.1_hiera_t.yaml"
CONFIG_RELATIVE_PATH = "sam2/" + CONFIG_PATH
CONFIG_SHA256 = "f932eac1c6241e910031b2f000a81cd9f8a8d4896e2277ab5ffb721f378b188d"
CONFIG_SIZE_BYTES = 3855
SOURCE_REQUIREMENT = "https://github.com/facebookresearch/sam2/archive/" + SOURCE_REVISION + ".tar.gz"
# Official PyPI metadata reviewed; build tools stay in the optional target.
BUILD_REQUIREMENTS = ("setuptools==84.2.1", "wheel==0.48.0", "packaging==26.3")
# Explicit --no-deps installation never resolves/replaces Torch, torchvision,
# numpy, Pillow, or the selected CPU/CUDA/ROCm variant.
OPTIONAL_REQUIREMENTS = (
    "hydra-core==1.3.2", "omegaconf==2.3.0", "antlr4-python3-runtime==4.9.3",
    "iopath==0.1.10", "portalocker==2.10.1", "tqdm==4.67.1", "PyYAML==6.0.2",
    "typing_extensions==4.12.2",
)
