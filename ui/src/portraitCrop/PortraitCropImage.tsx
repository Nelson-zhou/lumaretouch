// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, type ReactNode} from 'react';
import {imageKey, imageUrl, type ImageProof} from './model';
export type PortraitCropImageProps = {
  value: ImageProof; identity: string; alt: string; children?: ReactNode;
  onReady: (identity: string, ready: boolean) => void;
};
/** Actual immutable PNG pixels, never a CSS crop, schematic or source-image stand-in. */
export function PortraitCropImage({value, identity, alt, children, onReady}: PortraitCropImageProps) {
  const key = `${identity}:${imageKey(value)}`;
  const [loaded, setLoaded] = useState(''), [verified, setVerified] = useState(''), [failed, setFailed] = useState('');
  const notify = useRef(onReady); notify.current = onReady;
  useEffect(() => {
    let live = true;
    setVerified(''); setFailed(''); notify.current(identity, false);
    void (async () => {
      try {
        const bytes = Uint8Array.from(atob(value.base64), char => char.charCodeAt(0));
        const digest = await crypto.subtle.digest('SHA-256', bytes);
        const actual = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
        if (live) {if (actual === value.sha256) setVerified(key); else setFailed(key);}
      } catch {if (live) setFailed(key);}
    })();
    return () => {live = false; notify.current(identity, false);};
  }, [key, identity, value.base64, value.sha256]);
  const ready = loaded === key && verified === key && failed !== key;
  useEffect(() => {notify.current(identity, ready);}, [identity, ready]);
  return <div className="portrait-crop-image-group">
    <div className="portrait-crop-image" style={{aspectRatio: `${value.source_width} / ${value.source_height}`}}>
      <img key={key} src={imageUrl(value)} width={value.width} height={value.height} alt={alt} draggable={false}
        onLoad={event => {
          if (event.currentTarget.naturalWidth === value.width && event.currentTarget.naturalHeight === value.height) setLoaded(key);
          else {setLoaded(''); setFailed(key);}
        }} onError={() => {setLoaded(''); setFailed(key);}}/>
      {children}
    </div>
    {!ready && <p role="status">{failed === key ? '图片内容或像素尺寸校验失败，不能确认或应用。' : '正在加载并校验真实图像…'}</p>}
    <small>完整图像：{value.source_width} × {value.source_height} px。显示副本：{value.width} × {value.height} px；显示缩放不参与最终裁剪。</small>
  </div>;
}
