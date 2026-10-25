# Light glow native contract

Operation `lnx.light_glow.v1`; ABI **1**; math identity **65537 / 0x00010001**.
All lengths count native float32 elements, not bytes. All public structs are
`repr(C)` and fields are listed in declaration order in `light_glow.h`.

## Introspection and admission

- `lrt_light_glow_abi()` returns 1; `lrt_light_glow_math()` returns 65537.
- `lrt_light_glow_settings_size()`, `lrt_light_glow_geometry_size()` and
  `lrt_light_glow_plan_size()` return intended sizes 56, 32 and 72 bytes.
  Layout is an authored contract, not a platform ABI test result.
- `lrt_light_glow_plan(settings, geometry, max_work_bytes, out_plan)` validates
  everything except pixel content and writes one plan on success only.
- `lrt_light_glow_render(settings, geometry, input, input_floats, output,
  output_floats, coverage, coverage_floats, max_work_bytes, cancel, cancel_user)`
  validates the same plan and exact lengths, then reads input and privately renders.

There is no caller-supplied plan to trust or mutate. The host calls the planner,
extracts exactly its region, then the renderer independently derives that plan.
Settings and geometry must remain identical during the two calls. Changing any
scalar requires a new candidate; radius changes can change the required region.

## Settings

Metadata is `struct_bytes=56`, `abi_version=1`, `math_identity=65537`, and both
reserved fields zero. Mode 0 is `black_mist`, 1 is `white_mist`, 2 is `glow`.

- `radius_px`: unsigned integer 0–512, measured on the full source grid.
- `strength`, `threshold`, `scattering`: finite float32 0–1.
- `exposure_ev`: finite float32 −4–4, the gain parameter of a bounded SDR
  exposure response, not unrestricted scene exposure. See the equation.
- `hue_deg`: finite float32 −180–180.
- `saturation`, `lightness`: finite float32 −1–1, relative HSL adjustments.

The wire recipe's nested tint object becomes the three corresponding C fields.
The adapter must validate JSON types/ranges before narrowing to float32 and must
bind/hash the canonical wire recipe. No booleans-as-numbers or coercion. Floating
rounding is part of this float32 ABI; parent review must hash its canonical recipe
and exact result. Presets are local scalar expansions, not core mode IDs or assets.

## Geometry and plan

Geometry metadata is `struct_bytes=32`, `reserved=0`. `full_width/full_height`
identify the full immutable canonical source. `tile_x/tile_y` locate the output
tile in it. `tile_width/tile_height` give output size; no crop/orientation guessing.

Limits: 12,000 per source edge; 100,000,000 source pixels; 512 per tile edge;
65,536 tile pixels. Max working budget is 536,870,912 bytes. These are local
resource limits, not advertised vendor restrictions.

Plan metadata is `struct_bytes=72`, `channels=9` (scratch plane count, NOT RGBA
channel count), `reserved=0`. Its region is the exact full-source rectangle
required for the output tile. The extent clips the complete halo to actual image
bounds. For enabled processing, halo is `ceil(radius_px*(1+0.25*scattering))`, at
most 640 pixels. For strength zero, halo is exactly zero and region equals tile.

Let N be region pixels and T tile pixels. Input length is 4N, output length 4T,
coverage length T. The two internal nine-plane float32 vectors cost 72N bytes
when enabled and zero when neutral. Total declared working budget is:

    region input 16N + scratch (enabled ? 72N : 0) + private result 20T + 8192.

The host separately charges retained canonical source, current edits/capture,
complete staged output/coverage, destination tile buffers, encoded display,
immutable byte freeze and historical assets. This native plan is not a total
application RSS guarantee. A caller cannot claim 24MP feasibility from tile math
alone. Admission must precede all those allocations, including source capture.

## Memory, alpha and publication

Every pointer must be non-null, aligned, valid for its exact extent and stable
for the call. Settings, geometry, input, output and coverage are pairwise
nonoverlapping; even overlapping read-only metadata is rejected. Checked address
arithmetic does not prove a foreign pointer is mapped: validity remains a caller
obligation. The supplied region is contiguous row-major premultiplied RGBA.

Each pixel obeys finite `0 <= RGB <= alpha <= 1`; transparent pixels contain zero
RGB (negative zero is accepted). Alpha is copied exactly. The core does not decode
ICC, quantize RGB16, turn encoded sRGB into linear, tone-map HDR or grow alpha.
There is no implicit straight-alpha input route. Input must always come from the
same immutable full source, never from an earlier output tile.

The callback, when non-null, is synchronous; nonzero means cancel. It must not
unwind across the C boundary, reenter the renderer, free state, mutate buffers,
or perform a host commit. Source validation, seeding, every blur line and each
output row poll it. A final poll occurs before publication. Cancellation arriving
after that last poll does not undo a completed call.

Core processing and result validation happen in privately owned buffers. Every
nonzero return leaves both destination arrays unchanged. On success only final
non-fallible copies write them. This is **call-level error atomicity**, not
cross-thread atomicity: the host must not expose/read destinations concurrently
or publish a partly assembled multi-tile asset. Rust unwind becomes error 9;
foreign UB, callback unwinding and process termination are outside the contract.

## Return codes and replacement

0 success; 1 ABI/pointer/length; 2 settings; 3 geometry; 4 unsupported pixel;
5 budget; 6 cancelled; 7 allocation; 8 numerical result; 9 caught Rust panic.
Errors are not successful neutral results. Invalid input remains invalid on the
zero-strength path. No automatic lower-resolution, different-mode or fallback
algorithm is allowed.

Load all symbols and verify ABI, math and struct sizes before availability.
Missing/replaced/incompatible libraries leave saved intent intact and fail the
active effect explicitly. Replace only between process lifetimes, not while calls
or views are live. New numerical semantics need a new math identity and explicit
migration/review; do not silently reinterpret a saved version-one recipe.
