# Portrait crop RULE catalogue core — v1, AUTHORED / UNRUN

`lib.rs` is a small GPL-3.0-or-later Rust source module included by the existing
native host, using its existing `serde` / `serde_json` dependencies. It is not a
new plugin, FFI library, geometric planner, render path or engine command.

It validates exactly four original local intent scalars and performs pure,
immutable catalogue CAS transitions. `tests_unrun.rs` is authored but **not run**.
No Rust parser, type check, compile or test result is claimed.

- `aspect_ratio`: width / height, finite `[0.001, 1000]`.
- `headroom_fraction`: true crown-to-top spacing / frame height, finite `[0, 1]`.
- `head_fraction`: true crown-to-chin height / frame height, finite `(0, 1]`.
- `horizontal_position`: selected face center / frame width, finite `[0, 1]`.
- Headroom plus head fraction must be `<= 1`; no implicit default or clamp.

The existing actual-photo Rust/Python/native planner remains final authority on
feasibility. Valid intent is not proof that any photo can satisfy it.

Names: 1–64 Unicode scalar values, <=192 UTF-8 bytes, no leading/trailing
whitespace, controls, non-space whitespace or listed zero-width/bidi formatting.
Names are case-sensitive, without implicit trimming/normalization. Exact duplicate
names are refused on create/rename; only explicit `update` changes a saved rule.

Catalogue metadata is only schema, random catalogue ID, monotonic safe-integer
revision, and monotonic entry IDs. The payload is name plus four scalar values.
No source/document/person/face IDs, anchors, rectangles, rotation, candidate IDs,
review flags, image data or paths are accepted or persisted. Every struct rejects
unknown fields. An unknown schema is refused, never migrated into defaults.

Storage/UI contract and acceptance handoff: `docs/portrait-crop/RULE-PRESETS.md`.
