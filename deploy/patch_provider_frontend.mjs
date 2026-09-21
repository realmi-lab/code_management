import fs from 'node:fs';
import crypto from 'node:crypto';
const path = 'src/components/settings/generation-form.tsx';
const before = fs.readFileSync(path, 'utf8');
let result = before;
function replace(old, next) {
  if (result.split(old).length !== 2) throw new Error(`Pinned provider UI contract changed: ${path}`);
  result = result.replace(old, next);
}
replace('              value={form.watch("provider")}',
        '              disabled={Boolean(settings?.llm_provider)}\n              value={form.watch("provider")}');
replace('                <SelectItem value="openai">OpenAI</SelectItem>',
        '                <SelectItem value="openai">OpenAI</SelectItem>\n                <SelectItem value="commandcode">DeepSeek (Command Code)</SelectItem>\n                <SelectItem value="deepseek">DeepSeek</SelectItem>');
replace('              {...form.register("model")}',
        '              readOnly={Boolean(settings?.llm_provider)}\n              {...form.register("model")}');
replace('            <Label>모델</Label>',
        '            <Label>모델</Label>\n            {Boolean(settings?.llm_provider) && <p className="text-sm text-muted-foreground">AI 공급자·모델·키는 알림 코드 → AI 설정에서 선택할 수 있습니다.</p>}');
fs.writeFileSync(path, result);
fs.writeFileSync('catalog-provider-patches.json', JSON.stringify({path,
  before_sha256: crypto.createHash('sha256').update(before).digest('hex'),
  after_sha256: crypto.createHash('sha256').update(result).digest('hex')}, null, 2));

const embeddingPath = 'src/components/settings/embedding-form.tsx';
const embeddingBefore = fs.readFileSync(embeddingPath, 'utf8');
let embeddingAfter = embeddingBefore;
for (const [old, next] of [
  ['              value={form.watch("provider")}', '              disabled={Boolean(settings?.embedding_provider)}\n              value={form.watch("provider")}'],
  ['                <SelectItem value="openai">OpenAI</SelectItem>', '                <SelectItem value="openai">OpenAI</SelectItem>\n                <SelectItem value="local">이 Mac · 로컬 임베딩</SelectItem>\n                <SelectItem value="none">임베딩 없이 키워드 검색</SelectItem>'],
  ['              {...form.register("model")}', '              readOnly={Boolean(settings?.embedding_provider)}\n              {...form.register("model")}'],
  ['            <Label>모델</Label>', '            <Label>모델</Label>\n            {Boolean(settings?.embedding_provider) && <p className="text-sm text-muted-foreground">검색 방식은 알림 코드 → AI 설정에서 선택할 수 있습니다. 키워드 검색은 임베딩이 필요 없습니다.</p>}'],
]) {
  if (embeddingAfter.split(old).length !== 2) throw new Error(`Pinned embedding UI contract changed: ${embeddingPath}`);
  embeddingAfter = embeddingAfter.replace(old, next);
}
fs.writeFileSync(embeddingPath, embeddingAfter);
fs.writeFileSync('catalog-embedding-patches.json', JSON.stringify({path: embeddingPath,
  before_sha256: crypto.createHash('sha256').update(embeddingBefore).digest('hex'),
  after_sha256: crypto.createHash('sha256').update(embeddingAfter).digest('hex')}, null, 2));
