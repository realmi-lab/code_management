// Preserve upstream sources; validate all contracts before writing build copies.
import fs from 'node:fs';
import crypto from 'node:crypto';
const edits = [];
function patch(path, replacements) {
  const before = fs.readFileSync(path, 'utf8');
  let after = before;
  for (const [old, next] of replacements) {
    if (after.split(old).length !== 2) throw new Error(`Pinned watcher UI contract changed: ${path}`);
    after = after.replace(old, next);
  }
  edits.push({path, before, after});
}
patch('src/lib/api.ts', [[`    start: (directories?: string[], usePolling?: boolean) =>
      fetchJSON<WatcherActionResponse>(\`/api/watcher/start\${buildQueryString({
        directories: undefined,
        use_polling: usePolling,
      })}\`, {
        method: "POST",
        params: { ...(directories ? { directories: directories.join(",") } : {}), ...(usePolling ? { use_polling: "true" } : {}) },
      }),`, `    start: (directories: string[], usePolling = false) => {
      const params = new URLSearchParams();
      for (const directory of directories) params.append("directories", directory);
      params.set("use_polling", String(usePolling));
      return fetchJSON<WatcherActionResponse>(\`/api/watcher/start?\${params.toString()}\`, { method: "POST" });
    },`]]);
patch('src/lib/queries.ts', [[
  '    mutationFn: () => api.watcher.start(),',
  '    mutationFn: (options: { directories: string[]; usePolling: boolean }) => api.watcher.start(options.directories, options.usePolling),',
]]);
patch('src/components/settings/watcher-form.tsx', [
  ['import { useForm, useFieldArray }', 'import { useEffect } from "react";\nimport { useForm, useFieldArray }'],
  ['  const onSubmit = async (_data: WatcherFormData) => {\n    // 감시 설정은 별도 watcher API(start/stop/scan)로 관리됩니다.\n    // settings API와 연결되지 않으므로 저장은 동작하지 않습니다.\n    toast.info("감시 설정은 시작/중지 버튼으로 제어하세요.");\n  };',
   '  useEffect(() => {\n    if (watcherStatus?.running && watcherStatus.directories?.length) {\n      form.setValue("directories", watcherStatus.directories.map((value) => ({ value })));\n    }\n  }, [watcherStatus?.running, JSON.stringify(watcherStatus?.directories)]);\n\n  const onSubmit = async () => { await handleStart(); };'],
  ['      await startMutation.mutateAsync();', '      const directories = form.getValues("directories").map(({ value }) => value.trim()).filter(Boolean);\n      if (!directories.length) { toast.error("감시할 컨테이너 디렉토리를 입력하세요."); return; }\n      await startMutation.mutateAsync({ directories, usePolling: form.getValues("use_polling") });'],
  ['      await scanMutation.mutateAsync();\n      toast.success("수동 스캔이 시작되었습니다.");', '      const result = await scanMutation.mutateAsync();\n      toast.info(`지원 파일 ${result.scanned_files}개를 확인했습니다. 이 작업은 인덱싱을 실행하지 않습니다.`);'],
  ['              <Label>감시 활성화</Label>', '              <Label>감시 활성화 (시작/중지 버튼으로 제어)</Label>'],
  ['                checked={form.watch("enabled")}', '                disabled\n                checked={watcherStatus?.running ?? false}'],
  ['                <Label>폴링 간격: {pollingInterval}초</Label>', '                <Label>폴링 간격: 서버 기본값 5초 (변경 미지원)</Label>'],
  ['                  value={[pollingInterval]}', '                  disabled\n                  value={[5]}'],
  ['                checked={form.watch("auto_delete")}', '                disabled\n                checked={false}'],
  ['                  원본 파일 삭제 시 인덱스에서도 자동 제거', '                  원본의 삭제 작업자 연동은 아직 구현되지 않았습니다.'],
  ['              <div className="flex items-center justify-between">\n                <Label>파일 패턴</Label>', '              <div className="flex items-center justify-between">\n                <Label>파일 패턴 (서버 고정: PDF, DOCX, TXT, MD)</Label>'],
  ['                  onClick={() => patternFields.append({ value: "" })}', '                  disabled\n                  onClick={() => patternFields.append({ value: "" })}'],
  ['                    {...form.register(`file_patterns.${index}.value`)}', '                    disabled\n                    {...form.register(`file_patterns.${index}.value`)}'],
  ['                    onClick={() => patternFields.remove(index)}', '                    disabled\n                    onClick={() => patternFields.remove(index)}'],
  ['            <Button type="submit" disabled={updateMutation.isPending}>', '            <p className="text-sm text-muted-foreground">컨테이너에서 접근 가능한 경로를 입력하세요. 하위 폴더도 감시합니다. 설정은 서버에 영구 저장되지 않습니다. 원본 파일 감지 작업자의 DB·인덱싱 연결은 아직 미구현입니다.</p>\n            <Button type="submit" disabled={startMutation.isPending || watcherStatus?.running}>'],
  ['              {updateMutation.isPending ? "저장 중..." : "저장"}', '              {startMutation.isPending ? "시작 중..." : "입력한 설정으로 시작"}'],
]);
for (const edit of edits) fs.writeFileSync(edit.path, edit.after);
fs.writeFileSync('catalog-watcher-patches.json', JSON.stringify(edits.map(({path,before,after}) => ({path,
  before_sha256: crypto.createHash('sha256').update(before).digest('hex'),
  after_sha256: crypto.createHash('sha256').update(after).digest('hex')})), null, 2));
