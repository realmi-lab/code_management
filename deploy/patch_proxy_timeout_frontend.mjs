// Match the pinned Next proxy to the catalogue API's 240 second request budget.
import fs from 'node:fs';
import crypto from 'node:crypto';
const path='next.config.ts';
const before=fs.readFileSync(path,'utf8');
const marker='  output: "standalone",';
if(before.split(marker).length!==2 || before.includes('experimental:'))throw new Error('Pinned Next proxy configuration changed; build stopped.');
const after=before.replace(marker,marker+'\n  experimental: { proxyTimeout: 300_000 },');
fs.writeFileSync(path,after);
console.log(JSON.stringify({patch:'catalogue-proxy-timeout',file:path,before:crypto.createHash('sha256').update(before).digest('hex'),after:crypto.createHash('sha256').update(after).digest('hex')}));
