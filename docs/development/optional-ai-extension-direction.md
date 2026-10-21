# Optional AI extensions: user-requested future direction

On 2026-10-21 the user described selecting an extension, automatically downloading
its models/configuration, and using it immediately, for example ID-photo background
replacement. This records future product direction, not implemented capability or
a replacement for the original manual's unfinished functions.

## User experience

A curated extension catalogue presents capability, download size, disk/RAM/VRAM
requirements, tested devices and licences. Selecting install prepares a versioned
isolated runtime, verified model files and a fixed tested workflow. Include resumable
transfers, integrity verification, shared model storage, update/rollback and removal.
Failure must explain missing space, unsupported hardware, download or dependency
errors without leaving an extension falsely marked ready.

For ID-photo background replacement, prefer segmentation/compositing that preserves
the original face; do not regenerate identity details by default. Red/white/blue or
custom background is a simple native panel. Generative inpainting, outpainting and
relighting can use a separate local ComfyUI backend where appropriate. Ordinary
RAW/editing/undo/colour/export remain independent of ComfyUI availability.

## Boundaries

- Rust owns native UX, job lifecycle and integration. A separate optional runtime
  provides model inference; existing Python/ComfyUI components need not be rewritten.
- Pin tested workflow/node/model versions and hashes; never silently install arbitrary
  custom-node code from an imported workflow. A custom node is executable code.
- Default local-only transport. Remote services require explicit data-destination
  choice; never silently upload portraits.
- Check code, nodes, weights and upstream assets separately. Open-source application
  licensing does not automatically grant redistribution/use rights for every model.
- Results become reversible edits/new layers with provenance; preserve the source.
- No claim of universal compatibility with all community workflows or AMD/CUDA nodes.

Official sources verified for feasibility:
https://docs.comfy.org/development/comfyui-server/comms_routes
https://docs.comfy.org/tutorials/basic/inpaint
https://docs.comfy.org/tutorials/basic/outpaint
https://docs.comfy.org/tutorials/basic/upscale
https://github.com/Comfy-Org/ComfyUI/blob/master/SECURITY.md
https://github.com/lllyasviel/IC-Light
The IC-Light README illustrates why dependencies matter: its example BRIA RMBG1.4
component has a non-commercial restriction despite the repository's Apache-2.0 code.
