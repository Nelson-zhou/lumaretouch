/** Optional empty-state layout diagnostics; observes UI, owns no application state. */
import {useEffect} from 'react';
import {m0Env,report} from '../native';
export function useEmptyStateProbe(hasImage:boolean){
  // 空状态自证（1.10.0 收官）：没有图时，视口中央那张卡片是不是真的画出来了、
  // 是不是在容器里居中、顶栏那颗按钮的字对不对。浏览器预览只能证明 React 树，
  // "装上去的这一件"要靠真窗口答；判据在 m5 第 11 臂里（$LRT_AUTO_EMPTY）。
  useEffect(() => {
    if (hasImage) return;
    let dead = false;
    void (async () => {
      const env = await m0Env().catch(() => null);
      if (dead || !env?.auto_empty) return;
      // 两帧之后再量：首帧还在布局，量到的矩形可能是 0
      await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
      const card = document.querySelector(".emptyCard") as HTMLElement | null;
      const stage = (document.querySelector(".stageBody")
        ?? document.querySelector(".stage")) as HTMLElement | null;
      const btn = document.querySelector(".topbar .openPhoto") as HTMLElement | null;
      const brand = document.querySelector(".topbar .brand") as HTMLElement | null;
      const cr = card?.getBoundingClientRect();
      const sr = stage?.getBoundingClientRect();
      await report(`M0_EMPTY ${JSON.stringify({
        card: !!card,
        title: card?.querySelector(".emptyTitle")?.textContent?.trim() ?? "",
        brand: brand?.textContent?.trim() ?? "",
        openBtn: btn?.textContent?.trim() ?? "",
        // 产品态的三条硬要求：页面上没有调试 HUD；右栏恰好四组；组的标题是那四个词
        hud: !!document.querySelector(".hud"),
        bars: document.querySelectorAll(".gallery .bar").length,
        groups: Array.from(document.querySelectorAll(".side .pg > summary"))
          .map((x) => (x.querySelector("span")?.textContent
            ?? x.textContent ?? "").trim()),
        // 39 族 / 805 项：功能清单的唯一出处是 ui/src/spec/refine.json
        families: Array.from(document.querySelectorAll(".side [data-spec-family]"))
          .map((x) => (x as HTMLElement).dataset.specFamily ?? ""),
        specControls: (document.querySelector(".retouch") as HTMLElement | null)
          ?.dataset.specControls ?? "",
        // 相对所在容器量：.stage 才是视口的容器（顶栏与右栏不归它管）
        dx: cr && sr ? Math.round(cr.left + cr.width / 2 - (sr.left + sr.width / 2)) : null,
        dy: cr && sr ? Math.round(cr.top + cr.height / 2 - (sr.top + sr.height / 2)) : null,
        w: Math.round(cr?.width ?? 0),
        h: Math.round(cr?.height ?? 0),
      })}`);
    })();
    return () => { dead = true; };
    // 只在"没有图"这一档跑一次；有图时不报（那一臂的前提不成立）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasImage]);
}
