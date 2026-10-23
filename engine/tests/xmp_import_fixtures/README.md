# XMP source fixtures

AUTHORED / UNRUN. These files were not imported or executed. No test pass, native
build, numerical result, photographic quality or package compatibility is claimed.
Static Python AST parsing only checks source syntax.

- test_document_unrun.py: hostile XML/RDF, namespaces, duplicate properties,
  DTD/entities/PI refusal, UTF8/UTF16, file races, symlinks and all parser budgets.
- test_adaptation_unrun.py: exact observed process syntax, finite EV, complete
  point-curve groups, no silent clamping/filling, original-byte/report/module
  revalidation, explicit import and target-image acknowledgment, corrupt catalog
  isolation.
- ../test_xmp_target_review_unrun.py: original/derived full-target render seams,
  immutable source/upstream/people proof, bounded display PNGs and installed-state
  verification. Synthetic seams do not establish real-image parity or quality.

Runtime checks must use a security-patched Expat >=2.7.2 plus the normal complete
engine dependencies and packaged Rust curve compiler. Browser/native fixtures
are separately authored under ui/src/xmpImport and ui/src-tauri/src.
