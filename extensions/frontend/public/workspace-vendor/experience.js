/* Local motion layer. Semantic content remains visible when this script is unavailable. */
(() => {
  'use strict';
  const g = window.gsap, st = window.ScrollTrigger;
  if (!g || !st) return;
  g.registerPlugin(st);
  window.WorkspaceMotion = {
    mount(root, smooth = false) {
      const media = g.matchMedia();
      root.classList.add('motion-enhanced');
      media.add('(prefers-reduced-motion: no-preference)', () => {
        let lenis = null, ticker = null, disposed = false;
        const seen = new WeakSet();
        const timelines = new Set();
        const animate = () => {
          if (disposed || document.hidden) return;
          const items = [...root.querySelectorAll('.workspace-kicker, .hero-word, .workspace-intro-aside, .welcome-heading>p, .welcome>p, .workflow-note, .example, .bubble, .result-group .card')].filter(e => !seen.has(e) && e.getClientRects().length);
          if (!items.length) return;
          items.forEach(e => seen.add(e));
          const tl = g.timeline({onComplete: () => timelines.delete(tl)});
          timelines.add(tl);
          tl.from(items, {y: 18, opacity: .5, duration: .65, stagger: .055, ease: 'power3.out', clearProps: 'transform,opacity'});
        };
        const context = g.context(() => {
          animate();
          root.querySelectorAll('.workspace-rule').forEach(rule => g.from(rule, {
            scaleX: .65, duration: .9, ease: 'power3.out', clearProps: 'transform',
            scrollTrigger: {trigger: rule, scroller: root, start: 'top 95%', once: true}
          }));
        }, root);
        if (smooth && window.Lenis) {
          const content = root.querySelector('.workspace-content');
          if (content) {
            lenis = new window.Lenis({wrapper: root, content, duration: .65, autoRaf: false, smoothWheel: true, syncTouch: false, prevent: node => !!node.closest('textarea, select, [role="dialog"], [data-lenis-prevent]')});
            lenis.on('scroll', st.update);
            ticker = time => lenis.raf(time * 1000);
            g.ticker.add(ticker);
            g.ticker.lagSmoothing(0);
          }
        }
        let scheduled = 0;
        const observer = new MutationObserver(() => {
          if (scheduled) return;
          scheduled = requestAnimationFrame(() => { scheduled = 0; animate(); st.refresh(); });
        });
        observer.observe(root, {childList: true, subtree: true, attributes: true, attributeFilter: ['hidden']});
        const refresh = () => { if (!disposed) { lenis?.resize(); st.refresh(); } };
        document.fonts?.ready.then(refresh);
        root.addEventListener('load', refresh, true);
        const visibility = () => {
          if (document.hidden) { if(ticker)g.ticker.remove(ticker); lenis?.stop(); timelines.forEach(t => t.pause()); }
          else { if(ticker)g.ticker.add(ticker); lenis?.start(); timelines.forEach(t => t.resume()); refresh(); animate(); }
        };
        document.addEventListener('visibilitychange', visibility);
        return () => {
          disposed = true;
          observer.disconnect(); cancelAnimationFrame(scheduled);
          root.removeEventListener('load', refresh, true);
          document.removeEventListener('visibilitychange', visibility);
          if (ticker) g.ticker.remove(ticker);
          lenis?.destroy();
          timelines.forEach(t => { t.progress(1); t.kill(); }); timelines.clear();
          context.revert();
        };
      });
      return () => { media.revert(); root.classList.remove('motion-enhanced'); };
    }
  };
})();
