# First curated extension: prompted foreground → existing ID background

Status: SOURCE AUTHORED, NOT RUN (2026-10-25). This slice does not establish a
working package, install, build, device compatibility, portrait quality or speed.

## Researched choice and existing owners

* Official pinned [SAM 2 README](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/README.md)
  documents image prompting, Python 3.10+, Torch 2.5.1+, torchvision 0.20.1+ and
  optional CUDA postprocessing. Its code/checkpoints are Apache-2.0; the pinned
  [license](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/LICENSE)
  and existing `docs/model-licenses/sam2.1-hiera-tiny-provenance.md` retain evidence.
* [Google Image Segmenter](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter)
  is a legitimate existing person/category backend, not a universal matting
  solution. The existing ID-background owner deliberately rejects generic
  semantic/full operands as independently reviewed subject support. This slice
  therefore uses the existing approved SAM prompted object, not a fake new
  semantic-to-ID acceptance path or arbitrary ComfyUI executable nodes.
* The app already has `prompted_model_api.rs` (owned helper/cancel lifecycle),
  `prompted_model_install.py` (versioned components), `Predictor` (offline pinned
  config/weights in memory), and local-mask→ID reviewed-support ownership.
  We reuse these; do not add another process registry, model store or inference
  API. All photos stay in existing local workers.

## Concrete first-install-to-use source path

1. Existing ID-background panel exposes a curated card and fixed metadata.
2. User chooses **Install / continue / retry**. The native owner selects the
   already-running app engine's Python, never an arbitrary system fallback.
3. A version-owner kernel lock protects install/repair. Fixed-size checkpoint
   partials survive errors/cancellation. HTTP Range must match the exact pinned
   total; an ignored Range restarts; full SHA256 failure resets untrusted bytes.
   A complete verified partial needs no network. Model and same-version partial
   are shared with existing prompted features; no duplicate extension model.
4. Existing isolated target components are prepared in staging; app/global Torch
   and chosen GPU variant are untouched. Fixed source revision/config/checkpoint
   are retained. Optional dependencies are version-pinned, **not a complete
   wheel-hash-locked environment**; this existing supply-chain gap is not hidden.
5. The staged candidate gets an explicit, bounded CPU programmatic-fixture check
   in a killable child using the same `Predictor`, actual verified bytes, strict
   state_dict and real prediction contract. No user photo is supplied. The
   source code for this check was written but **not executed during development**.
6. Only a passing candidate replaces an invalid older installation; old bytes
   are retained in a named backup. Failed candidate setup leaves them untouched.
   Repair uses two renames with exception rollback, not crash-atomic exchange;
   abrupt process loss between renames may leave the canonical location missing,
   with the prior bytes still in the retained backup. Restore/rollback UI remains
   outstanding. Existing valid installations get rechecked rather than overwritten. An old
   readiness receipt is invalidated before a recheck; failure cannot reuse it.
7. Offline status hashes actual checkpoint and component inventory, and matches
   the readiness receipt to the current Python/base package metadata identity (versions, locations and
   distribution RECORD hashes). Base-package payloads are not all rehashed: a
   same-version file edit with unchanged metadata may require explicit recheck. `installed`
   alone is never ready. Readiness is explicitly `cpu-probe-passed`, not GPU,
   image quality, latency, final export or regulatory acceptance.
8. **Use** rechecks status and current document context, then enters the existing
   single prompted dialog. Actual candidate prediction, visible-presentation
   acknowledgement and accepted local-mask object retain their original owners.
   ID background still requires separate explicit support review, edge inspection
   and background application. No automatic review, full-image fallback or photo
   edit occurs just because installation succeeded.

## Limits exposed, not silently completed

Supported scope is a Linux app engine with existing compatible base dependencies.
Automatic base Python/Torch preparation on an empty machine is **not connected**.
`engine/requirements-cpu.txt` still has broad version constraints and an explicit
unverified-bare-machine note; it is not a reviewed standalone installer lock.
Missing/old base dependencies yield unsupported/error without mutation or device
fallback. No universal ComfyUI/node/AMD/NVIDIA compatibility is claimed.

The setup uses a conservative 1 GiB free disk floor (checkpoint cache + candidate
+ optional components; prior retained versions consume additional disk), visible
Linux cgroup-v2/host memory accounting with 4 GiB currently available for the CPU
probe, 8 GiB virtual-address ceiling, 180 CPU seconds and 240 seconds wall time.
These are **admission budgets, not measured minimum hardware requirements**.
Runtime-component download size is not locked as a complete cross-platform sum.
Legacy mkdir install locks are refused, not blindly stolen from an old installer.
Uninstall/rollback UX, complete empty-machine setup and community catalog expansion
remain open; no photos/projects or shared runtime are deleted by this card.

## Authored but UNRUN evidence

* `engine/tests/test_curated_extension_setup_unrun.py`: resumed range, ignored
  range, malformed range, hash rejection, offline completed partial, symlink
  refusal, installed-but-unchecked, failed recheck invalidation.
* `ui/src/promptedMasks/curatedExtension.unrun.test.ts`: readiness/progress gates.
* Still needs separately authorized first install, interrupted/resumed download,
  offline reuse, cancellation, candidate repair/rollback, failure reporting,
  real-device smoke, end-to-end UI and real portrait/edge/export/latency acceptance.

Static Python AST parsing and whitespace diff review are the only checks performed
for this source slice. No tests/typechecks/build/download/install/inference ran.
