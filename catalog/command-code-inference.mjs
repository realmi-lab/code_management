// Narrow inference-only mode: reuse Command Code authentication without coding tools.
export default function (cmd) {
  cmd.setActiveTools([]);
  cmd.hooks({
    appendSystemPrompt() {
      return 'This is a Korean notification catalog inference request (search queries or wording). Use only the supplied data. ' +
        'Do not access files, use tools, generate identifiers, or change business conditions. ' +
        'Keep reasoning brief and return only the requested JSON object.';
    }
  });
}
