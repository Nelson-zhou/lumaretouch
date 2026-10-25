// SPDX-License-Identifier: GPL-3.0-or-later
import type {SyntheticEvent} from 'react';

/** UI affordance only. Native/engine exact owners remain authoritative. */
export interface CreativeWorkGuards {
  hairUnification: boolean; selection: boolean; glow: boolean; lens: boolean; expression: boolean; background: boolean;
  heal: boolean; layers: boolean; idBackground: boolean; body: boolean;
}
export function guardCreativeWork(event: SyntheticEvent, guards: CreativeWorkGuards): void {
  if (!(event.target instanceof Element)) return;
  const rules: [boolean, string][] = [
    [guards.hairUnification, '[data-hair-unification-workflow],.retouchToolActivity'],
    [guards.selection, '.creative-selection'],
    [guards.glow, '[data-light-glow-workflow]'],
    [guards.lens, '[data-lens-blur-workflow]'],
    [guards.expression, '[data-expression-workflow]'],
    [guards.background, '.commonBackgroundPanel,.commonBackgroundWorkspace,.fringePanel,.fringeWorkspace,.fringeReceipt,.fringeBackdrop,.retouchToolActivity'],
    [guards.heal, '[data-heal-workflow],.retouchToolActivity'],
    [guards.layers, '.creative-layers,.creative-connection'],
    [guards.idBackground, '.idBackgroundPanel,.id-background-picker,.backgroundMaterialHost'],
    [guards.body, '[data-arm-workflow],[data-waist-workflow],[data-leg-length-workflow],[data-neck-workflow],[data-torso-length-workflow],[data-waist-length-workflow],[data-head-size-workflow],[data-body-slim-workflow],.retouchToolActivity'],
  ];
  for (const [blocked, allowed] of rules) {
    if (blocked && !event.target.closest(allowed)) {
      event.preventDefault(); event.stopPropagation(); return;
    }
  }
}
