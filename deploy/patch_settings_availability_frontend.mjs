import fs from 'node:fs';
import crypto from 'node:crypto';

// Validate every pinned source contract before writing any changed file.
const anchor = '        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">';
const notices = [
  ['search-form.tsx', '현재 임베딩이 연결되지 않아 실제 검색은 키워드 방식으로 실행하며 멀티쿼리는 실행하지 않습니다. 선택한 검색 모드와 멀티쿼리 설정은 저장됩니다. 임베딩 연결과 문서 재인덱싱 후 저장한 설정을 사용합니다.'],
  ['hyde-form.tsx', '현재 임베딩이 연결되지 않아 키워드 검색을 사용하며 HyDE는 실행하지 않습니다. HyDE 설정은 저장되며, 임베딩 연결과 문서 재인덱싱 후 적용됩니다.'],
  ['chunking-form.tsx', '현재 임베딩이 연결되지 않아 검색은 키워드 방식으로 실행합니다. 시맨틱 청킹을 선택해도 설정은 저장하고 실제 청킹에는 자동 전략을 사용합니다. 시맨틱 청킹은 임베딩 연결 후 문서를 재인덱싱할 때 적용되며, 다른 청킹 전략은 현재 사용할 수 있습니다.'],
];
const changes = notices.map(([filename, message]) => {
  const path = `src/components/settings/${filename}`;
  const before = fs.readFileSync(path, 'utf8');
  if (before.split(anchor).length !== 2 || before.includes('data-embedding-availability')) {
    throw new Error(`Pinned settings availability UI contract changed: ${path}`);
  }
  const notice = `${anchor}
          {settings?.embedding_provider === "none" && (
            <p role="status" data-embedding-availability="${filename.replace('-form.tsx', '')}" className="rounded-md border p-3 text-sm text-muted-foreground">
              ${message}
            </p>
          )}`;
  return {path, before, after: before.replace(anchor, notice)};
});
for (const {path, after} of changes) fs.writeFileSync(path, after);
fs.writeFileSync('catalog-settings-availability-patches.json', JSON.stringify(changes.map(({path, before, after}) => ({
  path,
  before_sha256: crypto.createHash('sha256').update(before).digest('hex'),
  after_sha256: crypto.createHash('sha256').update(after).digest('hex'),
})), null, 2));
