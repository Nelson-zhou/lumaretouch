# M14 immutable derived-source continuation

Status: source implementation and UNRUN fixtures, not functional acceptance.
Baseline: local `3a0cb19e05085e7af9b1fd7287ffe84cb58befab`.
This advances `LNX-REF-WF-127932-a9c143a25d` (return) and
`LNX-REF-WF-127932-c7783ea5fb` (history). It does not complete M14,
M13 generation, or the 32 AI functions.

## Implemented source contracts

- `creative_derived_source.py` separates original-file provenance from effective
  pixels. The returned canonical RGBA float32 asset's hash and baked dimensions,
  not the original JPEG hash, identify analysis and portrait graph entries.
- Real MediaPipe inference receives a proxy decoded from that exact composite.
  Its output records canonical identity, proxy dimensions and actual input-byte
  hash. Template/synthetic substitutes are refused. Models still consume uint8
  proxies; this does not replace or quantize the canonical float export asset.
- People selection, face/all-people targeting and reanalysis use the derived
  binding. Manual ROI detection receives the same owned composite pixels.
  Frozen export snapshots carry explicit derived-source proof and reject stale
  original analysis. Export runtime accepts validated float-domain input without
  applying the old uint8 divisor a second time.
- Returned new images start with an independent empty portrait scope, not an
  accidental same-original-fingerprint association. Source-switch history keeps
  both graphs and restores source dimensions and inference before replay. A
  source-local context digest permits unrelated global counters to change while
  protecting relevant shared relationships, effective overrides and local edits.
  Old histories without this proof retain conservative protection.
- Each persisted history frame validates against its own effective source. The
  physical original remains the relocation/recovery anchor. Existing project
  schema, external content-addressed blobs and package ownership are retained.
- Full-source 100% inspection uses the immutable returned float asset through the
  shared export resolver, not the original file or analysis/display proxy. See
  `../CREATIVE-INSPECTION-SOURCE.md` for worker, budget and wire details.

## Integration map

| Owner | Ports |
| --- | --- |
| Source identity / inference proof | creative_derived_source, face.FacePrecompute |
| Real precompute / source-switch restore | server.cmd_precompute, _history_apply; people_open |
| Portrait binding / snapshot / local ROI | people_host, people_host_commands, export_snapshot |
| History ownership / persistence | people_document_history, people_source_context, people_history_persistence |
| Float snapshot replay | people_export, people_engine_runtime, creative_document_base |
| Inspection transport / isolation | render_snapshot, inspection_bundle/controller/job/worker/wire, full_quality |
| Native and UI precision receipt | ui/src-tauri/src/inspection_wire.rs, ui/src/inspectionFrame.ts |
| Compatibility admission | creative_document_host.guard_command |

## Explicit remaining work and refusal status

1. Derived-aware effect consumers and planners: pending, deliberately refused.
   Face effects, hair/body/repair/local-mask/source-patch tools and cross-image
   people/batch/semantic planners still have original-path dependencies. Audit
   each model/evidence/asset resolver and preview/export parity before opening
   that specific guard. This slice admits analysis/cursor operations only, not
   those effect mutations or shared person/group targeting.
2. Transparent/HDR photo return: explicitly unsupported by the existing photo
   renderer. Canonical layers retain the data; return/inspection will not flatten
   transparency, clip HDR or silently borrow original pixels.
3. Inspection requires stable original provenance and stays within the existing
   512 MiB snapshot/spool budget. Large canonical assets plus analysis buffers may
   exceed it and fail explicitly. No blanket 24 MP or resource-cap claim is made.
4. Runtime validation: pending external authorized test owner. No product imports,
   tests, builds, compilers, type checks, inference or numerical acceptance were
   run. Static Python AST, JSON, hashes, source inspection and whitespace only.
   Exercise actual MediaPipe reanalysis, new/update return, undo/redo across
   sources, save/reopen/recovery/package, unchanged-original hashes, inspection
   ROI equivalence, cancellation and changed-source refusals before acceptance.

## Practice references and licensing

Original implementation; no third-party engine code copied. Primary practice
references inspected read-only: [GEGL Buffer explicit extent and format]
(https://developer.gimp.org/api/gegl/class.Buffer.html),
[GEGL boundary policy](https://www.gegl.org/abyss_policy.html), and
[Krita nondestructive layers/masks]
(https://docs.krita.org/en/user_manual/layers_and_masks.html).
These inform separation of immutable source, working pixels and nondestructive
operations; they are not evidence that this implementation has passed tests.
