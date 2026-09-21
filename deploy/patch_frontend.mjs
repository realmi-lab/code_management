// Group navigation in the build copy while preserving every upstream page.
import fs from 'node:fs';
const filename='src/components/layout/sidebar.tsx';
let source=fs.readFileSync(filename,'utf8');
const marker='  { href: "/search", label: "검색 테스트", icon: Search },';
if(source.split(marker).length!==2)throw new Error('Pinned sidebar contract changed; build stopped.');
source=source.replace(marker,marker+'\n  { href: "/codes", label: "알림 코드", icon: FileText },');
function replaceOnce(before, after) {
  if (source.split(before).length !== 2) throw new Error('Pinned sidebar grouping contract changed; build stopped.');
  source = source.replace(before, after);
}
replaceOnce('      {navItems.map((item) => {', '      {navItems.filter((item) => item.href === "/codes").map(renderItem)}\n      <details className="admin-navigation" open>\n        <summary className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium">\n          <Settings className="h-4 w-4" aria-hidden="true" />\n          관리자\n        </summary>\n        <div className="admin-navigation-items">\n          {navItems.filter((item) => item.href !== "/codes").map(renderItem)}\n        </div>\n      </details>');
const start = source.indexOf('        const Icon = item.icon;');
const end = source.indexOf('      })}', start);
if (start < 0 || end < 0) throw new Error('Pinned sidebar item contract changed; build stopped.');
const renderBody = source.slice(start, end);
source = source.slice(0, start) + source.slice(end + '      })}'.length);
replaceOnce('  return (\n    <nav', '  function renderItem(item: (typeof navItems)[number]) {\n' + renderBody + '  }\n\n  return (\n    <nav');
fs.writeFileSync(filename,source);
