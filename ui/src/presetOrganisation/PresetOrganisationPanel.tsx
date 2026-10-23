import {useRef,useState,type DragEvent} from 'react';
import {confirm} from '@tauri-apps/plugin-dialog';
import {normalName,validName,type Edit,type Preset} from './model';
import {useOrganisation} from './useOrganisation';
import './organisation.css';
type Drag={kind:'category'|'preset';id:string;revision:string};
export function PresetOrganisationPanel({enabled,externalBusy=false,onChanged,onSelect,sourceVersion}:{sourceVersion:unknown;enabled:boolean;externalBusy?:boolean;onChanged:()=>void|Promise<void>;onSelect:(id:string)=>void}){
  const w=useOrganisation(enabled,onChanged,sourceVersion),[filter,setFilter]=useState(''),[trash,setTrash]=useState(false);
  const [draft,setDraft]=useState<{kind:'category'|'preset';id:string;value:string;create:boolean}|null>(null);
  const [menu,setMenu]=useState<string|null>(null),[dialog,setDialog]=useState(false),[dialogError,setDialogError]=useState('');
  const dragging=useRef<Drag|null>(null),dialogLock=useRef(false);
  const blocked=w.busy||!!w.uncertain||externalBusy||dialog||!enabled||!w.view||!!w.view.errors.length;
  const cats=w.view?.categories??[],presets=w.view?.presets??[],active=cats.filter(c=>!c.deleted);
  const filtered=presets.filter(p=>p.deleted===trash&&(!filter||p.kind===filter));
  const submit=(edit:Edit)=>{if(!blocked)void w.edit(edit);};
  function start(event:DragEvent,kind:Drag['kind'],id:string){
    if(blocked||trash){event.preventDefault();return;}
    dragging.current={kind,id,revision:w.view!.revision};event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',id);
  }
  function drop(event:DragEvent,cid:string,before:string|null=null){
    event.preventDefault();event.stopPropagation();const drag=dragging.current;dragging.current=null;
    if(!drag||blocked||trash||drag.revision!==w.view?.revision)return;
    if(drag.kind==='category'){if(drag.id!==cid)submit({action:'category_move',id:drag.id,before_id:cid});}
    else if(drag.id!==before)submit({action:'preset_move',id:drag.id,category_id:cid,before_id:before});
  }
  async function remove(edit:Edit,label:string){
    if(blocked||dialogLock.current)return;dialogLock.current=true;setDialog(true);
    try{if(await confirm(`将“${label}”移入回收站？\n不删除预设配方或 LUT/参考素材，不撤销照片调整，可从回收站恢复。`,{title:'移入回收站',kind:'warning'}))await w.edit(edit);}
    catch(error){setDialogError(String(error));}
    finally{dialogLock.current=false;setDialog(false);setMenu(null);}
  }
  function move(p:Preset,delta:number){
    // Use unfiltered siblings: filtering never renumbers or replaces hidden rows.
    const siblings=presets.filter(v=>!v.deleted&&v.category_id===p.category_id),index=siblings.findIndex(v=>v.id===p.id);
    if(index+delta<0||index+delta>=siblings.length)return;
    submit({action:'preset_move',id:p.id,category_id:p.category_id,before_id:delta<0?siblings[index-1].id:siblings[index+2]?.id??null});
  }
  if(!enabled)return <p>分类管理需要支持持久化目录回执的配套引擎。</p>;
  return <section className="presetOrganisation" aria-label="预设分类管理">
    <h4>分类与排序</h4>
    <p>拖动分类或预设排序，跨分类拖放移动。内置预设可排序，不可改名或删除。筛选不会改变隐藏项顺序。</p>
    <div className="organisationActions">
      <button disabled={blocked} onClick={()=>setDraft({kind:'category',id:`category-${crypto.randomUUID()}`,value:'',create:true})}>新建分类</button>
      <button disabled={w.busy||dialog} onClick={()=>void w.refresh()}>刷新分类</button>
      <label>类型<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="">全部类型</option>{[...new Set(presets.map(p=>p.kind))].sort().map(kind=><option key={kind} value={kind}>{kind}</option>)}</select></label>
      <label><input type="checkbox" checked={trash} onChange={e=>{setTrash(e.target.checked);setMenu(null);}}/>回收站</label>
    </div>
    {draft&&<form onSubmit={e=>{e.preventDefault();if(blocked||!validName(draft.value))return;submit({action:draft.create?'category_create':draft.kind==='category'?'category_rename':'preset_rename',id:draft.id,name:normalName(draft.value)});setDraft(null);}}>
      <label>{draft.create?'新分类名称':'重命名'}<input autoFocus value={draft.value} disabled={blocked} onChange={e=>setDraft({...draft,value:e.target.value})}/></label>
      <small>{Array.from(normalName(draft.value)).length}/20 字符；同分类中名称不区分大小写，不能重复。</small>
      <button disabled={blocked||!validName(draft.value)}>保存名称</button><button type="button" onClick={()=>setDraft(null)}>取消</button>
    </form>}
    {active.map((category,index)=><section key={category.id} className="organisationCategory" aria-label={category.name}
      onDragOver={e=>{if(!blocked&&!trash)e.preventDefault();}} onDrop={e=>drop(e,category.id)}>
      <div className="organisationCategoryHeading" draggable={!blocked&&!trash} onDragStart={e=>start(e,'category',category.id)} onDragEnd={()=>{dragging.current=null;}}>
        <strong>{category.name}</strong><small>{presets.filter(p=>!p.deleted&&p.category_id===category.id).length} 项</small>
        {!trash&&<>
          <button disabled={blocked||index===0} aria-label={`上移分类 ${category.name}`} onClick={()=>submit({action:'category_move',id:category.id,before_id:active[index-1].id})}>↑</button>
          <button disabled={blocked||index===active.length-1} aria-label={`下移分类 ${category.name}`} onClick={()=>submit({action:'category_move',id:category.id,before_id:active[index+2]?.id??null})}>↓</button>
          {!['builtin','custom'].includes(category.id)&&<><button disabled={blocked} onClick={()=>setDraft({kind:'category',id:category.id,value:category.name,create:false})}>重命名分类</button>
            <button disabled={blocked||presets.some(p=>p.category_id===category.id)||!!w.view?.missing.some(p=>p.category_id===category.id)} title="仅删除空分类；预设可先移到其他分类" onClick={()=>void remove({action:'category_trash',id:category.id},category.name)}>删除空分类</button></>}
        </>}
      </div>
      <ul>{filtered.filter(p=>p.category_id===category.id).map(p=>{
        const siblings=presets.filter(v=>!v.deleted&&v.category_id===p.category_id),position=siblings.findIndex(v=>v.id===p.id);
        return <li key={p.id} draggable={!blocked&&!trash} onDragStart={e=>{e.stopPropagation();start(e,'preset',p.id);}} onDragEnd={()=>{dragging.current=null;}}
          onDragOver={e=>{if(!blocked&&!trash)e.preventDefault();}} onDrop={e=>drop(e,category.id,p.id)}
          onContextMenu={e=>{e.preventDefault();setMenu(p.id);}}>
          <button disabled={trash||externalBusy} onClick={()=>onSelect(p.id)}>{p.name}</button><small>{p.kind} · {p.id}</small>
          {trash?<button disabled={blocked} onClick={()=>submit({action:'preset_restore',id:p.id})}>恢复</button>:<>
            <button disabled={blocked||position===0} aria-label={`上移预设 ${p.name}`} onClick={()=>move(p,-1)}>↑</button>
            <button disabled={blocked||position===siblings.length-1} aria-label={`下移预设 ${p.name}`} onClick={()=>move(p,1)}>↓</button>
            {!p.builtin&&<><label>移动到<select aria-label={`移动 ${p.name} 到分类`} disabled={blocked} value={p.category_id} onChange={e=>submit({action:'preset_move',id:p.id,category_id:e.target.value,before_id:null})}>{active.filter(c=>c.id!=='builtin').map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
            <button disabled={blocked} aria-expanded={menu===p.id} onClick={()=>setMenu(menu===p.id?null:p.id)}>更多</button></>}
            {menu===p.id&&!p.builtin&&<div role="group" aria-label={`${p.name} 操作`} onKeyDown={e=>{if(e.key==='Escape')setMenu(null);}}>
              <button disabled={blocked} onClick={()=>{setDraft({kind:'preset',id:p.id,value:p.name,create:false});setMenu(null);}}>重命名预设</button>
              <button disabled={blocked} onClick={()=>void remove({action:'preset_trash',id:p.id},p.name)}>移入回收站</button><button onClick={()=>setMenu(null)}>关闭</button>
            </div>}
          </>}
        </li>;
      })}</ul>
      {!filtered.some(p=>p.category_id===category.id)&&<p>{trash?'此分类没有已删除预设':filter?'没有此类型的预设':'空分类，可拖入预设'}</p>}
    </section>)}
    {trash&&cats.filter(c=>c.deleted).map(c=><p key={c.id}>{c.name}（已删除空分类） <button disabled={blocked} onClick={()=>submit({action:'category_restore',id:c.id})}>恢复分类</button></p>)}
    {dialogError&&<p role="alert">{dialogError}</p>}
    <p role="status" aria-live="polite">{w.message}</p>
    {!!w.view?.missing.length&&<details><summary>源文件缺失，分类引用仍保留</summary>{w.view.missing.map(p=><p key={p.id}>{p.id}（分类 {cats.find(c=>c.id===p.category_id)?.name}）：请恢复原配方文件或导入同 ID 文件；不会自动删除引用或素材。</p>)}</details>}
    {w.uncertain&&<div role="alert"><p>原请求：{w.uncertain}。目录操作未确认，禁止重复提交。</p><button disabled={w.busy} onClick={()=>void w.query()}>查询原操作</button><button disabled={w.busy} onClick={w.inspected}>已刷新并核对，结束等待</button></div>}
    {!!w.view?.errors.length&&<details open><summary>先修复源目录问题，分类修改已禁用</summary>{w.view.errors.map((e,i)=><p key={i}>{e.file}：{e.error}</p>)}</details>}
    <small>分类目录独立于照片历史。重命名与移动保留预设 ID；回收站不回收引用素材。</small>
  </section>;
}
