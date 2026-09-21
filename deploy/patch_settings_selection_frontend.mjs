import fs from 'node:fs';
import crypto from 'node:crypto';

// Radix can emit an empty native-select value while async form values settle.
// Empty values are not valid selections and must not replace persisted choices.
const specs = [
  ['search-form.tsx', [
    ['onValueChange={(v) => form.setValue("mode", v as SearchFormData["mode"])}',
      'onValueChange={(v) => { if (v) form.setValue("mode", v as SearchFormData["mode"]); }}'],
    ['onValueChange={(v) => form.setValue("keyword_engine", v)}',
      'onValueChange={(v) => { if (v) form.setValue("keyword_engine", v); }}'],
  ]],
  ['chunking-form.tsx', [
    ['onValueChange={(v) => form.setValue("strategy", v)}',
      'onValueChange={(v) => { if (v) form.setValue("strategy", v); }}'],
    ['                <SelectItem value="recursive">Recursive</SelectItem>',
      '                <SelectItem value="auto">Auto detect</SelectItem>\n' +
      '                <SelectItem value="header">Section header</SelectItem>\n' +
      '                <SelectItem value="recursive">Recursive</SelectItem>\n' +
      '                <SelectItem value="recursive_1024">Recursive (1024)</SelectItem>\n' +
      '                <SelectItem value="semantic">Semantic</SelectItem>'],
  ]],
];
const changes = specs.map(([filename, replacements]) => {
  const path = `src/components/settings/${filename}`;
  const before = fs.readFileSync(path, 'utf8');
  let after = before;
  for (const [old, next] of replacements) {
    if (after.split(old).length !== 2) throw new Error(`Pinned settings selection UI contract changed: ${path}`);
    after = after.replace(old, next);
  }
  return {path, before, after};
});
for (const {path, after} of changes) fs.writeFileSync(path, after);
fs.writeFileSync('catalog-settings-selection-patches.json', JSON.stringify(changes.map(({path, before, after}) => ({
  path,
  before_sha256: crypto.createHash('sha256').update(before).digest('hex'),
  after_sha256: crypto.createHash('sha256').update(after).digest('hex'),
})), null, 2));
