// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState, type PointerEvent} from 'react';
import {PROTECTION_LIMITS, REGION_KEYS, checkBounds, checkBox, emptyPatch, imageDigest, key, type Box, type Draft,
  type PatchDraft, type Point, type Reference, type RegionKey} from './model';

import {normalizedImagePoint, pairedProbe, sourcePixelPoint} from './sourceGeometry';

type Mode = 'outer' | 'plateau' | 'contour' | 'hair_samples' | 'background_samples' | 'ears' | 'neck' | 'other_people';
const REGION_LABELS: Record<RegionKey, string> = {crown: '颅顶', left: '画面左侧', right: '画面右侧'};
const MODE_LABELS: Record<Mode, string> = {outer: '过渡外界：点选矩形两角', plateau: '轮廓平台：点选矩形两角',
  contour: '可见头发外轮廓', hair_samples: '轮廓内真实头发采样点', background_samples: '轮廓外清晰背景采样点',
  ears: '可见耳部保护框：点选两角', neck: '可见颈部保护框：点选两角', other_people: '其他人物保护框：点选两角'};
const PROTECTION_KEYS = ['ears', 'neck', 'other_people'] as const;
const isBoxMode = (mode: Mode) => mode === 'outer' || mode === 'plateau' || PROTECTION_KEYS.some(field => field === mode);

