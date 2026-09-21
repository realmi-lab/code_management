import fs from 'node:fs';
if(fs.readFileSync('src/app/documents/page.tsx','utf8').includes('CatalogPanel'))throw new Error('Catalog surface already patched');
function patch(path,before,after){const s=fs.readFileSync(path,'utf8');if(s.split(before).length!==2)throw new Error('Pinned catalogue surface contract changed: '+path);fs.writeFileSync(path,s.replace(before,after));}
patch('src/lib/api.ts','async function fetchJSON<T>(', 'export async function fetchJSON<T>(');
for(const [path,mode] of [['src/app/documents/page.tsx',''],['src/app/search/page.tsx',' search']]){
 patch(path,'"use client";','"use client";\nimport { CatalogPanel } from "@/components/catalog/catalog-panel";');
 patch(path,'    <div className="space-y-6">','    <div className="space-y-6">\n      <CatalogPanel'+mode+' />');
}
