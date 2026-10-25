# Desktop USB capture: bounded source slice

Exact original requirement: `workflow:47251`, source `工作流规格.json`,
index 27 in `docs/development/handbook-traceability.json`. The preserved source
specification is `ui/src/spec/workflows.json`, entry `47251`.
Primary official semantics: https://www.pixcakeai.com/guide/47251 .

This is partial implementation, not completed handbook acceptance. The source
path connects a replaceable real libgphoto2 adapter, dedicated owner thread,
actual file events, private completed transfers, source hash/stat evidence and
existing atomic managed import into the exact current clean saved project.
Remote shutter and live view require explicit actions and actual driver support.
No camera files are deleted, no camera settings changed, no automatic install.

Five naming intents preserve safe UTF-8 bytes; native capability admission is
not a vendor camera compatibility list. Equal-content shots remain separate
occurrences. RAW/JPEG receiving cannot alter the camera's recording format.

## Still missing / unverified

- Hardware, USB disconnect, native ABI, image quality, runtime, builds and all
  authored fixtures are UNRUN. Source presence proves none of these.
- Latest imported-photo following is unavailable while the ingestion lease pins
  editor selection; keep-current is the supported mode. Live view is not that
  feature and is not a full-source imported-image preview.
- Naming patterns currently govern immutable staged names and project display
  names, while the chosen managed folder uses existing UUID storage filenames.
  Direct user-pattern file delivery is not implemented.
- Automatic selection, sync-previous effects, reviewed preset application,
  overlay preview/export, automatic reconnect and full vendor device parity are
  not implemented by this slice.
- Engine restart loses the ingestion lease. A retained uncertain operation is
  not silently retried or considered canceled. Persisted query-only recovery
  across a new engine is still a separate missing path.
- Native drivers can allocate or block internally. Application sink limits do
  not establish universal process-memory or hard cancellation limits.
- Session and durable receipt limits remain explicit, not unlimited studio
  capture. See DEVICE.md and HOST.md for actual bounds and stage ownership.

No new image algorithm is counted for this integration. Generic import, source
precision and export algorithms remain unchanged.
