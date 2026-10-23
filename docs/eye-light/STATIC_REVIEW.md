# Static review, 2026-10-23

- Parsed authored and shared changed Python source/fixture files with Python standard-library AST,
  without importing any product module.
- Parsed acceptance JSON with standard-library JSON parser.
- Inspected actual people graph, retained evidence, LocalEffect, support-store,
  stage merger, source-preview receipt and mask-vector schemas read-only.
- Corrected evidence model field to detector_model_sha256 after reading the
  actual retained-evidence schema.
- Removed initial independent history/session proposal. Canonical graph and
  existing transaction/history owner remain sole durable owners.
- Preserved all catchlight control code unchanged.
- Rechecked eye coordinates against source-normalized pixel-center receipt;
  geometry uses [width-1,height-1], Rust integer pixel centers and UI uses same
  inverse source viewport mapping.
- Artifacts include dedicated Rust and Python numerical/contract fixtures,
  TypeScript recipe fixtures and a dedicated native build shell script, all
  authored but UNRUN.
- After explicit integration grant, edited canonical shared graph/transport/UI/
  recovery/preset/export/package seams; no body operation order changes.
- No compiler, typechecker, test runner, product execution/import, inference,
  download, installation, Git mutation or push occurred in this slice.

This is source consistency inspection only. AST parsing does not establish
imports resolve, native ABI compiles, fixtures pass, or host integration works.
The reviewer UI uses a verified full-frame thumbnail for coordinate picking;
zoom/resolution usability and actual photo-detail review remain local QA needs.
A source receipt proves mapping, not that all eye detail is discernible.

Integration added per-eye persisted recipe schema 2, atomic linked validation,
source-only project/history reference checks and UNRUN integration fixtures.
Local relative Python/TypeScript import paths were inspected as text; no missing
paths were found. This is NOT a dependency import or typecheck.
