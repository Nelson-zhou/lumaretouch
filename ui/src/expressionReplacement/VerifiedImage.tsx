// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import {verifyImage,type Image,type Source} from './model';
export function VerifiedImage({image,source,label,onReady,children}:{image:Image;source:Source;label:string;onReady:(ready:boolean)=>void;children?:ReactNode}){
  const key=`${source.asset_sha256}:${source.retained_asset_id}:${image.sha256}:${image.width}:${image.height}`;
  const notify=useRef(onReady);notify.current=onReady;
  const [verified,setVerified]=useState(''),[loaded,setLoaded]=useState(''),[failed,setFailed]=useState('');
  useLayoutEffect(()=>{setVerified('');setLoaded('');setFailed('');notify.current(false);},[key]);
  useEffect(()=>{
    let live=true;
    void verifyImage(image,source).then(valid=>{if(!live)return;if(valid)setVerified(key);else setFailed(key);}).catch(()=>{if(live)setFailed(key);});
    return()=>{live=false;notify.current(false);};
  },[key,image.base64]);
  const ready=verified===key&&loaded===key&&failed!==key;
  useEffect(()=>{notify.current(ready);},[ready,key]);
  return <figure className="expression-image"><figcaption>{label}</figcaption>
    <div className="expression-image-stage">
      <img key={key} src={`data:image/png;base64,${image.base64}`} draggable={false} alt={label}
        onLoad={event=>{if(event.currentTarget.naturalWidth===image.width&&event.currentTarget.naturalHeight===image.height)setLoaded(key);else{setLoaded('');setFailed(key);notify.current(false);}}}
        onError={()=>{setLoaded('');setFailed(key);notify.current(false);}}/>
      {ready&&children}
    </div>
    {!ready&&<p role="status">{failed===key?'全图 PNG 内容、尺寸或加载校验失败，不能确认。':'正在校验并显示完整画面…'}</p>}
  </figure>;
}
