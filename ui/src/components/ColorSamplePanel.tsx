import type {ColorSampler} from '../useColorSampler';
import type {CapturePoint} from '../captureModel';
export function ColorSamplePanel({sampler,canArm,reason,onArm}:{sampler:ColorSampler;canArm:boolean;reason:string;onArm:()=>void}){
  const {ui,size,setSize}=sampler,analysis=ui.readout?.analysis,region=ui.readout?.region;
  const triple=(values:number[]|null|undefined,scale=1)=>values?values.map(v=>(v*scale).toFixed(3)).join(' / '):'无有效读数';
  return <section data-readonly-scopes aria-label="颜色取样">
    <strong>RGB / Lab 取色</strong>
    <div><button type="button" disabled={!canArm} title={reason} onClick={onArm}>{sampler.active?'重新锁定画面':'锁定画面取色'}</button>
      <button type="button" disabled={!sampler.active} onClick={sampler.cancel}>退出</button></div>
    <label>平均范围 <select value={size} onChange={e=>setSize(Number(e.target.value) as CapturePoint['size'])}>
      {[1,3,5,11].map(n=><option key={n} value={n}>{n} × {n} 像素</option>)}</select></label>
    <p role="status">{ui.message||reason||'锁定后点击画面；滚轮缩放，中键平移，Esc 退出。'}</p>
    {ui.frame&&<small>代理输出 {ui.frame.descriptor.width} × {ui.frame.descriptor.height}；读数来自浮点处理结果，不是屏幕截图。</small>}
    {analysis&&<dl><dt>RGB（0–1）</dt><dd>{triple(analysis.mean_srgb)}</dd>
      <dt>RGB（×255）</dt><dd>{triple(analysis.mean_srgb,255)}</dd>
      <dt>Lab（D65）</dt><dd>{triple(analysis.mean_lab_d65)}</dd>
      <dt>实际取样区域</dt><dd>{region?`${region.x}, ${region.y} · ${region.width} × ${region.height}`:'未知'}；有效 {analysis.finite_samples} / {analysis.samples}</dd></dl>}
  </section>;
}
