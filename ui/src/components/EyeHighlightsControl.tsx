import { useState, type ComponentType } from "react";

type SliderProps = {
  label: string; value: number; min: number; max: number;
  disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void;
};

/** PC-32470 亮眼/眼睛高光: existing glints only; sides are the subject's sides. */
export function EyeHighlightsControl({ amounts, disabled, reason, commit, Slider }: {
  amounts: Record<string, number>;
  disabled: boolean;
  reason?: string;
  commit: (patch: Record<string, number>) => void;
  Slider: ComponentType<SliderProps>;
}) {
  const [unlocked, setUnlocked] = useState(false);
  const left = amounts.catchlight_left ?? 0;
  const right = amounts.catchlight_right ?? 0;
  // Reopened projects and undo must never hide unequal saved sides behind a linked value.
  const separate = unlocked || left !== right;
  const slider = (label: string, value: number, keys: string[]) => (
    <Slider key={label} label={label} value={Math.round(value * 100)} min={0} max={100}
      disabled={disabled} title={reason || "只增强照片已有高光，不生成或移动眼神光"}
      onChange={(v) => commit(Object.fromEntries(keys.map((key) => [key, v / 100])))}
      onReset={() => commit(Object.fromEntries(keys.map((key) => [key, 0])))} />
  );
  return <div className="eyeHighlights">
    <button type="button" className="specBtn" disabled={disabled}
      aria-pressed={separate}
      title={separate ? "恢复联动时将人物右眼同步为人物左眼的数值" : "分别调整人物的左眼和右眼"}
      onClick={() => {
        if (separate) {
          if (left !== right) commit({ catchlight_right: left });
          setUnlocked(false);
        } else setUnlocked(true);
      }}>{separate ? "左右独立 · 点击联动" : "双眼联动 · 点击解锁"}</button>
    {separate ? <>
      {slider("眼睛高光 · 人物左眼", left, ["catchlight_left"])}
      {slider("眼睛高光 · 人物右眼", right, ["catchlight_right"])}
    </> : slider("眼睛高光", left, ["catchlight_left", "catchlight_right"])}
  </div>;
}
