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
