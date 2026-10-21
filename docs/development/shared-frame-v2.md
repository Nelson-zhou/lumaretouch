# Shared-frame protocol v2

The 64-byte global/slot layouts and RGBA8 pixel layout are unchanged, but global
version is now 2. Engine and native host must be updated/rebuilt together. A v1
peer is rejected; an old unlocked reader is not compatible with the guarantee.

## Commit and snapshot contract

- Exactly one engine writer owns the frame sequence. Writing pixels and then slot
  metadata is performed under an exclusive flock on the shared-memory file.
- A reader holds a shared flock across choosing a committed slot, checking metadata
  and copying every required pixel. Unlock before WebView/IPC/render acknowledgements.
- Two ping-pong slots limit storage; they do not retain every old notification.
  A stale event must be skipped or resolved to a clearly identified newer snapshot,
  never relabelled as its old sequence.
- Python offers read_snapshot(slot, expected_seq) for checked copies. Low-level
  meta_of/read_pixels must not be combined without the same frame_lock during
  concurrent access. Rust exposes reads only through the RAII FrameReadGuard.
- Recreated buffers are reopened following shm_ready. Size/layout mismatches fail
  before accessing an unsafe mapping. The normal server unlinks old mappings before
  recreation, so already-open readers retain their old inode until released.
- This is advisory locking between cooperating v2 peers, not a security boundary
  against another process with the same user's access rights. No host network or
  security configuration is changed by this protocol.

Reference: https://man7.org/linux/man-pages/man2/flock.2.html

Tests: engine/tests/test_shm_cross_process.py and the actual Rust module built via
 tools/shm-interop. Full native application build and visual testing remain separate
 gates; module interop is not a claim that GTK/WebKit or the full app built.
