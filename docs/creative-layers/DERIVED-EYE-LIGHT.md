# M14 returned-source eye-light port

Later continuation: `DERIVED-MAKEUP.md` ports the remaining six reviewed makeup
consumers. The residual list below records this earlier eye-light-only snapshot.

Source-only continuation of `7087e87ebdfee8eb67cefa63e2cce7cef3385f85`.
Runtime, native, numerical and visual acceptance: **UNRUN**.
This narrows the residual for handbook `LNX-REF-WF-127932-a9c143a25d`
(return for further editing) and `LNX-REF-WF-127932-c7783ea5fb` (history).
It does not complete M14, M13 generation, or the 32 AI functions.

## Reachable path and ownership

- Existing EyeLightPanel reference/review/patch requests use the same captured
  document, graph, association and exact FaceRef envelope. Admission now includes
  only `lnx.eye_light.v1`, `eye_light_reference` and `eye_light_review` in addition
  to the eight previously adapted local operation IDs.
- `body_pose_commands.source_preview` now obtains `analysis_rgb(engine)`, rather
  than presenting physical-original `_src_rgb` under a derived source ID. The
  original source path retains its previous pixels; derived sources use their
  canonical immutable base's analysis/display proxy. Before/after source fences,
  full-frame mapping, bounded PNG and dimension checks remain. This shared helper
  correction does not admit other body or makeup commands.
- Live review requests still require actual composite-bound MediaPipe analysis.
  They are not exempted as analysis-repair commands. Existing eye_light_host also
  requires the currently selected, enabled, verified FaceRef and previously shown
  source reference before staging review.
- Both original material IDs (`original-softbox-v1`, `original-window-v1`),
  independent/linked eyes, strength, horizontal/vertical position, rotation and
  flip use their existing validators. Scalar admission no longer rejects the
  first member of a valid atomic linked-eye pair. The existing people_edit owner
  still validates the complete resolved linked recipe before publication.
- The only newly admitted support descriptor is `eye_light_visibility`, owned
  by the exact derived FaceRef. Existing eye_light_support resolves content hash,
  source hash/extent, face analysis revision and landmark digest. Preview and
  runtime check retained descriptors even when neutral or disabled. No copied
  source mask, guessed visibility or original-file support is accepted.
- Preview forwards the existing canonical support bank. Export already captures
  and forwards that bank with target-owned analyses. No second storage/history
  owner or new output codec is introduced.
- The concrete eye_light_people consumer is now invoked in derived preparation.
  It receives actual working-sRGB pixels, uses existing native transfer to linear
  RGB, rerasterizes reviewed normalized vectors at output dimensions and invokes
  existing Rust eye-light rendering. It returns working-space deltas to the same
  all-face pipeline. Full-resolution derived export remains float32, not RGB8.
  Missing native solver, invalid support or any requested-face refusal prevents
  a successful partial preparation. The hair return fence remains in place.

## Exact integration map

| Boundary | Changed file |
| --- | --- |
| Effective reference pixels | engine/src/lumaretouch_engine/body_pose_commands.py |
| Exact operation/review/descriptor admission | engine/src/lumaretouch_engine/creative_derived_effects.py |
| Owned review bank and neutral descriptor checks | engine/src/lumaretouch_engine/people_owned_inputs.py |
| Concrete derived consumer and runtime review checks | engine/src/lumaretouch_engine/people_render_runtime.py |
| Current-source review wording | ui/src/eyeLight/EyeLightSupportEditor.tsx |
| Existing forwarding fixture update | engine/tests/fixtures/creative_layers/test_derived_effects_contract.py |
| New ownership/atomicity/consumer fixtures | engine/tests/fixtures/creative_layers/test_derived_eye_light_contract.py |

Existing eye_light_state/support/host/people/runtime/native, Rust renderer,
people_edit, export capture, project support persistence and unified history are
reused, not replaced. No third-party source was copied. Primary architecture
references remain recorded in DERIVED-SOURCE.md and IMPLEMENTATION.md.

## Checks and remaining work

Authored fixtures cover distinct original/derived reference pixels; both material
IDs and scalar domains; linked atomic staging and unequal-pair rejection; stale
analysis; review hash/source/extent/face/landmark mismatches; neutral support
validation; target-owned runtime forwarding and explicit native failure; and
unquantized export forwarding. They use synthetic contract evidence and mocked
consumer boundaries, not actual inference or rendered photographs. They are
UNRUN. Static Python AST, whitespace and per-file hashes do not prove behavior.

Local QA must still exercise the real UI, model and Rust library, both eyes and
materials, missing active-eye review, multiple faces/all-or-nothing publication,
preview/full-source output, undo/redo, save/reopen and recovery/package replay.
The existing review geometry can refuse closed, occluded or too-small eyes.
One-pixel/thin-canvas preview constraints remain explicit. Transparent and HDR
photo return remain refused rather than flattened or clipped.

Remaining derived consumers include lipstick, blush, eyeliner, eyelash, brow and
iris makeup, hair/body, semantic/local masks and repair/recovery. Iris reference
has its own original-pixel crop path and is not fixed by this shared preview port.
Shared person/group inheritance and transfer remain fenced. Future transfer work
must resolve dormant original graph slices, require target-owned measured analysis
even for neutral transfers, and provide explicit identity review across private
return-new document owners; it must not copy source landmarks/masks or merge
private graphs silently.
