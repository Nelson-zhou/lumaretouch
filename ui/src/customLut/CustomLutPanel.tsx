import { useEffect, useRef, useState } from "react";
export type LutAsset = { id: string; name: string; bytes: number };
export type LutSnapshot = { document_id: string; revision: number; asset_id: string | null; amount: number };
// The transport must return correlated durable receipts, not enqueue acknowledgments.
export interface CustomLutPort {
  choose(): Promise<string | null>;
  list(): Promise<LutAsset[]>;
  import(path: string, document: string, revision: number): Promise<LutAsset>;
  recover(path: string, document: string, revision: number, id: string): Promise<LutAsset>;
  select(document: string, revision: number, id: string | null, amount: number): Promise<LutSnapshot>;
  rename(id: string, name: string): Promise<void>;
  remove(id: string): Promise<void>;
  restore(id: string): Promise<void>;
  cancel(document: string): void;
}
export function CustomLutPanel({ port, snapshot, onSnapshot }: {
  port: CustomLutPort; snapshot: LutSnapshot; onSnapshot: (s: LutSnapshot) => void;
}) {
  const [items, setItems] = useState<LutAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [removed, setRemoved] = useState<string | null>(null);
  const [name, setName] = useState("");
  const intent = useRef(0);
  const listIntent = useRef(0);
  const latest = useRef(snapshot); latest.current = snapshot;
  useEffect(() => {
    let active = true;
    const request = ++listIntent.current;
    port.list().then(x => { if (active && request === listIntent.current) setItems(x); }).catch(e => { if (active && request === listIntent.current) setError(String(e)); });
    return () => { active = false; ++intent.current; port.cancel(snapshot.document_id); };
  }, [port, snapshot.document_id]);
  useEffect(() => { setBusy(false); }, [snapshot.document_id]);
  async function action(work: (current: () => boolean) => Promise<void>) {
    const id = ++intent.current;
    const doc = snapshot.document_id;
    setBusy(true); setError("");
    const current = () => intent.current === id && latest.current.document_id === doc;
    try { await work(current); }
    catch (e) { if (current()) setError(String(e)); }
    finally { if (current()) setBusy(false); }
  }
  async function refresh(current: () => boolean) {
    const request = ++listIntent.current;
    const rows = await port.list(); if (current() && request === listIntent.current) setItems(rows);
  }
  async function select(id: string | null, amount: number, current: () => boolean) {
    const before = latest.current;
    const result = await port.select(before.document_id, before.revision, id, amount);
    if (current() && result.document_id === latest.current.document_id && result.revision >= latest.current.revision) onSnapshot(result);
  }
  return <section aria-label="自定义 CUBE 滤镜库" data-requirement="LNX-REF-PC-32455-C-f8f5161c78">
    <p>本地 CUBE：1D 2–65536，3D 2–65。低网格尺寸可能产生可见插值误差。仅用于 sRGB 编码素材；不会自动识别 Log/相机空间。域外输入夹到边界，输出浮点值不截断。</p>
    <button disabled={busy} onClick={() => void action(async current => {
      const path = await port.choose(); if (!path || !current()) return;
      await port.import(path, snapshot.document_id, snapshot.revision); if (current()) await refresh(current);
    })}>导入 CUBE</button>
    <button disabled={busy || !snapshot.asset_id} onClick={() => void action(async current => {
      const path = await port.choose(); if (!path || !current()) return;
      await port.recover(path, snapshot.document_id, snapshot.revision, snapshot.asset_id!); if (current()) await refresh(current);
    })}>重新定位同一 LUT</button>
    <button disabled={busy || !snapshot.asset_id} onClick={() => void action(c => select(null, 1, c))}>移除当前滤镜</button>
    <label>自定义滤镜<select disabled={busy} value={snapshot.asset_id ?? ""} onChange={e => {
      const id = e.target.value || null; void action(c => select(id, snapshot.amount, c));
    }}><option value="">无</option>{snapshot.asset_id && !items.some(x => x.id === snapshot.asset_id) && <option value={snapshot.asset_id}>当前引用（库中已隐藏或资源缺失）</option>}{items.map(x => <option key={x.id} value={x.id}>{x.name} · {x.id.slice(0, 8)}</option>)}</select></label>
    <label>强度 {Math.round(snapshot.amount * 100)}%<input type="range" min={0} max={100} step={1} value={Math.round(snapshot.amount * 100)} disabled={busy || !snapshot.asset_id} onChange={e => {
      const amount = Number(e.target.value) / 100; void action(c => select(snapshot.asset_id, amount, c));
    }} /></label>
    <label>库内名称<input maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
    <button disabled={busy || !snapshot.asset_id || !name.trim()} onClick={() => void action(async current => {
      await port.rename(snapshot.asset_id!, name); if (current()) await refresh(current);
    })}>重命名</button>
    <button disabled={busy || !snapshot.asset_id} onClick={() => void action(async current => {
      const id = snapshot.asset_id!; await port.remove(id); if (current()) { setRemoved(id); await refresh(current); }
    })}>从库中隐藏（保留工程引用）</button>
    {removed && <button disabled={busy} onClick={() => void action(async current => {
      await port.restore(removed); if (current()) { setRemoved(null); await refresh(current); }
    })}>撤销隐藏</button>}
    {busy && <button onClick={() => { ++intent.current; port.cancel(snapshot.document_id); setBusy(false); }}>取消</button>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
