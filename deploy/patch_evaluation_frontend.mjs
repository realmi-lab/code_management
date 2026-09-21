// Missing measurements are not zero. Patch only the verified build copy.
import fs from 'node:fs';
import crypto from 'node:crypto';
const edits = [];
const helper = `function measured(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
function metricText(value: unknown, percent = false): string {
  return measured(value) ? (value * 100).toFixed(1) + (percent ? "%" : "") : "미측정";
}

`;
function patch(path, replacements, marker) {
  const before = fs.readFileSync(path, 'utf8');
  let after = before;
  for (const [old, next] of [...replacements, [marker, helper + marker]]) {
    if (after.split(old).length !== 2) throw new Error(`Pinned evaluation UI contract changed: ${path}`);
    after = after.replace(old, next);
  }
  edits.push({path,before,after});
}
const replacements = [];
for (const key of ['faithfulness','answer_relevancy','context_precision','context_recall']) {
  replacements.push([
    `{((run.metrics.${key} ?? 0) * 100).toFixed(1)}%`, `{metricText(run.metrics.${key}, true)}`
  ], [
    `{((r.${key} ?? 0) * 100).toFixed(1)}`, `{metricText(r.${key})}`
  ], [
    `{run.metrics ? ((run.metrics.${key} ?? 0) * 100).toFixed(1) : "-"}`, `{metricText(run.metrics?.${key})}`
  ]);
}
patch('src/app/evaluation/runs/page.tsx', replacements, 'function RunDetailDialog(');
patch('src/app/evaluation/compare/page.tsx', [
  ['const val1 = comparison.run1.metrics?.[metric as keyof typeof comparison.run1.metrics] ?? 0;', 'const val1 = comparison.run1.metrics?.[metric as keyof typeof comparison.run1.metrics];'],
  ['const val2 = comparison.run2.metrics?.[metric as keyof typeof comparison.run2.metrics] ?? 0;', 'const val2 = comparison.run2.metrics?.[metric as keyof typeof comparison.run2.metrics];'],
  ['const diff = comparison.diff[metric] ?? 0;', 'const diff = measured(val1) && measured(val2) ? comparison.diff[metric] : undefined;'],
  ['const isPositive = diff > 0;', 'const isPositive = measured(diff) && diff > 0;'],
  ['A: {(val1 * 100).toFixed(1)}%', 'A: {metricText(val1, true)}'],
  ['B: {(val2 * 100).toFixed(1)}%', 'B: {metricText(val2, true)}'],
  ['isPositive ? "text-green-600 border-green-200" : "text-red-600 border-red-200",', '!measured(diff) ? "text-muted-foreground" : isPositive ? "text-green-600 border-green-200" : "text-red-600 border-red-200",'],
  ['{isPositive ? "+" : ""}{(diff * 100).toFixed(1)}%', '{isPositive ? "+" : ""}{metricText(diff, true)}'],
], 'export default function ComparePage()');
for (const edit of edits) fs.writeFileSync(edit.path, edit.after);
fs.writeFileSync('catalog-evaluation-patches.json', JSON.stringify(edits.map(({path,before,after}) => ({path,
  before_sha256: crypto.createHash('sha256').update(before).digest('hex'),
  after_sha256: crypto.createHash('sha256').update(after).digest('hex')})), null, 2));
