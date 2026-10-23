import {useEffect,useState,type MouseEvent} from 'react';
import {CONFIRMATIONS,refKey,type BodyChoice,type Support,type Box} from './model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
export function NeckSupportEditor({body,image,disabled,onReview}:{body:BodyChoice;image:SourceImage|null;disabled:boolean;onReview:(v:Support)=>Promise<void>}){
 const [draft,setDraft]=useState<Partial<Support>>({}),[target,setTarget]=useState('upper'),[station,setStation]=useState(0),[corner,setCorner]=useState<number[]|null>(null),[flags,setFlags]=useState<Record<string,boolean>>({}),[error,setError]=useState(''),[loaded,setLoaded]=useState('');
 const context=`${refKey(body.body_ref)}:${body.points_sha256}:${JSON.stringify(body.support)}`;
 useEffect(()=>{setDraft(body.support?structuredClone(body.support):{});setFlags({});setCorner(null);setStation(0);setTarget('upper');},[context]);
 const matched=matchesSource(image,body.source),key=matched&&image?image.url:'';const ready=matched&&key!==''&&loaded===key&&!disabled;
 function change(v:Partial<Support>){setDraft(v);setFlags({});setError('');}
 function pick(e:MouseEvent<SVGSVGElement>){if(!ready)return;try{const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());const x=p.x/(body.source.width-1),y=p.y/(body.source.height-1);if(x<=0||x>=1||y<=0||y>=1)throw Error('请选择源图内部可见位置');
 if(['head_box','transition_box','exclusions'].includes(target)){if(!corner){setCorner([x,y]);return;}const b:Box=[Math.min(x,corner[0]),Math.min(y,corner[1]),Math.max(x,corner[0]),Math.max(y,corner[1])];setCorner(null);if(b[0]===b[2]||b[1]===b[3])throw Error('矩形不能退化');if(target==='exclusions')change({...draft,exclusions:[...(draft.exclusions??[]),b]});else change({...draft,[target]:b});return;}
 if(target==='upper'||target==='lower'||target==='center_x'){change({...draft,[target]:target==='center_x'?x:y,negative:undefined,positive:undefined});return;}
 if(draft.upper==null||draft.lower==null||draft.center_x==null||draft.upper>=draft.lower)throw Error('先指定真实上下界和中心轴');
 const expected=draft.upper+station*(draft.lower-draft.upper)/4;if(Math.abs(y-expected)>.04*(draft.lower-draft.upper))throw Error('请沿当前截线点击真实轮廓');
 if(target==='negative'?x>=draft.center_x:x<=draft.center_x)throw Error('请选择指定的屏幕侧');
 const side=target as 'negative'|'positive';const values=[...(draft[side]??Array(5).fill(null))];values[station]=Math.abs(x-draft.center_x);change({...draft,[side]:values});setStation((station+1)%5);
 }catch(e){setError(e instanceof Error?e.message:'测量失败');}}
 async function save(){try{if(!ready||Object.keys(CONFIRMATIONS).some(k=>flags[k]!==true)||draft.upper==null||draft.lower==null||draft.center_x==null||!draft.head_box||!draft.transition_box||!draft.anatomical_left||[draft.negative,draft.positive].some(a=>!a||a.length!==5||a.some(n=>typeof n!=='number'||!Number.isFinite(n)||n<=0)))throw Error('请完整测量并逐项复核，不会补齐隐藏轮廓');await onReview({...draft,version:1,exclusions:draft.exclusions??[],confirmations:flags} as Support);setError('');}catch(e){setError(e instanceof Error?e.message:'复核未保存');}}
 const w=body.source.width-1,h=body.source.height-1;
 return <fieldset disabled={disabled}><legend>颈部与完整头发原图复核</legend><p>逐项点击原图。左右各五点为真实颈部轮廓；头部框须包含完整头发和脸，不能用脸框代替。仅支持清晰近正面颈部；衣领、头发遮挡或严重透视时不要确认。</p>
 <select value={target} onChange={e=>{setTarget(e.target.value);setCorner(null);setStation(0);}}>{Object.entries({upper:'脖子上界',lower:'脖子下界',center_x:'脖子中心轴',negative:'屏幕左轮廓五点',positive:'屏幕右轮廓五点',head_box:'完整头部头发框（两角）',transition_box:'过渡外框（两角）',exclusions:'排除框（两角）'}).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select>
 <label>人物解剖左侧<select value={draft.anatomical_left??''} onChange={e=>change({...draft,anatomical_left:e.target.value as Support['anatomical_left']})}><option value="">请核对</option><option value="negative">屏幕左侧</option><option value="positive">屏幕右侧</option></select></label>
 {matched&&image?<div style={{position:'relative'}}><img src={image.url} alt="未变形全图颈部测量参考" style={{width:'100%',display:'block'}} onLoad={e=>setLoaded(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight?key:'')} onError={()=>setLoaded('')}/><svg viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} style={{position:'absolute',inset:0,width:'100%',height:'100%'}}>
 {draft.upper!=null&&draft.lower!=null&&Array.from({length:5},(_,i)=><line key={i} x1={0} x2={w} y1={(draft.upper!+i*(draft.lower!-draft.upper!)/4)*h} y2={(draft.upper!+i*(draft.lower!-draft.upper!)/4)*h} stroke={i===station?'magenta':'cyan'} strokeWidth={w*.001}/>)}
 {(['negative','positive'] as const).flatMap(s=>(draft[s]??[]).map((n,i)=>typeof n==='number'&&draft.center_x!=null&&draft.upper!=null&&draft.lower!=null?<circle key={`${s}${i}`} cx={(draft.center_x+(s==='negative'?-n:n))*w} cy={(draft.upper+i*(draft.lower-draft.upper)/4)*h} r={w*.003} fill="yellow"/>:null))}
 {[draft.head_box,draft.transition_box,...draft.exclusions??[]].map((b,i)=>b?<rect key={i} x={b[0]*w} y={b[1]*h} width={(b[2]-b[0])*w} height={(b[3]-b[1])*h} fill="none" stroke={i<2?'lime':'red'} strokeWidth={w*.002}/>:null)}
 </svg></div>:<p role="status">缺少匹配的未变形全图参考，不能复核。</p>}
 <p>轮廓站 {station+1}/5。测量与原图归属随照片和分析修订绑定，不能复制到另一张照片。</p>
 {Object.entries(CONFIRMATIONS).map(([k,v])=><label key={k} style={{display:'block'}}><input type="checkbox" checked={flags[k]===true} disabled={!ready} onChange={e=>setFlags({...flags,[k]:e.target.checked})}/>{v}</label>)}
 <button type="button" disabled={!ready} onClick={()=>void save()}>保存原图复核</button><button type="button" onClick={()=>change({...draft,exclusions:[]})}>清空排除框</button>{error&&<p role="alert">{error}</p>}
 </fieldset>;
}
