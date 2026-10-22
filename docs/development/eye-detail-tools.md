# Frozen portrait eye-detail controls

Development implementation only. No tests, build, typecheck, product execution,
visual acceptance or regression campaign were performed, per development-first instruction.

## Exact baseline mapping

- control:PC-32470:7, source child index 6, 亮眼/眼睛高光:
  catchlight_left and catchlight_right, independent [0,1] zero defaults.
  The UI links both sides by default and offers left/right unlock. Restoring linkage
  explicitly copies the subject's left-eye value to the right eye. Different saved
  side values remain visibly independent after undo/reopen.
- control:PC-32470:8, source child index 7, 祛红血丝:
  veins, independent [0,1] zero default.

Frozen source: ui/src/spec/refine.json, PC-32470; row identities are from
handbook-traceability.json. Unknown baseline ranges are not represented as confirmed
upstream ranges: the normalized 0..1 engine contract is our implementation choice.

## Implementation boundaries

Pinned RapidRetouch eyes.py vein detection uses Lab redness ridge detection,
clean neighbouring sclera interpolation, and redness reduction. Existing highlight
boost detects bright local excess and retains eye-opening support. It does not
create, place, rotate or mirror synthetic eye-light assets. Those separate baseline
眼神光 rows remain unsupported, as do red-eye correction, eyelid tape and glasses
reflection. Iris hue/saturation and lash contrast are not exposed because they do
not correspond to these frozen enhancement controls. Existing sclera/iris/teeth
controls retain their meaning and algorithms.

UnderEyeLayer extends the existing selected actual-478-landmark source-derived
family. Entire source face ROIs are solved before tile cropping; repair source
versions invalidate the delta. Amounts are included in the existing dynamic enhance
state, history, project normalization, preview and full-resolution export contract.
Zero amounts bypass processing, and unchanged/outside-mask pixels are preserved.
Each control reports its measured support independently, including per-eye gates.

Algorithm source, pinned revision, original author and AGPL-3.0-only terms are
recorded in third_party/rapidretouch/UNDER_EYE_NOTICE and the adjacent LICENSE.
