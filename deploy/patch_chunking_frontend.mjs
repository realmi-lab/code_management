// Label inherited legacy fallback choices and the limits of sentence-based splitting.
import fs from 'node:fs';
import crypto from 'node:crypto';
const path = 'src/components/settings/chunking-form.tsx';
const before = fs.readFileSync(path, 'utf8');
let after = before;
for (const [old,next] of [
 ['<SelectItem value="sentence">Sentence</SelectItem>', '<SelectItem value="sentence" disabled>Sentence (이전 설정 · 실제 Auto detect)</SelectItem>'],
 ['<SelectItem value="token">Token</SelectItem>', '<SelectItem value="token" disabled>Token (이전 설정 · 실제 Auto detect)</SelectItem>'],
 ['          <div className="space-y-2">\n            <Label>청크 크기:', '          <p className="text-sm text-muted-foreground">크기·오버랩은 Auto detect, Section header, Recursive에 적용되며 문장 단위로 근사합니다. Recursive (1024)는 1024/200 고정값을 사용하고 Semantic은 임베딩 유사도로 나눕니다. 저장 후 문서를 재인덱싱해야 반영됩니다.</p>\n          <div className="space-y-2">\n            <Label>청크 크기:'],
]) {
 if (after.split(old).length!==2) throw new Error(`Pinned chunking UI contract changed: ${path}`);
 after=after.replace(old,next);
}
fs.writeFileSync(path,after);
fs.writeFileSync('catalog-chunking-ui-patches.json',JSON.stringify({path,before_sha256:crypto.createHash('sha256').update(before).digest('hex'),after_sha256:crypto.createHash('sha256').update(after).digest('hex')},null,2));
