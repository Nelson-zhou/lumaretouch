import {useState} from 'react';
export interface LayoutSpec {
  enabled: boolean; mode: 'ordinary'|'id'; unit: 'mm'|'cm'|'in';
  paperWidth: number; paperHeight: number; orientation: 'portrait'|'landscape'; dpi: number;
  rows: number; columns: number; marginTop: number; marginBottom: number; marginLeft: number;
  marginRight: number; gapX: number; gapY: number; photoWidth: number; photoHeight: number;
  copies: number; fit: 'contain'|'cover';
}
export interface LayoutReceipt {
  error?: string; manifest?: string; pdf?: string; pages?: string[]; page_count?: number;
  width_mm?: number; height_mm?: number; dpi?: number; bits?: number; profile?: string;
}
export const initialLayout = (): LayoutSpec => ({enabled:false, mode:'ordinary', unit:'mm',
  paperWidth:210, paperHeight:297, orientation:'portrait', dpi:300, rows:2, columns:2,
  marginTop:10, marginBottom:10, marginLeft:10, marginRight:10, gapX:5, gapY:5,
  photoWidth:25, photoHeight:35, copies:1, fit:'contain'});
export const units = {mm:1, cm:10, in:25.4};
export const lengths = ['paperWidth','paperHeight','marginTop','marginBottom','marginLeft','marginRight',
  'gapX','gapY','photoWidth','photoHeight'] as const;
export function changeUnit(spec:LayoutSpec, unit:LayoutSpec['unit']):LayoutSpec {
  const next = {...spec, unit};
  for (const field of lengths) next[field] = spec[field] * units[spec.unit] / units[unit];
  return next;
}
export function layoutSummary(spec:LayoutSpec, selected:number) {
  const short = Math.min(spec.paperWidth, spec.paperHeight) * units[spec.unit];
  const long = Math.max(spec.paperWidth, spec.paperHeight) * units[spec.unit];
  const [width,height] = spec.orientation==='portrait' ? [short,long] : [long,short];
  const cw = (width-(spec.marginLeft+spec.marginRight+(spec.columns-1)*spec.gapX)*units[spec.unit])/spec.columns;
  const ch = (height-(spec.marginTop+spec.marginBottom+(spec.rows-1)*spec.gapY)*units[spec.unit])/spec.rows;
  const validNumbers = [...lengths,'dpi','rows','columns','copies']
    .every(k=> typeof spec[k as keyof LayoutSpec]==='number' && Number.isFinite(spec[k as keyof LayoutSpec]));
  let error = !validNumbers ? '请输入有限数值' : '';
  if (short<25 || long>1000 || cw<1 || ch<1) error='纸张/边距/间隔/行列超出可用区域';
  if ([spec.rows,spec.columns,spec.copies,spec.dpi].some(v=>!Number.isInteger(v) || v<1)
    || spec.rows>40 || spec.columns>40 || spec.copies>100 || spec.dpi<72 || spec.dpi>1200
    || lengths.some(k=>spec[k]<0)) error='数值超出范围';
  if (spec.mode==='id' && (spec.photoWidth<=0 || spec.photoHeight<=0 || spec.photoWidth*units[spec.unit]>cw || spec.photoHeight*units[spec.unit]>ch)) error='证件照尺寸无法放入指定行列';
  const pages=Math.ceil(selected*spec.copies/(spec.rows*spec.columns));
  if (pages>200 || Math.round(width*spec.dpi/25.4)*Math.round(height*spec.dpi/25.4)>60_000_000) error='超过 200 页或单页 6000 万像素上限';
  return {width,height,pages,error};
}
const storageKey='lumaretouch.layout.templates.v1';
export function useLayoutSettings() {
  const [layout,setLayout]=useState(initialLayout);
  const [templates,setTemplates]=useState<Record<string,LayoutSpec>>({});
  const [storageError,setStorageError]=useState('');
  const readTemplates=()=>{
    try {
      const raw=JSON.parse(localStorage.getItem(storageKey)??'{}');
      if (!raw || typeof raw!=='object' || Array.isArray(raw)) throw Error('模板数据损坏');
      for (const spec of Object.values(raw) as LayoutSpec[]) {
        if (!spec || !['ordinary','id'].includes(spec.mode) || !['mm','cm','in'].includes(spec.unit)
          || !['portrait','landscape'].includes(spec.orientation) || !['contain','cover'].includes(spec.fit)
          || layoutSummary(spec,1).error) throw Error('模板参数无效，原数据已保留');
      }
      setTemplates(raw); setStorageError(''); return raw as Record<string,LayoutSpec>;
    } catch(e) { setStorageError(String(e)); return null; }
  };
  const saveTemplate=(name:string)=>{
    const old=readTemplates(); if (!old) return;
    if (!name.trim() || name.length>80 || layoutSummary(layout,1).error) {setStorageError('请填写模板名并修正排版参数');return;}
    if (Object.prototype.hasOwnProperty.call(old,name)) {setStorageError('模板名已存在，请换一个名字，避免覆盖');return;}
    try {const next={...old,[name]:{...layout}};localStorage.setItem(storageKey,JSON.stringify(next));setTemplates(next);setStorageError('');}
    catch(e){setStorageError(`模板未保存：${e}`);}
  };
  return {layout,setLayout,templates,readTemplates,saveTemplate,storageError};
}
