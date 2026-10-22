# WB action sampling foundation

Status: verified infrastructure, not a usable eyedropper yet. No local execution.
Candidate5e5b32f108b2510554583bf0459604403a561565 passed CI39750120470, all non-GPU
jobs successful; GPU jobs skipped. Dedicated CPU Torch foundation:61 passed,
0 skipped,1.40s. Existing WB40, geometry112 and preset3 tests remained green.
Lightweight engine:1252 passed,485 skipped,72.26s. These do not prove GUI/photographic
acceptance or completion of the action picker.
Controller redemption, native presented-capture integration, input-preview lifecycle,
UI entry points and actual desktop/photographic acceptance remain outstanding.

## Real source and projection

Production retouch has an explicit wb-input early return after repair/light,
retouch mix, deformation and enhancement, before the entire exposure/WB/tone stage.
Ordinary output keeps the same operation order. A shared geometry_projection
function is the existing crop/rotate/fixed-proxy resize path, not an inverse-map
approximation. Normal-size pixels and the separately verified singleton rule remain.

Sampling is project(decode(wb-input)), then regional aggregation. It is not
 decode(project(input)) or decode(mean(input)). Preview re-encodes that same linear
projection for display. Samples are at most121 pixels, sliced on the device before
CPU transfer. Full source dimensions and document/recipe identity are still the
future action owner's responsibility; Projection freezes proxy geometry only.

Coverage is an all-ones plane through the identical projection. Source clipping
risk is formed before projection for encoded values >=1 or <0, then projected.
Finite guided-filter overshoot away from the chosen region does not block the
whole image; the existing exposure decoder clamps it, and affected selections are
rejected by their risk contribution. Nonfinite source stages fail explicitly.

## Rust policy and compatibility

The bounded white-balance-pick-v1 request uses proxy-linear-neutral-v1:
- 1–121 projected linear RGB/coverage/risk samples;16KiB input cap.
- All RGB finite and within0–1; all coverage within1e-6 of1; risk exactly0.
- Mean linear-sRGB Y at least0.005 and each mean channel at least0.0001.
- Replacement picked gains and manual×picked gains each within1/16–16.
- No silent clamp, no previous-pick accumulation, no EV in neutralization math.

These thresholds are an explicit initial product policy, not darktable thresholds,
RAW sensor clipping detection or proven optimal values for wedding photographs.
They need representative photographic acceptance. Existing saved picked gains are
not retroactively constrained by this action policy. Rust owns the policy/math;
Python validates the bounded ABI and transfers only small samples, not image JSON.

The correction preserves Y of the selected linear mean before clipping. It does
not promise every pixel or a high-contrast region's final mean will be neutral:
production per-pixel clipping does not commute with aggregation, EV may clip and
later creative grading/background composition can recolour the result. The final
interaction must explain neutral/unclipped region selection and this distinction.

## Resource admission and warm prerequisite

Projection checks source pixels, rotated bounding-box pixels and a conservative
allocation estimate before stage rendering or meshgrid allocation. The estimate is
not a measured total-renderer peak. Cold guided/light integral-image work is not
allowed inside this action: exact current filter/light/deformation cache keys must
already match the recipe, or the caller is told to wait for the normal preview.
A cached None deformation warp is valid when its key matches (identity displacement).

The CPU budget reader follows the process's actual cgroup and all visible parents,
with host MemAvailable as another limit. Only an unambiguous, full-root cgroup v2
layout is supported; v1/hybrid, hidden ancestor boundaries, overlaid mounts,
missing metadata, read failures and observed membership/mount changes fail closed.
GPU availability uses the runtime device's mem_get_info. Future capture publishing
must separately account for host-side SHM/native/UI copies; this module publishes
no frame and does not claim to have admitted that complete path.

Counters are snapshots, not allocation guarantees. Concurrent workloads, NUMA,
virtual-address limits, fragmentation and memory.high latency remain outside this
estimate. Allocation exceptions must still produce failure/restore through the
future action owner. No cache purge, CPU fallback, crop disabling or hidden proxy
change is used to manufacture success.

## Required evidence

Candidate tests cover real Rust replies, bad protocol/policy/counts, linearization
order, projected clipping/coverage, independent NumPy geometry, real nonneutral
filter overshoot, normal output order/pixel compatibility, every warm-key family,
and synthetic cgroup hierarchies including migration/failure. CI runs with CPU
Torch and rejects skips; Rust policy tests have a standalone harness. No results
beyond those exact-commit checks are claimed. Reference run:
https://github.com/Nelson-zhou/lumaretouch/actions/runs/39750120470 .

## Official/community comparison

- darktable distinguishes global output readout from local module-space pickers:
  https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/darkroom/global-color-picker/
- WB coefficients need not correspond to a Kelvin/tint pair:
  https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/white-balance/
- Explicit sampling source/averaging semantics:
  https://docs.gimp.org/3.0/en/gimp-tool-levels.html
- Square-pixel geometry and explicit resize settings:
  https://docs.pytorch.org/docs/2.14/generated/torch.nn.functional.interpolate.html
- Device availability versus live/reserved allocator memory:
  https://docs.pytorch.org/docs/2.14/notes/cuda.html#memory-management
- Hierarchical limits, subtree usage and namespace visibility:
  https://docs.kernel.org/admin-guide/cgroup-v2.html
- Mount mapping and MemAvailable estimation:
  https://man7.org/linux/man-pages/man5/proc_pid_mountinfo.5.html
  https://www.kernel.org/doc/html/latest/filesystems/proc.html#meminfo

These are implementation references, not claims that our Y-preserving/rejecting
policy duplicates darktable's green-normalized/clamped coefficients. No upstream
application source was copied in this change.
