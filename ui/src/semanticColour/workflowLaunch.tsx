import {useState} from 'react';

/** Exact handbook entry routes to the mounted workflow, not a copied preset. */
export function SemanticColourWorkflowLaunch({enabled}:{enabled:boolean}){
 const [notice,setNotice]=useState('');
 const reveal=()=>{
  const panel=document.querySelector<HTMLDetailsElement>('details[data-control-id="PC-32452-C-e92914a50b"]');
  if(!panel){setNotice('请先打开照片并进入精修工作区，等待 AI 语义追色面板就绪。');return;}
  panel.open=true;panel.scrollIntoView({behavior:'smooth',block:'center'});
  const summary=panel.querySelector('summary');summary?.focus();setNotice('');
 };
 return <div className="toolRouteNote"><button className="toolRouteLink" disabled={!enabled} onClick={reveal}>AI 追色批量重新拟合 / 便携预设</button>
  <p>{notice||(!enabled?'请打开照片并使用声明追色工作流协议的配套引擎。':'进入独立审核面板。仅全图模式可携带，所有目标重新拟合；导出样片照片需明确同意。')}</p></div>;
}
