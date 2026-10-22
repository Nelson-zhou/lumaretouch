import {useEffect,useState} from 'react';
import './layout.css';
import {invoke} from '@tauri-apps/api/core';
import {changeUnit,layoutSummary,units,type LayoutReceipt,type LayoutSpec,type useLayoutSettings} from './model';

export function LayoutControls({model,disabled,selected,receipt}:{model:ReturnType<typeof useLayoutSettings>;
  disabled:boolean;selected:number;receipt?:LayoutReceipt|null}) {
  const {layout,setLayout,templates,readTemplates,saveTemplate,storageError}=model;
  const [name,setName]=useState(''); const [printBusy,setPrintBusy]=useState(false); const [message,setMessage]=useState('');
  useEffect(()=>{readTemplates();},[]);
  const summary=layoutSummary(layout,selected);
  const number=(key:keyof LayoutSpec,label:string,min:number,max:number,step=1)=><label key={key}>{label}
    <input aria-label={label} type="number" min={min} max={max} step={step} value={layout[key] as number}
      onChange={e=>setLayout({...layout,[key]:Number(e.target.value)})}/></label>;
  async function action(command:'print_layout'|'open_layout_pdf') {
    if (!receipt?.manifest || printBusy) return;
    setPrintBusy(true);setMessage('');
    try {const result=await invoke<{outcome:string}>(command,{manifest:receipt.manifest});
      setMessage(result.outcome==='submitted'?'已交给系统打印后端，尚未确认实体打印结果':
        result.outcome==='cancelled'?'已取消打印，文件保留':result.outcome==='opened'?'已请求系统 PDF 查看器打开文件':'打印结果未知，请检查系统打印队列');
    } catch(e){setMessage(String(e));} finally{setPrintBusy(false);}
  }
  return <section className="layoutControls" style={{borderTop:'1px solid #555',paddingTop:12}}>
    <fieldset disabled={disabled} style={{border:0,padding:0}}>
      <label><input type="checkbox" checked={layout.enabled} onChange={e=>setLayout({...layout,enabled:e.target.checked})}/>排版印刷（保留单张导出）</label>
      {layout.enabled && <>
        <div className="exGrid">
          <label>排版类型<select value={layout.mode} onChange={e=>setLayout({...layout,mode:e.target.value as LayoutSpec['mode']})}><option value="ordinary">普通多图排版</option><option value="id">证件照尺寸排版</option></select></label>
          <label>单位<select value={layout.unit} onChange={e=>setLayout(changeUnit(layout,e.target.value as LayoutSpec['unit']))}><option>mm</option><option>cm</option><option value="in">英寸</option></select></label>
          <label>相纸快捷设置<select value="" onChange={e=>{const [w,h]=e.target.value.split(',').map(Number);if(w&&h)setLayout({...layout,paperWidth:w/units[layout.unit],paperHeight:h/units[layout.unit]});}}><option value="">自定 / 选择规格</option><option value="210,297">A4</option><option value="148,210">A5</option><option value="101.6,152.4">4×6 英寸相纸</option><option value="127,177.8">5×7 英寸相纸</option></select></label>
          <label>方向<select value={layout.orientation} onChange={e=>setLayout({...layout,orientation:e.target.value as LayoutSpec['orientation']})}><option value="portrait">竖向</option><option value="landscape">横向</option></select></label>
          {number('paperWidth','纸张边长一',.01,1000,.01)}{number('paperHeight','纸张边长二',.01,1000,.01)}
          {number('dpi','分辨率 DPI',72,1200)}{number('rows','行数',1,40)}{number('columns','列数',1,40)}{number('copies','每张照片份数',1,100)}
          {number('marginTop','上边距',0,1000,.01)}{number('marginBottom','下边距',0,1000,.01)}
          {number('marginLeft','左边距',0,1000,.01)}{number('marginRight','右边距',0,1000,.01)}
          {number('gapX','水平间隔',0,1000,.01)}{number('gapY','垂直间隔',0,1000,.01)}
          {layout.mode==='id'&&<>{number('photoWidth','证件照宽',.01,1000,.01)}{number('photoHeight','证件照高',.01,1000,.01)}</>}
          <label>照片放置<select value={layout.fit} onChange={e=>setLayout({...layout,fit:e.target.value as LayoutSpec['fit']})}><option value="contain">完整保留（可能留白）</option><option value="cover">填满单元（居中裁切）</option></select></label>
        </div>
        <p>{summary.width.toFixed(2)} × {summary.height.toFixed(2)} mm · 预计 {summary.pages} 页 · {layout.dpi} DPI</p>
        {summary.error&&<p role="alert">{summary.error}</p>}
        <p>版面是 sRGB 8-bit；16-bit 单张照片仍原样保留。证件照不自动判定各国证件合规。按“开始导出”生成 PNG 页面与 PDF，不会自动打印。</p>
        <label>模板<select value="" onChange={e=>{if(templates[e.target.value])setLayout({...templates[e.target.value],enabled:true});}}><option value="">选择已保存模板</option>{Object.keys(templates).map(k=><option key={k}>{k}</option>)}</select></label>
        <input aria-label="排版模板名" placeholder="模板名" value={name} maxLength={80} onChange={e=>setName(e.target.value)}/>
        <button type="button" onClick={()=>saveTemplate(name)} disabled={!!summary.error}>保存新模板</button>
        {storageError&&<p role="alert">{storageError}</p>}
      </>}
    </fieldset>
    {receipt?.error&&<p role="alert">排版未完成：{receipt.error}</p>}
    {receipt?.manifest&&<div><p>上一批实际版面：{receipt.page_count} 页 · {receipt.width_mm} × {receipt.height_mm} mm · {receipt.dpi} DPI</p>
      <p style={{overflowWrap:'anywhere'}}>{receipt.pdf}</p>
      <button disabled={printBusy||disabled} onClick={()=>action('open_layout_pdf')}>打开实际 PDF</button>
      <button disabled={printBusy||disabled} onClick={()=>action('print_layout')}>系统打印…</button>
      <p>请在系统对话框核对纸张、100% 缩放及打印机不可打印边距；最后确认由你操作。</p></div>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
