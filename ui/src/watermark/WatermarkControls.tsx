import {useState} from 'react';
import {open} from '@tauri-apps/plugin-dialog';
import {orientations, positions, type Orientation, type WatermarkProfile, type WatermarkSettings} from './model';
import './watermark.css';
const names = {landscape: '横图', portrait: '竖图', square: '方图'};
const anchors = ['左上', '中上', '右上', '左中', '居中', '右中', '左下', '中下', '右下'];
export function WatermarkControls({value, onChange, disabled, storageError}: {
  value: WatermarkSettings; onChange: (value: WatermarkSettings) => void; disabled: boolean; storageError: string;
}) {
  const [orientation, setOrientation] = useState<Orientation>('landscape');
  const [error, setError] = useState('');
  const p = value.profiles[orientation];
  function change(patch: Partial<WatermarkProfile>) {
    onChange({...value, profiles: {...value.profiles, [orientation]: {...p, ...patch}}});
  }
  async function pick(kind: 'image' | 'font') {
    try {
      const path = await open({multiple: false, directory: false, filters: [{name: kind === 'image' ? '水印图片' : '字体',
        extensions: kind === 'image' ? ['png', 'webp', 'jpg', 'jpeg', 'tif', 'tiff'] : ['ttf', 'otf', 'ttc']}]});
      if (typeof path === 'string') change(kind === 'image' ? {imagePath: path} : {fontPath: path});
      setError('');
    } catch (e) { setError(String(e)); }
  }
  function slider(key: 'opacity' | 'size' | 'margin' | 'offsetX' | 'offsetY' | 'rotation', label: string, min: number, max: number, step: number) {
    return <label className="wmSlider">{label}<input type="range" min={min} max={max} step={step} value={p[key]}
      onChange={e => change({[key]: Number(e.target.value)})}/><output>{key === 'rotation' ? `${p[key]}°` : `${Math.round(p[key]*100)}%`}</output></label>;
  }
  return <fieldset className="wmControls" disabled={disabled}>
    <legend>导出水印</legend>
    <label><input type="checkbox" checked={value.enabled} onChange={e => onChange({...value, enabled: e.target.checked})}/>启用水印</label>
    {value.enabled && <>
      <label><input type="checkbox" checked={value.alsoClean} onChange={e => onChange({...value, alsoClean: e.target.checked})}/>同时导出无水印副本（“无水印”子目录）</label>
      <div className="wmTabs" role="group" aria-label="画幅独立水印配置">{orientations.map(o => <button type="button" key={o} aria-pressed={o === orientation} onClick={() => setOrientation(o)}>{names[o]}</button>)}</div>
      <label>类型<select value={p.kind} onChange={e => change({kind: e.target.value as WatermarkProfile['kind']})}><option value="text">文字</option><option value="image">图片（保留透明度）</option></select></label>
      {p.kind === 'text' ? <>
        <label>文字<textarea maxLength={300} value={p.text} onChange={e => change({text: e.target.value})}/></label>
        <label>颜色<input type="color" value={p.color} onChange={e => change({color: e.target.value})}/></label>
        <label>字体<input placeholder="自动选择系统字体，或填入字体路径" value={p.fontPath} onChange={e => change({fontPath: e.target.value})}/><button type="button" onClick={() => void pick('font')}>选择字体</button></label>
      </> : <label>图片<input placeholder="PNG / WebP / JPEG / TIFF 路径" value={p.imagePath} onChange={e => change({imagePath: e.target.value})}/><button type="button" onClick={() => void pick('image')}>选择图片</button></label>}
      <div className="wmAnchors" role="group" aria-label="九宫格定位">{positions.map((position, i) => <button type="button" key={position} aria-pressed={p.position === position} onClick={() => change({position})}>{anchors[i]}</button>)}</div>
      {slider('opacity', '不透明度', 0, 1, .01)}{slider('size', '宽度 / 照片宽度', .01, 1, .01)}
      {slider('rotation', '顺时针旋转', -180, 180, 1)}{slider('margin', '画幅边距', 0, .45, .01)}
      {slider('offsetX', '水平偏移', -.5, .5, .01)}{slider('offsetY', '垂直偏移', -.5, .5, .01)}
      <label><input type="checkbox" checked={p.fit} onChange={e => change({fit: e.target.checked})}/>旋转后适合画幅（保留宽高比）</label>
      <button type="button" onClick={() => onChange({...value, profiles: {landscape: {...p}, portrait: {...p}, square: {...p}}})}>将当前配置复制到三种画幅</button>
      <small>按最终裁剪后的画幅选用配置；仅用于导出，不改变原图。设置在本机保存；提交时固定图片和字体内容。</small>
    </>}
    {(error || storageError) && <small role="alert">{error || storageError}</small>}
  </fieldset>;
}
export function WatermarkReceipt({outputs}: {outputs?: {path: string | null; variant: string; skipped?: boolean}[]}) {
  if (!outputs || outputs.length === 0) return null;
  return <small className="wmReceipt">{outputs.map((o, i) => <span key={i} title={o.path ?? ''}>{o.variant === 'clean' ? '无水印' : '水印'}：{o.skipped ? '同名跳过' : '已保存'} {o.path}</span>)}</small>;
}
