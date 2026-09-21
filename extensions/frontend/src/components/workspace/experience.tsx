"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Script from "next/script";

declare global {
  interface Window { WorkspaceMotion?: { mount: (root: HTMLElement, smooth?: boolean) => () => void }; }
}
export function WorkspaceExperience() {
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!ready) return;
    const root = document.getElementById("main-content");
    if (!root) return;
    return window.WorkspaceMotion?.mount(root, pathname !== "/codes");
  }, [pathname, ready]);
  return <>
    <Script src="/workspace-vendor/gsap.min.js" strategy="afterInteractive" onReady={() => {
      // Dependent scripts retain a deterministic order through the local loader.
      const sources = ["/workspace-vendor/ScrollTrigger.min.js", "/workspace-vendor/lenis.min.js", "/workspace-vendor/experience.js"];
      let chain = Promise.resolve();
      for (const src of sources) chain = chain.then(() => new Promise<void>((resolve, reject) => {
        const existing = document.querySelector<HTMLScriptElement>(`script[data-workspace-src="${src}"]`);
        if (existing?.dataset.loaded === "true") { resolve(); return; }
        const script = existing || document.createElement("script");
        script.addEventListener("load", () => { script.dataset.loaded = "true"; resolve(); }, { once: true });
        script.addEventListener("error", () => reject(new Error("motion_asset_unavailable")), { once: true });
        if (!existing) { script.src = src; script.dataset.workspaceSrc = src; document.body.append(script); }
      }));
      chain.then(() => setReady(true)).catch(() => { /* Static UI is complete without motion. */ });
    }} />
  </>;
}
