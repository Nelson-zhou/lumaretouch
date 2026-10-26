# SAM 2.1 Hiera Tiny optional extension

Reviewed 2026-10-22. This is a fetched extension, **not a bundled model**. No
checkpoint was downloaded, no model executed, and no installation or quality
test was performed during this code-only implementation.

## Immutable upstream identities

- Code: https://github.com/facebookresearch/sam2/tree/2b90b9f5ceec907a1c18123530e92e794ad901a4
- Checkpoint metadata: https://huggingface.co/api/models/facebook/sam2.1-hiera-tiny/tree/36f406a75c9be63c7f429da63246273f028c6fd4?recursive=false
- Checkpoint filename: `sam2.1_hiera_tiny.pt`; published size 156,008,466 bytes;
  published LFS SHA-256 `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`.
- Source config: `sam2/configs/sam2.1/sam2.1_hiera_t.yaml`, 3,855 bytes;
  actual downloaded configuration SHA-256
  `f932eac1c6241e910031b2f000a81cd9f8a8d4896e2277ab5ffb721f378b188d`.

## Archived evidence and attribution

The pinned upstream README expressly licenses model checkpoints, demo code and
training code under Apache 2.0. Copyright (c) Meta Platforms, Inc. and affiliates.
The optional package retains its upstream distribution license files. Ship this
notice and the full Apache license with redistributed copies; preserve upstream
notices and identify modifications. The checkpoint and source config are not
modified. SAM demo fonts are not used or shipped by this extension.

`archive/sam2-LICENSE.txt` is the full official 11,357-byte license, SHA-256
`c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.
`archive/sam2-README.md` is the pinned source README, SHA-256
`eea69ee1042fb30933c5ca5019fbf0f6f9366cec5e792109281b5023a4f1589c`.
`archive/sam2.1-hiera-tiny-hf-tree.json` records the official published weight
metadata; it is not evidence of a local weight download/hash verification.
`archive/sam2.1_hiera_t.yaml` records the actual source config bytes reviewed.
These evidence files were downloaded directly from the pinned official URLs.

## Installation boundary

Only an explicit user extension install may launch:

    SELECTED_ENGINE_PYTHON -m lumaretouch_engine.prompted_model_install --install

The native shell, not the offline/seccomp-restricted engine, must launch this
separate process with the engine source on its Python module path. No photo path
is accepted. Keep the engine's existing offline policy intact. `--status` and
all import/inference paths are read-only/offline; they do not install anything.
Progress and result/error records are JSON lines on stdout. SIGTERM/SIGINT request
cancellation; the current blocking HTTP read has a 30-second timeout. Child pip
process groups are terminated, staging is removed, and partial files never become
an installed model. The native caller should allow graceful cancellation before
hard killing, which can leave a staging directory/lock requiring explicit cleanup.

The installer uses the selected engine Python, keeps its Torch/torchvision/numpy/
Pillow wheels unchanged, checks minimum installed versions, and installs pinned
SAM source plus its small ancillary dependencies into a separate user-data
site-packages directory. Pip uses `--no-deps`; SAM uses `--no-build-isolation`
and `SAM2_BUILD_CUDA=0`. Only the selected engine Python and pip must already
be present. Git is not needed: SAM comes from the official fixed-commit archive
URL `https://github.com/facebookresearch/sam2/archive/2b90b9f5ceec907a1c18123530e92e794ad901a4.tar.gz`.
Build tools setuptools 84.2.1, wheel 0.48.0 and packaging 26.3 are installed as
wheels in the isolated target first. Their official PyPI JSON metadata was read
on 2026-10-22 (Python requirements >=3.10, >=3.9, >=3.9 respectively; no listed
vulnerabilities). Subsequent builds receive that target via PYTHONPATH with
`--no-build-isolation`: the upstream pyproject requires setuptools>=61 and
Torch>=2.5.1, but pip must never resolve or replace the existing Torch variant.
Missing base prerequisites fail visibly. Dependencies come from official PyPI. Ancillary package versions are pinned but their index wheel hashes are
not supply-chain locked. PyYAML may use an official platform wheel. This is not a
hermetic/offline runtime distribution, nor an audited installation claim.

A staging lock prevents simultaneous installation. After successful installation,
the SAM `direct_url.json` must match the exact pinned archive URL and contain
a valid archive SHA-256 recorded by pip. The source archive was not fetched
during development; its digest is installation-observed, not a pre-reviewed
source hash. The receipt inventory covers this metadata as well as code. Configuration bytes
must match their pinned hash; every installed runtime file is recorded by hash.
The checkpoint streams into staging with an exact byte cap and SHA-256, then the
complete extension is atomically renamed into its immutable final directory.
An invalid installation is not automatically deleted: ask the user to remove it
explicitly before retry. Status only checks checkpoint length; inference must call
`verified_checkpoint_bytes()` and use the returned bytes with
`torch.load(BytesIO(bytes), weights_only=True, map_location=...)`. Likewise consume
`verified_config_bytes()` directly when instantiating, never hash then reopen a
path. `activate_runtime()` checks installed runtime identity before exposing the
isolated import path. No Torch/CUDA extension build or variant replacement occurs.

## Outstanding validation

Installation, CPU/CUDA/ROCm compatibility, cancellation, integrity-failure cases,
real portrait segmentation and UI end-to-end behavior remain unexecuted. A source
commit and matching bytes establish identity, not real-world segmentation quality.


## Source-only curated setup revision (2026-10-25)

The newer source now hashes checkpoint bytes during offline status, retains bounded
partial downloads for SHA256-verified resume, and probes an isolated candidate
before publishing it. Invalid previous installations are preserved as backup;
failed rechecks invalidate old readiness. These supersede the older status-length
and manual-removal descriptions above, not their unexecuted-validation caveat.
See `docs/development/curated-id-background-extension-setup.md`. A CPU fixture
readiness receipt is not evidence of real-portrait quality or GPU performance.
Base runtime provisioning and a fully hash-locked dependency closure remain open.
