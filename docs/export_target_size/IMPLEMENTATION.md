# coreM10 · Approximate target-byte JPEG export

Status: shared product route authored on integration base b64782014c3923a99d9a264f5e0e214ba1b24d71. App controls, preview/start transport, engine validation, frozen queue options, final writer and result UI are connected in source; runtime validation remains UNRUN. Python AST/JSON/source/hash inspection only. No import, image encoding, tests, product execution, compiler, typecheck, build or inference has run. Authored acceptance cases are UNRUN. This is not product completion or image-quality acceptance.

## Baseline and exact mapping

- Guide: https://www.pixcakeai.com/guide/32483, read 2026-10-23, section 品质. It presents size and quality as alternatives and describes target size as approximate, not a guaranteed exact limit. Its 0–14 quality scale is not our encoder scale.
- Manual baseline `baseline_probe/manual-text.txt` lines 303–307 and 1146 require approximation, truthful infeasibility and no equivalence to the competitor's quality scale.
- Mapping: PC-32483 / WF-32483-30b6eae726 / LNX-REF-WF-32483-30b6eae726, 导出设置与资源竞争. Related queue mapping WF-32483-2bfb26ee30 is not claimed fully implemented here. No fabricated narrower baseline control ID.
- Mature implementation reference: existing `export.py::write_file`, `_profile_bytes`, `_convert_srgb_to_profile`, `_filter_exif`, `_icc_facts`, `QUALITY_MAPPING_VERSION`. Existing Pillow dependency is reused; no new codec or dependency.
- Primary encoder reference: https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg . JPEG quality, explicit subsampling, ICC and EXIF save parameters. The documented warning against quality above 95 is retained as a trade-off: the product already exposes 100, and this implementation does not silently clamp the chosen range. No promise of monotonic byte size.

## Implemented semantics

`target_bytes` and absolute `tolerance_bytes` are integers. B/kB/MB/KiB/MiB conversion is explicit in UI; wire values are B. The acceptance interval is inclusive target ± tolerance, so tolerance may permit output above target. This is approximate size, not a hard upload ceiling.

Search iterates every integer quality from explicit maximum down to minimum, retaining the closest candidate, choosing higher quality on equal distance. It stops at the first in-tolerance candidate, which is the highest measured quality that matches. No assumption that lower quality always produces smaller JPEG bytes is used. If samples hit the buffer cap, optimality is not claimed. Exhaustive out-of-tolerance search is `unreachable`; interrupted search is `budget_exhausted` or `encoded_budget_exhausted`, not proof of infeasibility.

Without explicit `allow_best_effort`, an unmet target writes nothing and raises a structured receipt. With opt-in, it publishes the closest measured candidate and reports `within_tolerance=false`. Never reports an approximate failure as matched. The UI makes possible target overshoot clear.

The worker must finish its normal edit/crop/upscale/watermark pipeline first. Writer detaches final RGB8 pixels once, color-converts once, freezes metadata once, and changes only JPEG quality between attempts. Existing 4:4:4 chroma sampling stays unchanged. The selected output is decoded once for container, dimensions, RGB mode, ICC and EXIF integrity; this is not lossless-pixel equality or visual acceptance. RGB16, alpha, PNG, TIFF and WebP do not silently convert. They are unsupported by this target-size algorithm.

Cancellation and elapsed-time budgets are cooperative between Pillow calls. One native encode cannot be preempted. Limits bound attempts, individual output buffers and admitted pixel count, not total process RSS or hard wall-clock runtime. No performance number is asserted. Rendering remains controlled by the existing worker. Existing partial-watermark-delivery behavior is preserved.

## Integration map (now wired in shared source; runtime UNRUN)

