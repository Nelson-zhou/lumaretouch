# Selective colour: connected source, UNRUN

Status: SOURCE_CONNECTED_UNRUN. No compiler, tests, application, numerical kernel, type checker, inference, downloads or package installation executed. No photographic completion claim. Shared integration granted at 328cde0fdef0a21951b8203775bec66449586b5b; parent owns publication. Project now writes v18 and retains v17 grading/v16 tone/v15 CUBE/v14 hair.

## Reference verification and authorship

- Handbook manual-text.txt lines 607 onward and exact source mapping identify selective colour as distinct from HSL. Original mapping lists parent + nine ranges + CMYK + two modes, 16 IDs total.
- Adobe official documentation, inspected 2026-10-23: https://helpx.adobe.com/photoshop/desktop/adjust-color/selective-color-adjustments/make-selective-color-adjustments.html . Describes nine families and CMYK controls on RGB. Relative changes existing ink by a fraction; absolute changes percentage points. This establishes user-facing semantics, not vendor pixel equivalence.
- FFmpeg mature open-source implementation, inspected 2026-10-23: https://ffmpeg.org/doxygen/trunk/vf__selectivecolor_8c_source.html . RGB extrema select six chromatic regions; separate white/neutral/black masks; CMYK adjustments have distinct relative and absolute modes, including RGB16. Reference only: no implementation copied, no linked dependency. Our continuous partition and additive black rule intentionally differ.

## Original f32 algorithm lrt-rgb-ink-v1

Nine masks in R,Y,G,C,B,M,W,N,K order are derived directly from encoded sRGB RGB, not HSL. Clip only the mask anchor to [0,1]. For anchor r,g,b:

- R=max(r-max(g,b),0), Y=max(min(r,g)-b,0), G=max(g-max(r,b),0).
- C=max(min(g,b)-r,0), B=max(b-max(r,g),0), M=max(min(b,r)-g,0).
- Let lo=min(r,g,b), hi=max(r,g,b), a=1-(hi-lo), l=(hi+lo)/2.
- W=a*l*l, N=a*2*l*(1-l), K=a*(1-l)*(1-l).

The six chromatic masks sum to chroma; the other three sum to achroma. All nine partition unity. Pure primaries and secondaries each select one distinct family. Neutral gray has no chromatic response; tonal masks intentionally overlap continuously. This is not a thresholded HSL saturation operation.

For output RGB channel c, original complementary ink I=1-anchor[c]. For each range, channel adjustment A uses C/M/Y and shared black adjustment K, both normalized -1..1. Scale=I in relative mode or 1 in absolute mode. Target ink=clamp(I+(A+K)*Scale,0,1). Sum each mask times (I-target ink); add to original encoded pixel. Every range is evaluated from the original anchor, so changing iteration order cannot feed earlier changes into later selection. Positive ink darkens its complementary RGB channel, negative ink lightens. Black adds equally to three process controls. This is a documented creative RGB model, not ICC printing separation or a promise of Photoshop/PixCake identity.

## Formats and identity

ABI1 accepts 37 f32 values: nine CMYK quartets in stated order and relative flag 0/1. Strict state uses complete named ranges, exact keys, version/algorithm/space, finite -100..100 values, no bool-as-number. Method is global. No explicit null recipe is treated as omission.

Mode 1 uses extended encoded sRGB D65, signed headroom up to magnitude 128. Mode 0 uses signed linear sRGB D65 up to magnitude 65504, sign-preserving sRGB transfer into/out of adjustment. The anchor is SDR, but signed/HDR residual is retained in encoded space rather than clipped. This is not scene-referred highlight reconstruction; HDR visual acceptance remains outstanding. Channel with zero delta returns original input to avoid conversion round-trip error. Fully neutral recipe is bit-exact, including signed zero, and bypasses native loading/CPU transfer in the host stage.

RGB8/RGB16 stage adapters normalize by 255/65535 to f32, never via uint8. Only terminal integer quantization rounds/clips; float output stays float. Non-sRGB source ICC conversion remains decoder-owned. Tensor path is explicit CPU Rust processing and returns float32, not a GPU acceleration claim.

FFI limits each call to 65,536 pixels, checks finite recipe/pixels and pointer alignment/overlap before touching output. Python bounds HWC RGB at 100 million pixels, polls cancellation between chunks, and never exposes partial destination. Native build is offline std-only at package time; no runtime compiler or Python numerical fallback.

## Workflow and ownership

Preview is temporary stage replacement with finally-restoration, not persisted edit. Latest-intent ticket, document/revision, reader ingress abort and final publication gate prevent stale frames. Apply requires the latest preview plus the actual Tauri compositor-presented exact frame sequence and slot. Request-ID replay returns the existing receipt. Unknown timeout does not resend commit. Cancellation cannot claim to undo an uncertain commit.

Host delegates history to existing engine capture/record/apply APIs, one non-coalesced changed gesture. It retains/restores host ledger on failure, with reload-required state if rollback fails. No parallel history owner. Portable presets carry recipe only; batch preparation is replacement with detached recipes, while existing generic scope transaction owns history/rollback. Export uses the same stage once after grading and before monochrome.
