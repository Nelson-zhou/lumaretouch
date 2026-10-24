# Face-style recipe binding v1: AUTHORED / UNRUN

This is original parameter composition, not a new numerical kernel, inferred
age/gender/face-type classifier, proprietary calibration, vendor-equivalence
claim or photographic acceptance result. Existing Rust-backed operations own
geometry, evidence gates and refusal. No existing numeric core or old state was
modified. No product imports, tests, typechecks, builds, inference or downloads
were run during this authoring pass.

## Requirement evidence and its limits

The supplied product manual, extracted line 516, lists seven face presets and
strength. The supplied AI pack `功能需求验收映射.json` maps PC-32466 family
3b31aac970, amount 6c86bf2c55 and the exact seven controls below. Its research /
uncovered status is not implementation evidence. Desktop guide
https://www.pixcakeai.com/guide/32466 was unavailable for live verification in
the parent review. The parent reviewed Android guide
https://www.pixcakeai.com/guide/202665 for corroborating style intent only;
Android wording does not establish additional desktop controls or coefficients.

- classic / 经典 / 7ce4146bc1: slimmer contours and larger eyes.
- youthful / 幼态 / e4a7970fd2: feature layout.
- bold / 英气 / 7e035684d8: smaller whole face.
- youth / 少年 / 0e3343d22a: smoother, slimmer contours.
- round / 圆脸适用 / 7b800a0655: reduced cheeks and chin shape.
- long / 长脸适用 / ae54a179f8: shortened mid/lower face.
- square / 方脸适用 / 9fc7c5a61e: inward jaw.

All numbers below are conservative initial local policy, pending visual review.
“Conservative” describes bounded coefficients, not proven safety or quality.
Applying a named style is an explicit user choice, never an inferred demographic.

## Exact amount-1 coefficients and native direction contracts

Every coefficient is multiplied by finite amount in [0,1]; booleans, strings,
NaN, infinities and out-of-range values are refused, not clamped. Maximum absolute
coefficient is .30. Omitted owned controls are zero; bilateral controls use equal
left/right values and explicit linked=true.

- classic: contour temple -.12, cheekbone +.18, jaw -.20; eye size +.18.
- youthful: mid length -.08, lower length -.04; brow position -.04; eye spacing
  +.04, position -.04; nose height -.03; mouth vertical -.03.
- bold: face size +.25.
- youth: contour temple -.10, cheekbone +.14, jaw -.16; chin shape +.06.
- round: contour cheekbone +.25, jaw -.12; chin shape +.18; chin length +.06.
- long: mid length -.25, lower length -.18, chin length -.08.
- square: contour jaw -.30; chin shape +.08.

Direction was read from existing state and Rust source, not guessed from labels:

- Contour positive temple/jaw is outward, positive cheekbone inward. This matches
  `slim_face_state.contour_recipe` and face-contour geometry's signed peak checks.
- Positive face size shrinks the measured face (existing gain .06).
- Negative mid/lower/chin length shortens the respective distinct region.
- Positive chin shape narrows horizontal chin width, not chin length.
- Positive eye size enlarges; positive eye spacing moves outward; negative eye
  position moves down. Negative brow position moves down. Nose height is vertical
  translation, negative down, NOT nose length or 3D height.
- Mouth vertical has the opposite sign: negative moves up. Thus the youthful
  composition mildly compresses layout, rather than translating every feature in
  the same image direction. This is a local design choice requiring review.

## Frozen API and overwrite scope

`catalogue()` returns fresh plain metadata with version=1, binding_version=1,
family_control_id, amount_control_id, amount_min/max, coefficient_limit, origin,
owned_operation_ids, owned_parameters, and styles. Each styles row has id, label,
control_id, intent, version, binding_version, owned_operation_ids. IDs use the
PC-32466-C- prefix; requirement IDs add LNX-REF- in traceability tooling.

`patches(style, amount, binding_version=1)` returns 30 existing people patch
objects: operation_id, parameter_path, unset=false, value. The binding keyword
refuses any other version. Existing geometry recipe versions are pinned to 1.
No renderer, model loading, source identity or global selection is accessed.

The SAME union is replaced for every style, including at zero:

- lnx.face_contour.v1: /temple, /cheekbone, /jaw each /linked, /left, /right.
- lnx.face_size.v1, lnx.mid_face.v1, lnx.lower_face.v1, lnx.chin_length.v1: /amount.
- lnx.chin_shape.v1: /linked, /left, /right.
- lnx.brow_shape.v1: /position/linked, /position/left, /position/right.
- lnx.eye_shape.v1: /size, /spacing, /position each /linked, /left, /right.
- lnx.nose_shape.v1: /height.
- lnx.mouth_shape.v1: /vertical.

Each complete internally constructed recipe is checked by its actual state
validator before patches are emitted. Other leaves in these operations stay
untouched, as do every other operation and all legacy values. Switching style
replaces old style-owned intent, does not accumulate. This also overwrites MANUAL
values on the 30 listed leaves, not only values originally written by a style.
Amount zero explicitly sets these leaves neutral/linked; it does NOT unset to
inherit or restore pre-style manual values. Undo remains the existing history
owner's responsibility. UI must disclose this scope before application.

`validate_compatibility(values)` requires the full effective recipe map from
people_algorithms, validates all full recipes, invokes its compatibility check,
then checks slim-v2 vs contour/legacy slim and legacy big-eye vs eye size. It
returns a checked detached map, never clears conflicts. The host must merge the
patches against inherited/current intent and call this helper on the COMPLETE
candidate before preview. Per-leaf validation is insufficient for linked equality.
No patch writes lnx.deform.v1, lnx.slim_face.v2 or legacy small_chin.

This helper does not replace source/face revision fencing, native availability,
semantic evidence, all-or-nothing preview/application, or geometry refusal. A
compatible recipe can still be unrenderable on a particular face. Existing
consumers must remain authoritative; partial requested effects are not success.

## Unrun fixture coverage and remaining acceptance

`test_face_style_recipes_unrun.py` specifies exact IDs, 30 unique paths, range and
schema rejection, deterministic output, all style transitions, unowned manual
preservation, owned manual overwrite at zero, exact signed coefficients and
compatibility refusal without mutation. These are authored assertions, not
passing results. Native/image quality, frontend behavior, history, source fencing,
project roundtrip and multi-person operation require their separate host/UI
fixtures and subsequently authorized runtime/photo acceptance.
