# PC-32455-C-171eace8b1: bounded routing handoff

Status: optics-owned enable/reset/presentation code and the three small shared
routing changes below are written, unrun and unaccepted. The routing changes
were applied only after parent released shared ownership following nose
snapshot `19e3c5658932dcc9a9b038d9da321e0b6f8e09c5`. They are included in this
bounded package. No server/main/history/native-dispatch hook is needed.

## Applied: ui/src/components/RetouchPanel.tsx

1. Remove the special two-line `renderLeaf` branch whose condition is
   `f.id === "PC-32455" && leaf.path === "透视矫正/AI透视矫正" && props.opticsPanel`.
   It currently returns a DisabledRow and the unsupported statement that an
   AI-perspective model has not been connected. The real parent control now
   lives in OpticsPanel; do not replace this branch with a second dummy control.
2. In the existing `renderExtra` route for `node.full === "透视矫正"`, keep its
   navigation/button unchanged and replace only the description with:
   `自动透视启用、智能/水平/垂直模式、手动微调与引导线使用同一个编辑器；自动分析基于真实线段与几何解算。`

## Applied: ui/src/toolRouting/coverage.ts

3. Add `"透视矫正/AI透视矫正"` to the PC-32455 exact-path set next to the three
   automatic mode paths. Update the introductory comment to remove only the
   claim that AI perspective is an explicit gap; keep the RAW gap and the
   distinction between UI de-duplication and acceptance evidence intact.

## Included native seam, not a shared dependency

The granted optics-owned `ui/src-tauri/src/optics_api.rs` now accepts the exact
one-field mutation `{"action":"reset_perspective"}` beside view/reset. Engine
and TypeScript mutation validation agree. Recipe version 1 and preview/apply
protocol 1 are unchanged. The presenter passes an explicit expected preview ID
to the existing acknowledgement path; native and engine still validate their
current bound document/session/preview identities before accepting it.

## Evidence and boundaries

The current official desktop guide identifies the AI-perspective entry as the
enable parent for smart/horizontal/vertical modes, and separately lists guides
and manual controls: https://wiki.pixcakeai.com/guide/9398.html . It does not
document a fourth learned algorithm, import default, reset scope, off/on memory
or manual composition order. Our explicit policy is documented in
`PC-32455-lens-perspective.md`; it is not an asserted PixCake implementation.

This change does not transplant a fitter, add models, alter dependencies, or
claim quality/performance acceptance. Mature line-evidence workflows are
documented by darktable:
https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/rotate-perspective/ .
The existing OpenCV implementation remains. No external solver code was copied.
If a later change imports darktable's solver, audit GPL-3.0-or-later and its
separate included LSD AGPL-3.0-or-later / simplex MIT notices rather than assuming
the entire file family has one license.
