/**
 * 右侧精修面板（1.11.0 产品态）：只保留四栏，文案只写中文名与数值。
 *
 * 这里没有任何注册表编号、规约说明或调试读数：面板是给影楼修图师用的，
 * 不是给开发者看的。数值一律从引擎的 doc_state 读；滑块在拖动期间用本地值
 * 先走一步（引擎回声到达时若不在拖动就对齐），松开后一切仍以引擎为准。
 */
import { useEffect, useRef, useState } from "react";
import {
  runDeform, runEnhance, runExposure, runLut, setStrength,
  type DocState, type EngineStatus,
} from "../native";

export interface RetouchProps {
  status: EngineStatus | null;
  doc: DocState | null;
  hasImage: boolean;
  faceOk: boolean;
  faceWhy: string;
  note: (s: string) => void;
  onDone: () => void;
}

const ok = (p: Promise<unknown>, props: RetouchProps) =>
  p.then(props.onDone).catch((e) => props.note(String(e)));

/** 一条干净的滑块：中文名 + 数值，双击归零。
 *
 * 拖动期间用本地值（引擎每条命令都要重画一帧，回声比手指慢半拍；
 * 若一直用回声值，滑块会在手指下轻微回弹）。松手后引擎的值才是唯一出处。
 */
function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  display?: string;
  disabled?: boolean;
  title?: string;
  onChange: (v: number) => void;
  onReset: () => void;
}) {
  const [local, setLocal] = useState(props.value);
  const dragging = useRef(false);
  useEffect(() => {
    if (!dragging.current) setLocal(props.value);
  }, [props.value]);
  const show = props.display ?? String(Math.round(local));
  return (
    <div className={"pslider" + (props.disabled ? " off" : "")} title={props.title}>
      <div className="prow">
        <span className="plabel">{props.label}</span>
        <span className="pval">{show}</span>
      </div>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step ?? 1}
        value={local}
        disabled={props.disabled}
        title="双击归零"
        onPointerDown={() => { dragging.current = true; }}
        onPointerUp={() => { dragging.current = false; }}
        onPointerCancel={() => { dragging.current = false; }}
        onChange={(e) => { const v = +e.target.value; setLocal(v); props.onChange(v); }}
        onDoubleClick={() => {
          dragging.current = false;
          setLocal(0);
          props.onReset();
        }}
      />
    </div>
  );
}

function Group(props: { title: string; open?: boolean; children: React.ReactNode }) {
  return (
    <details className="pg" open={props.open ?? true}>
      <summary>{props.title}</summary>
      <div className="pgBody">{props.children}</div>
    </details>
  );
}

const FACE_LABEL: Record<string, string> = {
  slim_face: "瘦脸",
  big_eye: "大眼",
  small_chin: "小下巴",
  smile: "微笑",
};

