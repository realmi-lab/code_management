(() => {
  let cleanup;
  const mount = () => { cleanup?.(); cleanup = window.WorkspaceMotion?.mount(document.getElementById('app'), false); };
  mount();
  window.addEventListener('pagehide', () => { cleanup?.(); cleanup = null; });
  window.addEventListener('pageshow', event => { if (event.persisted) mount(); });
})();
