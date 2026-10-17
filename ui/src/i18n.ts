import zh, { type MsgKey } from "./locales/zh";
import { en } from "./locales/en";

// 文案键的名单只从 zh 那一份导出（en 缺一项就编译不过）：组件要拿它做映射表的
// 类型，但不该因此直接依赖 locales 的内部形状。
export type { MsgKey };

export type Lang = "zh" | "en";

let current: Lang = (localStorage.getItem("lrt.lang") as Lang) || "zh";

export function setLang(l: Lang) {
  current = l;
  localStorage.setItem("lrt.lang", l);
}

export function lang(): Lang {
  return current;
}

/** 取文案：英文缺失时回落中文，并做 {var} 插值。 */
export function t(key: MsgKey, vars?: Record<string, string | number>): string {
  const raw = (current === "en" && en[key]) || zh[key] || key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_m, k: string) => String(vars[k] ?? `{${k}}`));
}