/** Every mark is measured on the hash-verified complete source, never a face-box extrapolation. */
export function HairVolumeSupportEditor({reference, draft, disabled, onChange, onPending, onSourceReady, onError}: {
  reference: Reference; draft: Draft; disabled: boolean; onChange: (draft: Draft) => void;
  onPending: (pending: boolean) => void; onSourceReady: (ready: boolean) => void; onError: (message: string) => void;
}) {
  const [region, setRegion] = useState<RegionKey>('crown'), [mode, setMode] = useState<Mode>('outer');
  const [corner, setCorner] = useState<Point | null>(null), [coordinates, setCoordinates] = useState(['', '']);
  const [clicking, setClicking] = useState(false);
  const click = useRef<{pointer: number; source: string; rect: DOMRect; client: Point} | null>(null);
  const [bounds, setBounds] = useState<string[]>(Array(8).fill('')), [boundsDirty, setBoundsDirty] = useState(false);
  const [loaded, setLoaded] = useState(''), [error, setError] = useState(''), [zoom, setZoom] = useState(1), [pan, setPan] = useState(false);
  const owner = useRef({onChange, onPending, onSourceReady, onError}); owner.current = {onChange, onPending, onSourceReady, onError};
  const mounted = useRef(false), sourceKey = key([reference.source, reference.face_ref, reference.source_png_sha256]), live = useRef(sourceKey);
  live.current = sourceKey;
  const patch = draft.regions[region] ?? emptyPatch(), width = reference.source.width - 1, height = reference.source.height - 1;
  const ready = !disabled && loaded === sourceKey;
  const pending = clicking || boundsDirty || !!corner || coordinates.some(value => value.trim() !== '');
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; owner.current.onPending(false); owner.current.onSourceReady(false);};}, []);
  useEffect(() => {owner.current.onPending(pending);}, [pending]);
  useEffect(() => {owner.current.onSourceReady(loaded === sourceKey);}, [loaded, sourceKey]);
  useLayoutEffect(() => {
    const value = draft.regions[region];
    setBounds([...(value?.x?.map(n => String(n * width)) ?? ['', '', '', '']), ...(value?.y?.map(n => String(n * height)) ?? ['', '', '', ''])]);
    setBoundsDirty(false); setCorner(null); setCoordinates(['', '']); setError(''); click.current = null; setClicking(false);
  }, [sourceKey, region]);
  useEffect(() => {setCorner(null); click.current = null; setClicking(false);}, [disabled, zoom, pan]);
  useEffect(() => {
    const cancel = () => {setCorner(null); click.current = null; setClicking(false);}, visibility = () => {if (document.hidden) cancel();};
    window.addEventListener('blur', cancel); document.addEventListener('visibilitychange', visibility);
    return () => {window.removeEventListener('blur', cancel); document.removeEventListener('visibilitychange', visibility);};
  }, []);
  function fail(message: string) {setError(message); owner.current.onError(message);}
  function changePatch(next: PatchDraft | null) {
    onChange({...draft, regions: {...draft.regions, [region]: next}, [`${region}_confirmed`]: false}); setError('');
  }
  function chooseMode(next: Mode) {setMode(next); setCorner(null); setCoordinates(['', '']); setError('');}
  function acceptBounds() {
    if (!ready) return;
    try {
      if (bounds.some(value => value.trim() === '')) throw Error('请先完整填写或点选过渡外界及内部平台的 8 个源图坐标。');
      const x = checkBounds(bounds.slice(0, 4).map(Number).map(n => n / width));
      const y = checkBounds(bounds.slice(4).map(Number).map(n => n / height));
      changePatch({...patch, x, y}); setBoundsDirty(false); setCorner(null);
    } catch (error) {fail(error instanceof Error ? error.message : '边界未采用。');}
  }
  function measure(point: Point) {
    if (!ready) return;
    if (point.some(n => !Number.isFinite(n) || n <= 0 || n >= 1)) throw Error('请标记当前完整源图内部；裁切、隐藏或图外轮廓不受支持。');
    if (isBoxMode(mode)) {
      if (!corner) {setCorner(point); return;}
      const box = checkBox([Math.min(corner[0], point[0]), Math.min(corner[1], point[1]), Math.max(corner[0], point[0]), Math.max(corner[1], point[1])]);
      if (mode === 'outer' || mode === 'plateau') {
        const next = [...bounds], first = mode === 'outer' ? 0 : 1, last = mode === 'outer' ? 3 : 2;
        next[first] = String(box[0] * width); next[last] = String(box[2] * width);
        next[4 + first] = String(box[1] * height); next[4 + last] = String(box[3] * height);
        setBounds(next); setBoundsDirty(true);
      } else {
        const field = mode as typeof PROTECTION_KEYS[number];
        if (draft.protection[field].length >= PROTECTION_LIMITS[field]) throw Error(`本类保护框最多 ${PROTECTION_LIMITS[field]} 个，未添加新框。`);
        onChange({...draft, protection: {...draft.protection, [field]: [...draft.protection[field], box],
          visible_anatomy_reviewed: false, whole_source_reviewed: false}, crown_confirmed: false, left_confirmed: false, right_confirmed: false});
      }
      setCorner(null); return;
    }
    const field = mode as 'contour' | 'hair_samples' | 'background_samples', points = patch[field];
    if (points.length >= 33) throw Error('每项最多 33 个配对采样点，未添加新点。');
    let measured = point;
    if (field !== 'contour') {
      const contour = patch.contour[points.length];
      if (!contour) throw Error('请先按顺序标记对应轮廓点，再添加同序号的头发或背景点。');
      // The user chooses the normal coordinate; tangent alignment is explicit, not inferred anatomy.
      measured = pairedProbe(point, contour, region);
    }
    changePatch({...patch, [field]: [...points, measured]});
  }
  function beginPick(event: PointerEvent<HTMLDivElement>) {
    if (!ready || pan || click.current || event.button !== 0 || !event.isPrimary) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    click.current = {pointer: event.pointerId, source: sourceKey, rect: event.currentTarget.getBoundingClientRect(), client: [event.clientX, event.clientY]};
    setClicking(true);
  }
  function finishPick(event: PointerEvent<HTMLDivElement>) {
    const started = click.current;
    if (!started || started.pointer !== event.pointerId) return;
    click.current = null; setClicking(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (!ready || pan || started.source !== sourceKey) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if ((['left', 'top', 'width', 'height'] as const).some(field => Math.abs(rect[field] - started.rect[field]) > .5)
      || Math.hypot(event.clientX - started.client[0], event.clientY - started.client[1]) > 6) {
      setCorner(null); fail('点选时来源图视图移动或发生拖动，本次点选已取消。请使用滚动平移模式移动视图。'); return;
    }
    event.preventDefault();
    try {measure(normalizedImagePoint([event.clientX, event.clientY], rect)); setCoordinates(['', '']); setError('');}
    catch (error) {fail(error instanceof Error ? error.message : '本次测量未添加。');}
  }
  function acceptPoint() {
    if (!ready) return;
    try {
      if (coordinates.some(value => value.trim() === '')) throw Error('请填写完整源图 X 与 Y 坐标。');
      measure(sourcePixelPoint([Number(coordinates[0]), Number(coordinates[1])], reference.source)); setCoordinates(['', '']); setError('');
    } catch (error) {fail(error instanceof Error ? error.message : '像素坐标未采用。');}
  }
  async function sourceLoaded(node: HTMLImageElement) {
    if (node.currentSrc !== reference.source_png || node.naturalWidth !== reference.source_preview_width || node.naturalHeight !== reference.source_preview_height) {
      setLoaded(''); fail('源图解码尺寸不符，不能在错误映射或占位图上标记。'); return;
    }
    try {
      const hash = await imageDigest(reference.source_png);
      if (!mounted.current || live.current !== sourceKey) return;
      if (hash !== reference.source_png_sha256) {setLoaded(''); fail('源图实际 PNG 字节摘要不符，不能标记或审核。'); return;}
      setLoaded(sourceKey);
    } catch {if (mounted.current && live.current === sourceKey) {setLoaded(''); fail('源图字节核验失败，测量已禁用。');}}
  }
  const stroke = Math.max(width, height) * .002;
  function boxGraphic(box: Box, id: string, color: string, dashed = false) {
    return <rect key={id} x={box[0] * width} y={box[1] * height} width={(box[2] - box[0]) * width} height={(box[3] - box[1]) * height}
      fill="none" stroke={color} strokeWidth={stroke} strokeDasharray={dashed ? `${stroke * 3} ${stroke * 2}` : undefined}/>;
  }
  function patchGraphic(value: PatchDraft, name: RegionKey) {
    const {x, y} = value, color = name === region ? '#f9cd78' : '#72d8cf';
    return <g key={name} opacity={name === region ? 1 : .55}>
      {x && y && <>{boxGraphic([x[0], y[0], x[3], y[3]], `${name}-outer`, color, true)}
        {boxGraphic([x[1], y[1], x[2], y[2]], `${name}-plateau`, color)}</>}
      <polyline points={value.contour.map(([x, y]) => `${x * width},${y * height}`).join(' ')} stroke={color} strokeWidth={stroke} fill="none"/>
      {(['contour', 'hair_samples', 'background_samples'] as const).map(field => value[field].map(([x, y], index) => <g key={`${name}-${field}-${index}`}>
        <circle cx={x * width} cy={y * height} r={stroke * 2} fill={field === 'contour' ? color : field === 'hair_samples' ? '#7ce899' : '#bda8ff'}/>
        <text x={x * width + stroke * 3} y={y * height - stroke * 2} fill="white" stroke="#111" strokeWidth={stroke * .2}
          fontSize={stroke * 7}>{index + 1}</text>
      </g>))}
    </g>;
  }
  return <section className="hair-volume-support" aria-label="当前来源照片的发量独立测量">
    <p>只手工标记当前人物实际可见的头发外轮廓。颅顶按从画面左到右排列；两侧按从上到下排列。“左 / 右”指照片画面，不推断解剖侧。没有默认颅顶、耳部关键点或自动人物头发实例蒙版。</p>
    <div className="hair-volume-toolbar"><label>本项轮廓<select value={region} disabled={disabled || pending} onChange={event => {setRegion(event.target.value as RegionKey); setMode('outer');}}>
      {REGION_KEYS.map(value => <option key={value} value={value}>{REGION_LABELS[value]}</option>)}</select></label>
      <label>测量内容<select value={mode} disabled={!ready || !!corner} onChange={event => chooseMode(event.target.value as Mode)}>
        {(Object.keys(MODE_LABELS) as Mode[]).map(value => <option key={value} value={value}>{MODE_LABELS[value]}</option>)}</select></label>
      <label>缩放<select value={zoom} disabled={!!corner} onChange={event => setZoom(Number(event.target.value))}>
        {[1, 2, 4, 8].map(value => <option key={value} value={value}>{value === 1 ? '完整适应' : `${value * 100}% 缩小图`}</option>)}</select></label>
      <button type="button" disabled={!!corner} aria-pressed={pan} onClick={() => setPan(!pan)}>{pan ? '恢复点选' : '滚动平移'}</button>
    </div>
    <div className="hair-volume-source-viewport"><div className="hair-volume-source"
      style={{width: `${zoom * 100}%`, aspectRatio: `${reference.source_preview_width}/${reference.source_preview_height}`, touchAction: pan ? 'pan-x pan-y' : 'none'}}
      onPointerDown={beginPick} onPointerUp={finishPick}
      onPointerCancel={() => {click.current = null; setClicking(false); setCorner(null);}}
      onLostPointerCapture={() => {click.current = null; setClicking(false);}}>
      <img key={sourceKey} src={reference.source_png} draggable={false} alt="当前未变形完整来源照片，手工标记真实头发轮廓、清晰背景和可见保护区域"
        onLoad={event => {void sourceLoaded(event.currentTarget);}} onError={() => {setLoaded(''); fail('完整源图未加载，不能在占位图上测量。');}}/>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        {REGION_KEYS.map(name => draft.regions[name] && patchGraphic(draft.regions[name]!, name))}
        {PROTECTION_KEYS.map(field => draft.protection[field].map((box, i) => boxGraphic(box, `${field}-${i}`, '#ff8b96')))}
        {corner && <circle cx={corner[0] * width} cy={corner[1] * height} r={stroke * 3} fill="#fff"/>}
      </svg>
    </div></div>
    <p role="status">{loaded === sourceKey ? `来源 PNG 字节与尺寸已核对。${reference.source_kind === 'derived' ? '这是当前实际修复派生源，不复用旧原片定位。' : '这是当前不可变原片源。'}` : '正在核验实际完整源图，核验前不能测量。'} {corner ? '已选第一角，请选第二角或取消。' : ''}</p>
    <p>虚线框为位移归零的过渡外界，实线框为轮廓及头发采样平台；颅顶下边与侧面内边保持固定，外围清晰背景连续过渡。红框保护可见耳、颈和其他人物。不要把头发与人脸、耳、衣服、手或他人接触的轮廓强行纳入。</p>
    <fieldset disabled={!ready}><legend>{REGION_LABELS[region]} · 过渡外界及平台（规范源图像素）</legend>
      <div className="hair-volume-bound-grid">{['X a 外左', 'X b 内左', 'X c 内右', 'X d 外右', 'Y a 外上', 'Y b 内上', 'Y c 内下', 'Y d 外下'].map((label, index) =>
        <label key={label}>{label}<input type="number" step="any" min={0} max={index < 4 ? width : height} value={bounds[index]}
          onChange={event => {const value = event.target.value; setBounds(old => old.map((n, i) => i === index ? value : n)); setBoundsDirty(true);}}/></label>)}</div>
      <div className="hair-volume-toolbar"><button type="button" disabled={!boundsDirty || !!corner} onClick={acceptBounds}>采用此项边界</button>
        <button type="button" disabled={!boundsDirty} onClick={() => {setBounds([...(patch.x?.map(n => String(n * width)) ?? ['', '', '', '']),
          ...(patch.y?.map(n => String(n * height)) ?? ['', '', '', ''])]); setBoundsDirty(false); setCorner(null);}}>取消未采用边界</button></div>
    </fieldset>
    <p>当前 {REGION_LABELS[region]}：轮廓 {patch.contour.length} 点，头发 {patch.hair_samples.length} 点，背景 {patch.background_samples.length} 点。每项需 3–33 组，编号逐一对应。绿点为实际头发，紫点为清晰背景。采样点的切向坐标固定到同编号轮廓的{region === 'crown' ? ' X' : ' Y'}，由你点选另一坐标，不自动生成偏移。</p>
    <div className="hair-volume-toolbar"><label>源图 X<input type="number" min={0} max={width} step="any" value={coordinates[0]} disabled={!ready}
      onChange={event => setCoordinates([event.target.value, coordinates[1]])}/></label>
      <label>源图 Y<input type="number" min={0} max={height} step="any" value={coordinates[1]} disabled={!ready}
        onChange={event => setCoordinates([coordinates[0], event.target.value])}/></label>
      <button type="button" disabled={!ready || coordinates.some(value => !value.trim())} onClick={acceptPoint}>采用当前测量点</button>
      <button type="button" disabled={!corner && coordinates.every(value => !value)} onClick={() => {setCorner(null); setCoordinates(['', '']);}}>取消未完成点选</button>
    </div>
    <div className="hair-volume-toolbar">
      <button type="button" disabled={!ready || pending || isBoxMode(mode) || !patch[mode as 'contour']?.length} onClick={() => {
        if (mode === 'contour') changePatch({...patch, contour: patch.contour.slice(0, -1), hair_samples: [], background_samples: []});
        else if (mode === 'hair_samples' || mode === 'background_samples') changePatch({...patch, [mode]: patch[mode].slice(0, -1)});
      }}>撤回本组最后一点{mode === 'contour' ? '（并清空配对采样）' : ''}</button>
      <button type="button" disabled={!ready || pending || !draft.regions[region]} onClick={() => {changePatch(null); setBounds(Array(8).fill(''));}}>清空此项轮廓与边界草稿</button>
      {PROTECTION_KEYS.map(field => <button type="button" key={field} disabled={!ready || pending || !draft.protection[field].length} onClick={() =>
        onChange({...draft, protection: {...draft.protection, [field]: draft.protection[field].slice(0, -1), visible_anatomy_reviewed: false, whole_source_reviewed: false}})}>
        撤回{field === 'ears' ? '耳部' : field === 'neck' ? '颈部' : '他人'}最后一框（{draft.protection[field].length}）</button>)}
    </div>
    <p>只标记实际可见的耳、颈和其他人物，不推测隐藏解剖。所选人物真实人脸及保留的其他真实人脸由引擎额外保护。合并头发语义证据仅核验实际头发/背景探针，不等于人物实例分割，也不授权其他工具的蒙版。</p>
    {pending && <p role="status">还有未采用的坐标或未完成框，请采用或取消后再确认轮廓并生成效果。</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
