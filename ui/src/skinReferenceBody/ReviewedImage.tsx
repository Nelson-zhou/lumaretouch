// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef} from 'react';
import type {SpillImage} from '../spillRemoval/model';

/** This operation's local presentation state only. Verified PNG bytes still need
 * browser decoding and visible presentation; seeing never grants user consent. */
export function ReviewedImage({image, identity, alt, onSeen, onError}: {image: SpillImage; identity: string; alt: string;
  onSeen: () => void; onError: () => void}) {
  const element = useRef<HTMLImageElement>(null), callbacks = useRef({onSeen, onError});
  callbacks.current = {onSeen, onError};
  const check = useRef<() => void>(() => {});
  useLayoutEffect(() => {
    const node = element.current; if (!node) return;
    let live = true;
    function inspect() {
      if (!live || !node || !node.complete || document.visibilityState !== 'visible') return;
      if (node.naturalWidth !== image.width || node.naturalHeight !== image.height) {
        // An incomplete browser request has naturalWidth=0; onError owns that failure.
        if (node.naturalWidth || node.naturalHeight) callbacks.current.onError();
        return;
      }
      const rect = node.getBoundingClientRect();
      // Layout alone is insufficient when a collapsed/tabbed ancestor hides paint.
      for (let parent: HTMLElement | null = node; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        if (style.visibility === 'hidden' || style.visibility === 'collapse' || style.display === 'none' || Number(style.opacity) === 0) return;
      }
      if (node.getClientRects().length && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0
        && rect.top < window.innerHeight && rect.left < window.innerWidth) callbacks.current.onSeen();
    }
    check.current = inspect;
    const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(inspect) : null;
    observer?.observe(node);
    document.addEventListener('visibilitychange', inspect);
    window.addEventListener('scroll', inspect, true); window.addEventListener('resize', inspect);
    inspect();
    return () => {live = false; check.current = () => {}; observer?.disconnect();
      document.removeEventListener('visibilitychange', inspect);
      window.removeEventListener('scroll', inspect, true); window.removeEventListener('resize', inspect);};
  }, [identity, image.width, image.height, image.sha256]);
  return <img ref={element} alt={alt} src={`data:image/png;base64,${image.base64}`}
    style={{display: 'block', width: '100%', height: 'auto'}}
    onLoad={() => check.current()} onError={() => callbacks.current.onError()}/>;
}
