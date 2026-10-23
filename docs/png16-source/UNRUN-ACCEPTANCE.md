# Original PNG16 acceptance plan: NOT RUN

Source inspection only. No local imports, codec calls, inference, tests,
compiler, build, typecheck or product execution were performed in this slice.

1. Decode independent RGB16 patterns containing adjacent levels (255/256/257,
   32767/32768/32769 and 65533/65534/65535), with misleading filename suffixes.
   Compare all native samples; use neutral output with no profile conversion for
   preservation checks. Do not require arbitrary photographs to use every level.
2. Exercise grayscale, grayscale-alpha, RGB/RGBA, tRNS exact16 matches/nonmatches,
   all-opaque alpha and alpha65534. No transparency decision may use RGB8.
3. All eight EXIF orientations, nonsquare dimensions, interlaced input and ICC
   metadata. Verify source geometry once, profile conversion once, and normalized
   output orientation. Original source SHA must remain unchanged.
4. RGB ICC test profiles: compare RGB16 working conversion to LittleCMS16 and
   compare proxy pixels only after that conversion. Invalid/gray ICC, unsupported
   cICP/PQ/HLG/primaries/range, animation and malformed metadata must fail without
   fallback or mislabeled sRGB. No wider HDR claim follows from a uint16 dtype.
5. Import into the ordinary image workspace. Inspect source-bit reporting,
   RGB8-proxy disclosure, 100% edited inspection, spill source locator and actual
   full before/after candidate, plus creative capture from current edits.
6. Edit exposure, curves, crop/rotation and representative source-bound effects.
   Verify preview, full inspection and export share source dimensions/ICC and
   preserve independent masks/analysis. Inspect boundaries at full resolution.
7. Neutral master16, edited16 and watermarked16 TIFF/PNG output: verify native
   readback samples, ICC and source identity. Output source profile is distinct
   from working sRGB. Verify the selected PNG16 container actually retains
   uint16 samples and that RGB8 PNG remains a separate delivery choice.
8. Ordinary RGB8 delivery: verify native16 decode, float editing/geometry before
   final quantization, output ICC/source profile, watermark/layout, target-size
   search and final dimensions. Regression-check other formats and derived-base
   routing; no path may consume a preview or double-apply geometry.
9. Project reopen/autosave/recovery, virtual copies, frozen batch recipes and
   cancellation must retain immutable source ownership. No decoder profile
   metadata is an inferred camera-RAW identity. Test source replacement races.
10. Ordinary24MP workloads, memory admission under real cgroups, peak allocations,
    cancellation boundaries and invalid oversized/complex PNGs. Conservative
    byte estimates are not measured performance or OOM guarantees.

Re-import eligible old unsupported sample rows and verify native PNG16/ICC16
selection, unchanged originals/identities and immutable preset references.
Unsupported transparency, colour signalling and stale/corrupt ownership stay guarded.
Per-target visual spill batch review, wider alpha/HDR, model/photo quality and
other handbook gaps are not acceptance targets declared complete here.
