import {useEffect,useState} from 'react';
import {historyMessage,mutateNamedVersion,readNamedVersions} from '../historyNavigation/owner';
import {validName} from '../historyNavigation/model';
import type {HistoryOwner} from '../historyNavigation/HistoryPanel';
export function NamedRecipeVersionsPanel({owner,context,disabled,onChanged}:{owner:HistoryOwner;context:string;disabled:boolean;onChanged:()=>Promise<void>}){
  const [name,setName]=useState('');
  const [refreshNeeded,setRefreshNeeded]=useState(false);
  useEffect(()=>{
    if(refreshNeeded&&!disabled&&!owner.busy&&!owner.pending){setRefreshNeeded(false);void readNamedVersions(context);}
  },[refreshNeeded,disabled,owner.busy,owner.pending,context]);
  const locked=disabled||owner.busy||!!owner.pending;
  const apply=async(action:Parameters<typeof mutateNamedVersion>[0])=>{
    if(await mutateNamedVersion(action,context)){
      try{await onChanged();setRefreshNeeded(true);}catch(e){historyMessage(`命名版本终态已保留，但刷新失败：${String(e)}`);}
    }
  };
  return <section aria-label="命名配方版本">
    <h4>命名配方版本</h4>
    <p><small>保存当前配方的独立命名快照，不是系统修订号、虚拟副本或整工程恢复快照。选择版本会作为新编辑恢复到工作版本；后续修改不会覆盖命名快照。创建、改名或选择后请保存工程。</small></p>
    <button type="button" disabled={locked} onClick={()=>void readNamedVersions(context)}>读取 / 刷新命名版本</button>
    <label>版本名称 <input value={name} maxLength={160} disabled={locked} onChange={e=>setName(e.target.value)} placeholder="例如：自然光方案"/></label>
    <button type="button" disabled={locked||!owner.catalog||!validName(name)} onClick={()=>void apply({action:'named_create',name})}>保存当前配方为命名版本</button>
    {owner.catalog&&<ul>{owner.catalog.versions.map(version=><li key={version.id}>
      <span>{version.name}</span>{' '}
      <button type="button" disabled={locked} onClick={()=>void apply({action:'named_select',version_id:version.id})}>选择并恢复此版本</button>{' '}
      <button type="button" disabled={locked||!validName(name)} onClick={()=>void apply({action:'named_rename',version_id:version.id,name})}>改为上方名称</button>
    </li>)}</ul>}
    {owner.catalog?.versions.length===0&&<p>当前照片尚无命名版本。</p>}
  </section>;
}
