// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef} from 'react';
import {imageUrl, type NeckImage} from './model';

/** Called only with hash-verified PNGs. Decode + visible pixels are necessary,
 * not user consent and not proof of whole-image photographic acceptance. */
export function NeckReviewedImage({image, identity, alt, nativePixels = false, onSeen, onError}: {
  image: NeckImage; identity: string; alt: string; nativePixels?: boolean; onSeen: () => void; onError: () => void;
}) {
  const element = useRef<HTMLImageElement>(null), check = useRef<() => void>(() => {});
  const latest = useRef({identity, onSeen, onError}); latest.current = {identity, onSeen, onError};
  useLayoutEffect(() => {
    const node = element.current; if (!node) return;
    let active = true;
    const inspect = () => {
      if (!active || latest.current.identity !== identity || !node.complete || document.visibilityState !== 'visible') return;
      if (node.naturalWidth !== image.width || node.naturalHeight !== image.height) {
        if (node.naturalWidth || node.naturalHeight) latest.current.onError();
        return;
      }
      for (let parent: HTMLElement | null = node; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0) return;
      }
      const rect = node.getBoundingClientRect();
      if (node.getClientRects().length && rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.bottom > 0
        && rect.left < window.innerWidth && rect.top < window.innerHeight) latest.current.onSeen();
    };
    check.current = inspect;
    const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(inspect) : null;
    observer?.observe(node); document.addEventListener('visibilitychange', inspect);
    window.addEventListener('scroll', inspect, true); window.addEventListener('resize', inspect); inspect();
    return () => {active = false; check.current = () => {}; observer?.disconnect();
      document.removeEventListener('visibilitychange', inspect); window.removeEventListener('scroll', inspect, true); window.removeEventListener('resize', inspect);};
  }, [identity, image.sha256, image.width, image.height, nativePixels]);
  return <img key={identity} ref={element} src={imageUrl(image)} alt={alt} draggable={false}
    style={{display: 'block', width: nativePixels ? image.width : '100%', maxWidth: nativePixels ? 'none' : '100%', height: nativePixels ? image.height : 'auto'}}
    onLoad={() => check.current()} onError={() => {if (latest.current.identity === identity) latest.current.onError();}}/>;
}