export default function RetouchPanel(props: RetouchProps) {
  const { doc, status } = props;
  const dim = !props.hasImage;
  const params = doc?.params ?? {};
  const amounts = doc?.deform.amounts ?? {};
  const enhance = doc?.enhance;
  const enhAmounts = enhance?.amounts ?? {};
  const ex = doc?.exposure;
  const presets = status?.presets ?? [];

  /** 高低频是一组参数：一次提交整组（引擎的 set_strength 就是整组收的）。 */
  const commitSkin = (patch: { strength?: number; detail?: number; broad?: number }) => {
    if (!doc) return;
    ok(setStrength(patch.strength ?? doc.strength, {
      channel: doc.channel ?? undefined,
      radius: params.radius,
      detailGain: patch.detail ?? params.detail_gain,
      midGain: params.mid_gain,
      broadGain: patch.broad ?? params.broad_gain,
    }), props);
  };

  // 引擎报哪几种就画哪几种；ready 还没到（首屏几百毫秒）时按这一版引擎的
  // 全集先画出来（禁用态），避免"面板里空一块"那种残破感。真能不能用仍由
  // faceOk 与引擎整条拒把关，前端不替它放行。
  const reported = (status?.ready_caps?.deform_kinds ?? []).filter((k) => k in FACE_LABEL);
  const faceKinds = reported.length ? reported : Object.keys(FACE_LABEL);

  return (
    <div className="retouch">
      <Group title="智能磨皮">
        <Slider label="磨皮强度" value={Math.round((doc?.strength ?? 0) * 100)}
                min={0} max={100} disabled={dim}
                onChange={(v) => commitSkin({ strength: v / 100 })}
                onReset={() => commitSkin({ strength: 0 })} />
        <Slider label="肤质保留" value={Math.round(((params.detail_gain ?? 0) / 2) * 100)}
                min={0} max={100} disabled={dim}
                onChange={(v) => commitSkin({ detail: (v / 100) * 2 })}
                onReset={() => commitSkin({ detail: 0 })} />
        <Slider label="肤色匀净" value={Math.round(((params.broad_gain ?? 0) / 2) * 100)}
                min={0} max={100} disabled={dim}
                onChange={(v) => commitSkin({ broad: (v / 100) * 2 })}
                onReset={() => commitSkin({ broad: 0 })} />
      </Group>

      <Group title="面部重塑">
        {faceKinds.map((kind) => (
          <Slider key={kind} label={FACE_LABEL[kind]}
                  value={Math.round((amounts[kind] ?? 0) * 100)}
                  min={0} max={100} disabled={dim || !props.faceOk}
                  title={props.faceOk ? undefined : props.faceWhy}
                  onChange={(v) => ok(runDeform("set", { [kind]: v / 100 }, "all"), props)}
                  onReset={() => ok(runDeform("set", { [kind]: 0 }, "all"), props)} />
        ))}
      </Group>

      <Group title="五官美白">
        <Slider label="眼白提亮" value={Math.round((enhAmounts.sclera ?? 0) * 100)}
                min={0} max={100} disabled={dim || !props.faceOk}
                title={props.faceOk ? undefined : props.faceWhy}
                onChange={(v) => ok(runEnhance("set", { sclera: v / 100 }), props)}
                onReset={() => ok(runEnhance("set", { sclera: 0 }), props)} />
        <Slider label="牙齿美白" value={Math.round((enhAmounts.teeth ?? 0) * 100)}
                min={0} max={100} disabled={dim || !props.faceOk}
                title={props.faceOk ? undefined : props.faceWhy}
                onChange={(v) => ok(runEnhance("set", { teeth: v / 100 }), props)}
                onReset={() => ok(runEnhance("set", { teeth: 0 }), props)} />
      </Group>

      <Group title="色彩风格">
        <Slider label="曝光" value={ex?.ev ?? 0} min={-2} max={2} step={0.05}
                display={(ex?.ev ?? 0).toFixed(2)} disabled={dim}
                onChange={(v) => ok(runExposure("set", { ev: v }), props)}
                onReset={() => ok(runExposure("set", { ev: 0 }), props)} />
        <Slider label="白平衡"
                value={Math.round((ex?.temperature_shift ?? 0) / 20)}
                min={-100} max={100}
                display={`${Math.round(ex?.temperature_shift ?? 0)} K`} disabled={dim}
                onChange={(v) => ok(runExposure("set", { temperature_shift: v * 20 }), props)}
                onReset={() => ok(runExposure("set", { temperature_shift: 0 }), props)} />
        <div className="presets">
          <button className={"chip" + (!doc?.lut.preset ? " on" : "")} disabled={dim}
                  onClick={() => ok(runLut("clear"), props)}>原片</button>
          {presets.map((p) => (
            <button key={p.name}
                    className={"chip" + (doc?.lut.preset === p.name ? " on" : "")}
                    disabled={dim}
                    onClick={() => ok(runLut("set", { preset: p.name, amount: 1 }), props)}>
              {p.title}
            </button>
          ))}
        </div>
      </Group>
    </div>
  );
}
