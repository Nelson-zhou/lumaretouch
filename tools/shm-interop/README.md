# Native shared-frame interop test harness

Compiles the actual application `shm.rs`, not a second reader implementation.
This checks the native module and cross-language locking; it does not replace a
complete Tauri application build or real-window testing.

Run from repository root:

```
cargo build --manifest-path tools/shm-interop/Cargo.toml --locked
PYTHONPATH=engine/src LRT_SHM_READER_BIN="$PWD/tools/shm-interop/target/debug/lrt-shm-harness" python -m pytest engine/tests/test_shm.py engine/tests/test_shm_cross_process.py
```

Protocol v2 requires both the engine writer and native reader to respect the same
file's advisory locks. Old v1 peers fail version validation instead of silently
mixing an unlocked writer/reader. Locks cover only frame selection and copying,
not WebView upload, rendering, or IPC acknowledgement. Notifications may become
stale; a skipped frame is not permission to relabel newer pixels as its sequence.

Reference: https://man7.org/linux/man-pages/man2/flock.2.html

## Immutable instance extension (LRI1)

The existing locking-v2 global header's 32 reserved bytes now optionally contain:
`LRI1` (4 bytes), a random nonzero 16-byte mapping identity, and 12 zero bytes.
Every create clears all slot commit metadata and generates a fresh identity, even
when name, dimensions and sequence are reused. Pixel bytes need not be zeroed, but
no old frame is readable under the new identity before its first actual write. Readers remember the identity at open and compare it under the same
shared lock before pixel access; writers also reject replacement under their
exclusive lock. Same-size recreation is not silently treated as the old mapping.

All-zero/unknown reserved headers remain compatible display-only v2 mappings;
future identity-dependent captures require the explicit LRI1 capability. Slot
layout and normal 40-byte preview IPC are unchanged. `shm_ready` advertises the
extension and canonical 32-hex identity. This identifies a buffer, NOT yet the
photograph, recipe, actual displayed frame or sampled pixel. Those remain separate
capture contracts; do not claim this change alone completes the eyedropper.

The actual native harness includes the same identity parser as the application.
`check-replacement` waits for its caller to recreate the mapping, then proves the
old native reader rejects it before copying. CI builds this harness so interop
cases no longer silently skip for lack of a reader executable.

The subsequent LPR1 slot extension binds presentation dimensions/document/geometry
to the frame under the same flock. The normal preview IPC is now LRF1 (128-byte
versioned header), documented in docs/protocols/preview-frame-v1.md. LRI1 mapping
identity and locking-v2 layout sizes are unchanged.
