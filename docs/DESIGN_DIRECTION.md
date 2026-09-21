# White editorial workspace

- Scope: all original administrator routes and the notification-code workspace. Preserve original documents/search/settings/evaluation/monitoring capabilities and backend actors.
- Visual thesis: a white, precise editorial workbench. Oversized Korean task headlines, asymmetrical title/description alignment, black rules, sparse cobalt actions, compact working controls below.
- Focal asset: real semantic typography and actual working tables/forms. No decorative stock media, fake codes, customers, metrics, or avatars.
- Type: system Korean sans; large 48–64px route headlines, 16px explanations, compact 13–14px utilities.
- Sequence: persistent original navigation → task introduction → original working content → status/help. Code workspace: intro → suggested queries → pinned composer → original result cards.
- Motion: local GSAP intro choreography, route transitions, tab and result entrance; CSS for focus/hover. Content starts visible and usable. Reduced motion returns immediately to static final states.
- Scroll: Lenis selected over Locomotive because it fits the existing native overflow container without a transformed page wrapper. One Lenis instance only on the outer long-form main content; no smoothing for chat or nested form controls. GSAP ticker and ScrollTrigger share the loop. Cleanup on route unmount and visibility change.
- Three.js: omitted; spatial imagery does not help users find registered messages or inspect documents.
- Assets: npm-integrity-verified local GSAP/ScrollTrigger/Lenis bundles. Solar interface icons obtained from Iconify, with attribution. No browser CDN dependencies.
- Login: reuse the already implemented CODE_AUTH_MODE=local shared-workspace path from the concurrent integration work. No new login endpoint or password storage is added by this design task. Existing get_current_user resolves the shared DB actor; the existing JWT mode remains available.
- Desktop-first at user request. Existing narrow-window access is retained, without a separate mobile product.
