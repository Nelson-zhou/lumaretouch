/** Labels and selectable scopes use only capabilities reported by the engine. */
const globalModules = [
  ['lnx.exposure.v1', '曝光'], ['lnx.white_balance.v1', '白平衡'],
  ['lnx.levels.v1', '色阶'], ['lnx.curves.v1', '曲线'],
  ['lnx.hsl.v1', 'HSL'], ['lnx.crop.v1', '裁剪'],
] as const;

export function batchScopeOptions(modules: readonly {operation_id: string; transferable: boolean}[]) {
  const supported = new Set(modules.filter(m => m.transferable === true).map(m => m.operation_id));
  const global = globalModules.filter(([op]) => supported.has(op));
  const skin = ['lnx.skin.v1', 'lnx.blemish.v1'].filter(op => supported.has(op));
  const out: {label: string; ops: string[]}[] = [];
  if (global.length) {
    out.push({label: `全图配方（${global.map(([, label]) => label).join('·')}）`, ops: global.map(([op]) => op)});
    if (skin.length) out.push({label: '全图配方 + 磨皮（逐张须单脸）', ops: [...global.map(([op]) => op), ...skin]});
    for (const [op, label] of global) out.push({label: `仅${label}`, ops: [op]});
  }
  if (skin.length) out.push({label: '仅磨皮（逐张须单脸）', ops: skin});
  return out;
}

export function resolveBatchScope(options: {label: string; ops: string[]}[], requested: string) {
  return options.find(option => option.label === requested)
    ?? (!requested ? options[0] : undefined)
    ?? {label: options.length ? '原模块不可用，请重新选择' : '当前无可同步模块', ops: []};
}
