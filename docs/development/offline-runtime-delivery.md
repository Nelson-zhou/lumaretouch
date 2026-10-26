# L4 prepared offline runtime installation — source-only, UNRUN

This adds an **installation source route**, not a downloadable runtime, an approved
release, or a clean-machine acceptance result. No runtime was prepared or executed
for this change. L4 remains open. The existing .deb still excludes Python/Torch;
its description remains true. The host's existing XDG `engine/venv/bin/python`
resolution is reused; no application/server edits are needed.

## Explicit entry points (future approved use only)

- `bash packaging/setup-runtime.sh --offline-bundle /media/runtime-bundle --manifest-sha256 <independently-authenticated-SHA256SUMS-digest>`
- Installed: `bash /usr/lib/LumaRetouch/engine/setup-runtime.sh` with those same arguments.
- Optional `--prefix /absolute/new/path`; custom locations need the existing
  `LRT_ENGINE_PY` override. Default is `${XDG_DATA_HOME:-$HOME/.local/share}/LumaRetouch/engine/venv`.
- Online legacy setup now requires `--online` as its first argument. Offline never
  falls back to uv, pip, a host interpreter, package indices or model services.
- Existing `--recheck` explicitly runs product imports; it is **not** run by this
  installer, and was not run for this delivery.

## Required input / trust contract

A release engineer must supply an already-built, **relocatable standalone CPython
plus complete installed CPU dependencies** directory, not a development venv whose
interpreter/stdlib points outside it. Version/architecture/distribution/libc are
exact-target restrictions, not promises that arbitrary Linux distributions work.
The installer uses shell/coreutils/find and the pinned bundled Python in isolated
stdlib-only mode; the clean machine need not have Python, uv or pip installed.

The bundle contains:

```
SHA256SUMS
BUNDLE.json
payload/bin/python
payload/...              # complete interpreter, stdlib, installed dependencies
reviews/...              # primary evidence, reviewer decisions, licenses/notices
```

`SHA256SUMS` has one `64-lowercase-hex + two spaces + relative/path` line per
regular file, **including BUNDLE.json and all review evidence**, excluding itself.
No extra/missing/duplicate files, absolute paths, dot/traversal segments, symlinks,
hardlinks, special files, group/world writable or setuid/setgid entries, or
non-ASCII-safe pathnames are accepted. Archives are
not supported: there is no extraction path or archive traversal surface.

**The digest must be authenticated independently**, e.g. a separately authenticated
release record reviewed by the distributor. Computing a digest from an untrusted
bundle and pasting it into the command is not authentication. The tool implements
no key infrastructure and cannot decide legal permission from text. No bundled
interpreter executes until the exact inventory and every file hash match the
trusted digest. Bundle bytes are privately snapshotted before verification. The shell snapshot
cleanup repairs directory owner permissions top-down without following symlinks
or changing files, so rejected read-only input directories remain removable.

`BUNDLE.json` schema (fields required, illustrative placeholders, not approval):

- `schema`: `lrt-offline-runtime-v1`; `variant`: `cpu`.
- `target`: `machine`, `os_id`, `os_version`, `python_version`, `libc_name`,
  `libc_version` matching the prepared target exactly.
- `relocation_review`, `dependency_closure_review`: each has `status: approved`,
  nonempty `reviewer`, and `evidence` / `decision` paths under `reviews/`.
- `components`: nonempty array, each with exact `name`, `version`,
  `license_expression`, nonempty `license_files`, `files`, and `review` with the
  same reviewer/evidence/decision structure. Every `payload/` file belongs to
  exactly one component. Actual `*.dist-info/METADATA` name/version must also have
  a matching reviewed component. Native libraries and interpreter/stdlib need
  their own coverage; licenses/notices and source-offer obligations must accompany
  the review. Dependency closure includes native dependencies, embedded vendor
  libraries and any bundled models, not merely top-level Python names.

A boolean `approved=true` is insufficient: evidence and signed-off decisions must
be nonempty, pinned inventory files and the external authenticated review must
establish their authority and correctness. The checker proves declared evidence
and bytes agree, not independent legal clearance or dependency resolution.

Four pending decisions are explicitly fail-closed both in component records and
installed distribution metadata: **tokenizers 0.22.2, safetensors 0.8.0,
markdown-it-py 4.2.0, mdurl 0.1.2**. No approval is granted here, no service is
queried, and no override flag exists. Do not rename/remove metadata to evade the
gate; the authenticated closure review must describe the actual contents.

## Installation and failure contract

The target must not already exist. No runtime replacement, upgrade or deletion of
existing installs is supported. The destination parent must be owned by the
installer uid and not group/world writable; symlink destinations are rejected.
A lock directory serializes cooperating installers. Files are copied into a
private sibling directory, rehashed and renamed into place only after success.
Private staged directories are temporarily owner-writable/searchable during
construction; validated payload directory modes are restored immediately before
publication. Cleanup makes only private staged directories removable, including
read-only copies left by interrupted copy operations. Cleanup errors are reported
without masking the original error or skipping the lock-removal attempt.
Before publication, failure removes the private staging tree, not the old runtime.
A process kill can leave staging/lock directories; review them manually after
confirming no installer is active. There is no automatic stale-lock removal.
The manifest/review receipt is retained under `.offline-delivery-receipt`.

This is not a hostile same-uid filesystem race defense, a power-loss durability
protocol, an installer sandbox, or a product smoke test. Local trusted OS tools,
trusted source installer, authenticated release inputs and protected destination
storage are preconditions. Signed-off relocation remains a release prerequisite;
this installer deliberately does not infer relocation by importing torch.

## What is still needed / Qoder acceptance handoff

1. Resolve L5 full runtime/native/model review and the four pending approvals;
   create exact prepared bytes and independently authenticated inventory only
   after approval. Do not use this source change as an acquisition authorization.
2. Produce a standalone relocation-reviewed CPU runtime for a published Linux
   target, including audited transitive dependencies. Preserve existing optics
   asset integrity and bundled-model gates; this route does not replace either.
3. Prepare the application .deb **and all system .deb dependency closure** for
   that clean target (WebKit/GTK/LibRaw/ExifTool/lcms/seccomp and transitive OS libs).
   This runtime installer does not fetch/install system packages. A prepared
   runtime alone therefore cannot establish clean-machine LINUX-001 closure.
4. In a future authorized isolated Qoder environment: deny all network, start
   without Python/uv/pip/product runtimes, install the approved OS/application
   packages and runtime, then import/edit/sync/export/reopen with licensed samples.
   Observe installer + desktop + engine egress, supported target behavior,
   relocation, CPU limits and identity of actual installed artifacts.
5. Exercise corrupt/extra/missing files, denied licenses, wrong target, symlink /
   hardlink / traversal names, existing destination, interrupted copy, repeated
   install and stale-lock recovery. No such tests were run for this change.

Only source inspection was performed here: no build, test, typecheck, installer,
product import, model inference, package acquisition or model acquisition.
