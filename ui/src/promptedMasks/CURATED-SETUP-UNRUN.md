# Curated ID-background setup — authored, not executed

Source path: `App` embeds `CuratedIdBackgroundSetup` in the existing ID-background
panel. It uses the existing native `prompted_model` install/status/check/cancel
owner. The use action rereads status, requires installed + ready +
`cpu-probe-passed` + complete checkpoint verification, and checks that the UI
source context and tool availability did not change during the status request.

Both this card and the old local-mask AI button call the single App
`startPromptedMasks` owner and mount one `PromptedMaskDialog`. They reuse the
original local-mask capture, source presentation, real prediction, candidate
presentation and accepted edit receipt. No extension code invents a retained
mask or marks ID-background support reviewed. The next action is the existing
ID-background independent support review / color / apply / save / export flow.

## Pending execution (UNRUN)

- Initial no-model status, explicit install, interruption and resumed bytes;
  complete checkpoint verification; setup error and retry.
- Invalid installation keeps repair/install available even if stale `installed`
  metadata is true; installed but unchecked keeps CPU check available.
- Installed but unchecked, failed CPU probe, modified checkpoint/runtime or
  stale receipt must not enable Use. Only full receipt matches may enable it.
- No Torch/torchvision: display unsupported and the unmet base-engine setup
  prerequisite, not “one click complete”.
- Switch document / source revision or enter another tool while Use's status
  request is pending: no selection dialog is opened for the old context.
- Old and curated entry points cannot create two concurrent selection dialogs.
- Create real prompted candidate, visually inspect it, explicitly accept it;
  wait for current-document confirmed local-mask receipt; then independently
  review ID-background support and apply a background. Cancel, failed or
  uncertain receipts must not present selection success.
- CPU fixture readiness is not GPU acceptance, face/hair edge quality, speed,
  memory use, identification-photo compliance, or export verification.

No build, typecheck, tests, download, installation, probe, inference, or product
runtime was executed in this authoring task. `curatedExtension.unrun.test.ts`
contains pending pure-contract fixtures, not recorded passing tests.
