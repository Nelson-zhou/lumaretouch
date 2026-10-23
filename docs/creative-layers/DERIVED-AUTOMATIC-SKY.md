# Derived-source automatic sky proposals

Baseline `e3dfe7b79c09f467f732fed52c52713678fdd5f2`. Source integration only. Authored fixtures are UNRUN; no product import, execution, compilation, typecheck, inference, model download or installation was performed.

## Requirements and evidence

This continues the exact PC-32476 requirements and M14 returned-source/history mapping in `DERIVED-SKY-REPLACEMENT.md`. In particular, `LNX-REF-PC-32476-C-1f5b94eaeb` covers sky controls, `0b58cf183b` person colour, `47bf45fbb5` water controls and `c68a287a5a` recovery. The supplied handbook says water reflection matters for detected water, not that every image has water or that a model may silently invent its horizon. The optional OneFormer proposal remains a product implementation choice, not a claim about the proprietary product's model or visual equivalence.

The live official guide `https://www.pixcakeai.com/guide/32476` remained inaccessible through the research tool on 2026-10-23. The supplied handbook and requirements mapping remain the primary product baseline. Hugging Face's primary OneFormer documentation, `https://huggingface.co/docs/transformers/model_doc/oneformer`, was read that day: image and task inputs are distinct, and semantic outputs require their semantic postprocessing. This slice retains the existing pinned semantic-only predictor, task-token derivation, class-chunked aggregation and pinned model/runtime inventory. It does not replace the model with an inverse-person heuristic.

## Immutable model input, separate from rendering

`creative_derived_sky.semantic_input` resolves the actual canonical creative asset with the existing Rust-backed `creative_document_base.export_source`. Its alpha/HDR refusal is preserved. Neither the physical original pathname nor `analysis_rgb`/display proxy is a derived model input. A bounded cache owns only immutable model bytes, keyed by validated canonical content and current adapter identity.

`sky_semantic/immutable_input.py` accepts the complete float32 working RGB grid. It validates finite SDR bounds without clipping, computes a separate canonical float hash, and quantizes a separate RGB8 model buffer with explicit round-to-nearest/ties-to-even rounding. The existing OneFormer target policy is preserved: `min(512/short_edge, 1024/long_edge)`, floor-rounded dimensions, bilinear resampling exactly once. This is not SAM's 2048-edge Lanczos transform. The packet contains the real source extent/identity, canonical pixel hash, transform contract, prepared size, prepared input hash and immutable bytes.

The worker transport has exclusive routes: an ordinary source pathname with its source proof, or `path=None` with the immutable packet. A fixed bounded regular raw file supplies packet bytes. Predictor consumption of prepared pixels does not resize them again. Worker results carry private packet evidence; the review owner checks source, actual prepared pixels, locator PNG, model, device and returned input identity before exposing a proposal. Candidate overlay alpha and pixel counts must match the decoded class fields exactly; a complete candidate-content hash prevents later relabeling. The RGB8 locator is explicitly not export pixels.

## Review, replay and history

The existing source-locator presentation, per-region proposal review and final sky-output presentation remain separate. Accepting semantic regions only returns a draft. It does not commit an edit, declare there is no person, invent a horizon or bypass native receipt/history ownership. Exact native semantic envelopes are admitted on derived sources only through the owned current-source route.

The resolver compares source identity as well as model/host/device/input/result identities. Derived cached and strict replay routes require the actual immutable input packet, never an original-path fallback. Current proposal/source evidence is rechecked through ready, shown and acceptance. Async final-effect preparation retains its source/recipe/asset/prepared-buffer fences and carries the packet through the existing sky raster/prepare path. Disabled stale semantic intent may remain suspended so the user can explicitly remove/replace it; it is not silently relabeled or applied.

Full export and 100% inspection use the canonically stamped full float source. Semantic inference observes its separately prepared input; full-domain Rust LMR2 still applies vector corrections and the existing sky stage handles real source-size fields, linked high-bit assets, actual deformation and tiled composition. No proxy-edited mask is enlarged as a substitute for full-resolution vector replay. Source-domain semantic observation is inherently reduced to the declared OneFormer input budget, and quality remains unverified.

## Installation identity and offline migration

Adapter identity includes the new preprocessing/packet implementation. Existing installed namespaces and old accepted descriptors are not rewritten to impersonate the changed adapter. The explicit native/UI migration action performs a local verified copy of compatible pinned model/runtime bytes into the current namespace. It is separate from license-gated network installation. The old directory/receipt remains intact, and prior reviewed descriptors still require regeneration and review under the new adapter identity.

Migration must validate the exact allowlisted legacy identity and complete locked inventory, preserve licenses/notices, stage within bounded disk/file budgets, reverify copied bytes and publish without overwriting an existing destination. Cancellation cannot advertise an incomplete installation as ready. Reusing verified weight/runtime bytes does not establish numerical compatibility or successful model loading. Neither migration nor inference has been run here.

The allowlisted predecessor adapter SHA is `f02bc1811ddb9787c80cb967fd1e10a334c96e4725a8a020bc9f8da273adf379`, inventory SHA `32a0d69bfd71205106bd1818892c9525830f2bfa4d8d1b2173367ed6f5a2d7b6`, namespace `bf7bdae029942fbc2cd88115ac9b419b02307035a933b3105bfa0ddac8cf19d6`. These were derived from immutable baseline source, not a mutable receipt. Other predecessor namespaces are not silently accepted. `sky_semantic_model_api.rs` maps the explicit `migrate` action to `--migrate`; `SkySemanticPanel.tsx` exposes local-copy size/identity, separate network consent and a post-publication warning when committed installation cleanup/durability needs attention. It never reports a committed directory as rolled back merely because a later cleanup failed.

Integration owners: `creative_sky_host`/`creative_document_host` admit only the exact proposal envelope; `sky_semantic/controller` and `review` own the source-bound proposal lifecycle; `job`/`worker` own bounded process transport; `predict`/`immutable_input` own the unchanged model preprocessing policy and explicit derived quantization; `resolver` owns reviewed result replay; `sky_replacement_preview`/`runtime` carry those proofs to the existing raster/compositor/export path. `manifest`/`migration`/`install` own installation identity and verified-copy publication. None introduces another edit-history owner.

## Remaining boundaries

Required local acceptance after source review: compare original-path preprocessing with its prior pinned byte contract; exercise a returned canvas whose dimensions differ from the original; display and acknowledge each proposed region; verify source/asset/repair edits invalidate stale proposals and final previews; compare full export with 100% inspection; test missing model, old descriptor, disabled repair, cancellation, altered packet, changed runtime inventory, and insufficient memory. Migration acceptance must include cancellation before publication, destination races, exact legacy receipt preservation, tampered wheel/runtime rejection, and warning reconciliation after committed publication. No such acceptance is implied by fixture authorship or static parsing.

- ID-background support masks, prompted artifacts, picker modes and its separate stage still need their coherent effective-source port.
- Legacy/common background replacement recovery and cross-image/shared transfer remain fenced until target-owned analysis and review are adapted.
- Transparent, signed and HDR returned sources remain refused by the portrait RGB path. RGB16 linked sky assets do not imply HDR compositing support.
- Runtime model loading, device behavior, deterministic replay, actual migration/cancellation, full-resolution memory/latency, visual edges, reflection quality, native/UI interaction and photographic acceptance remain unverified.
- This is neither completion of every M14 dependency nor completion of the 32 AI tools.