1. `ui/src/App.tsx`: add TargetSizeDraft state and TargetSizeControls next to existing quality slider; disable slider when target enabled. Validate targetSizePolicy against effective format/bit depth before calling engineStatus/runExport. Do not force JPEG or clear user's invalid target. Spread targetSizeArguments into runExport instead of unconditional quality. Disable controls during existing exporting state.
2. `ui/src/native.ts::runExport`: add optional `targetSize?: TargetSizePolicy`, send `targetSize` camelCase. Extend ExportedImage and per-variant receipts with `target_size?: TargetSizeReceipt`. Include error receipts too; do not only report the requested size or old quality field.
3. `ui/src-tauri/src/main.rs`: declare `mod export_target_size_port`; add `target_size: Option<Value>` to `export`; call attach_target_size after quality forwarding. No separate command or synthetic success.
4. `engine/.../server.py::EXPORT_KEYS`: add `target_size`. In cmd_export after format and bit depth are resolved and BEFORE queue/dirs/render, call request_policy(p, format=fmt, bit_depth=bit_depth), reject simultaneous explicit quality. Save returned dict in opts['target_size'] and task inputs. Existing immutable _task_args tuple/retry path must retain it; no reading live controls during worker/retry.
5. `server.py::_export_loop`: replace final write_delivery8 with export_target_size_adapter.write_delivery, add target_size=opts.get('target_size'), cancelled=ctl.cancel.is_set using this batch's captured control object. Do not rerun export_image or crop inside the search. Existing metadata/options remain unchanged. Preserve existing RGB16 branch and reject target mode before that branch. Existing marked/clean variants go through the adapter.
6. `server.py` success image result: forward info['target_size'] and each outputs variant receipt. Error image result: forward getattr(error,'target_size',None); DeliveryError carries the cause's target receipt. Keep errors failed, collisions skipped, and matched/unmet distinct. Existing task cancel bookkeeping still owns terminal states; do not turn cancellation into success.
7. `ui/src/components/ExportQueuePanel.tsx`: mount TargetSizeResult for main and variant receipts. Do not style best-effort-unmet as plain success; show warning even when a file was written. Main matched status alone cannot summarize both watermark variants.
8. `server.py` progress (optional, deliberately not wired): optional search callback emits a distinct `export_target_size_progress` event with path/task identity, not the existing completed-item export_progress shape. Add host event handling/types only if displaying per-attempt progress; otherwise leave callback absent, retaining responsive cancellation.

Destination integration now reuses `export_destination_commit.commit_encoded_bytes` through a small collision-policy adapter. The publisher pins every ancestor with dirfd/O_NOFOLLOW and uses no-clobber hard-link commit. When a destination plan supplies an exact frozen target, pass `frozen_target=True` to the writer: no recheck rename is then allowed, including retries. Legacy recheck may select a new name only outside frozen plans. Post-commit fsync failures are reported as committed with durability warning, not as absent output. Never reuse old resolve_target + os.replace for this new route: a concurrent file could be overwritten between those calls.

## Validation ownership

Qoder should execute `engine/tests/export_target_size_search_cases.py` and `engine/tests/export_target_size_writer_cases.py` explicitly (filenames intentionally non-auto-discovered here), plus acceptance.json scenarios, native transport tests, real edited JPEG/ICC/EXIF comparisons, cancellation/collision injection and full desktop UI/queue flows after shared wiring. Static parse is not a substitute. Required end-to-end output evidence: actual bytes, quality, dimensions, metadata, frozen snapshot identity, original hash unchanged, and correct task receipts for every output variant.

## Shared integration review

- App.destinationOptions and actual runExport use the same validated target policy. The destination signature includes the full draft. Server normalized target_size is in opts, destination settings hash, task inputs and immutable retry args. Unused batch quality is null in target mode rather than pretending the old slider value was used.
- The final adapter runs under the existing EDR.run per-document context. It checks EDR.resolve before encoding and before publication; explicit skip produces no encoding. create_missing is taken only from the frozen destination policy. A frozen-path race fails rather than renaming. Primary and clean variants retain their own destination entries and receipts.
- All normal quality-mode calls delegate to the existing watermark writer unchanged. PNG/TIFF/WebP and RGB16 are rejected only when target mode is requested. Existing PNG/PDF layout pages are not constrained by the JPEG target; UI says so.
- The queue captures this batch's cancellation Event, not a later retry's control. Existing task state machine still handles cancellation terminal state. Per-image success/failure, per-variant result and persisted task detail retain target receipt, actual quality and directory durability warnings.
- Shared files changed: ui/src/App.tsx, ui/src/native.ts, ui/src/components/ExportQueuePanel.tsx, ui/src-tauri/src/main.rs, engine/src/lumaretouch_engine/server.py. No Git writes, encoder invocation, app launch, tests, build, typecheck, compiler or inference were performed.
