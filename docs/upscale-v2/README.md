# Isolated AI超清 v2 source candidate, not an available feature

Date: 2026-10-25. Scope: new `engine/src/lumaretouch_engine/upscale_v2/` and
this documentation directory only. Legacy network, registry, dependencies,
server, UI, export, build/packaging scripts and acceptance ledgers are untouched.
No production inference path is enabled. No product imports, tests, compiler,
build, typecheck, installation, code/model download or inference were run.

This work implements an isolated, upstream-compatible architecture target and
a genuine private native-size float tiled reference computation in source.
It does not close LNX-REF-WF-158251-a4c9a2ccc1 or claim official checkpoint,
photographic, regional, performance, UI, persistence or end-to-end acceptance.
Parent integration remains separate. See the prior
[research requirements](../upscale-research/README.md) and
[full acceptance map](../upscale-research/IMPLEMENTATION-MAP.md).

## What exists

- `architecture.py`: exact two-candidate general-image RRDBNet shape/key
  contract. x2 means global 2-pixel input unshuffle, not removing an upsampling
  stage. x4 uses unshuffle=1. No scale=1, anime, compact x4v3 or face enhancer.
- `_network.py`: licensed inference-only adaptation of pinned BasicSR. Correct
  dense/outer residual 0.2, no extra RRDB convolution, upstream parameter names,
  two nearest-neighbor + convolution + LeakyReLU stages and strict state loading.
  It accepts already deserialized, externally admitted tensors, not a file.
  It is private and no current public production path calls it.
- `source.py`: immutable canonical RGBA-f32le dimensions/digest verification and
  complete bounded scans for finite, opaque, [0,1] linear RGB. No source clipping,
  flattening, ICC guessing, integer staging or proxy-source substitution.
- `geometry.py`: lazy globally phase-aligned model windows, disjoint native
  cores, filter support plus explicit neural halo, and honest payload accounting.
  It intentionally returns null peak memory and false admission/quality flags.
- `numeric.py`: float sRGB transfer/clamp primitives and explicitly anchored
  Lanczos-3 downsample taps, without invoking an integer-image convenience API.
- `_stream.py`: private source reference for actual tile model forward, generated
  clamp statistics, globally anchored float downsample, native result packing
  and cancellation/error atomicity. This is authored UNRUN. It allocates no
  full scaled output or full encoded source. Runtime resource reservation and
  independent numeric/photographic verification are missing, so no active path
  can use it. See [the working-set design](STREAMING-CONTRACT.md).
- `adapter.py`: dependency-free capability and unconditional unavailable entry.
  Paths, caller booleans, environment hashes and edited JSON cannot enable it.
  Missing evidence is not converted to sharpening, identity or a fake AI result.

## Narrow parent-facing interface

Importing `upscale_v2` performs no filesystem/network operation and imports
neither Torch nor NumPy/BasicSR. It only exposes stdlib-backed contracts:

1. `capability(model_id="RealESRGAN_x2plus")`: immutable status with
   `available=false`, `state=source_contract_only_unavailable` and exact blockers.
2. `plan_native_candidate(width, height, model_id=..., core_size=..., halo=...)`:
   planning only. Both tile parameters are explicit. No default halo is claimed
   adequate for the 23-block model. No resource admission is returned.
3. `iter_native_tiles(plan)`: lazy native/core and aligned-input rectangles.
4. `CanonicalSource` and `validate_source(..., check_cancelled=...)`: caller-owned
   immutable full current-source bytes, not permission to infer or mutate.
5. `restore_native_candidate(...)`: always raises `BackendUnavailable` before
   touching request source bytes or importing/allocating optional resources.
   Its unused request keywords are not a final production request schema.

Do not wire any private function as a bypass or advertise the presence of its
source as a live backend. Future activation requires code review plus explicit
release admission, not a UI checkbox. No `torch.load` function is provided yet:
a safe local byte loader must verify expected length/hash and file identity,
reject symlinks/unknown artifacts and use reviewed `weights_only=True` support
without fallback or allowlisting, all before this private graph constructor.

## Unresolved production gates

Official checkpoint SHA256, checkpoint-specific rights review, authenticated
runtime distribution hashes, installed code/config integrity, a safe file
loader, runtime/host reservation enforcement, device scratch bounds, actual
checkpoint compatibility and numeric/tile/photographic acceptance all remain
missing. The source candidate records that honestly and refuses production.
Reference code and upstream Git blob IDs are not authenticated weight hashes.

Region strengths are outside this backend. Face/body skin probabilities are
not complete face/body regions; `others` is not background. Neither automatic
nor manual segmentation is claimed by these modules. Whole/restored candidate
fusion, byte-exact zero strength/zero coverage behavior, current-source ownership,
semantic evidence and atomic Apply remain separate parent-owned requirements.

## License and provenance

The adapted graph carries Apache-2.0 attribution, a modification notice and the
complete locally archived upstream license alongside it. The remainder is
original project code. [PROVENANCE.json](PROVENANCE.json) pins inspected sources
and distinguishes unknown artifact/runtime evidence. Packaging has not been
changed or verified. [SOURCE-SHA256.txt](SOURCE-SHA256.txt) describes this slice,
not a repository-wide atomic snapshot or proof of execution.
