"""Bound CPU batches and receive raw CE logits; preserve the upstream ranking formula."""
import ast
import hashlib
import json
from pathlib import Path
import sys

TARGET = 'app/services/reranking/korean.py'
BEFORE_SHA256 = '12286fd550969c16a2b4375c680d64e05278d9b37830f5e6048a141cd613311e'
AFTER_SHA256 = 'fc6031bfce413496a6b80f2394f3888029c09d2a10a6075730d7b10e7d67599e'


def apply(root):
    root = Path(root)
    path = root / TARGET
    original_bytes = path.read_bytes()
    before = original_bytes.decode('utf-8')
    current_hash = hashlib.sha256(original_bytes).hexdigest()
    if current_hash not in (BEFORE_SHA256, AFTER_SHA256):
        raise RuntimeError(f'Upstream reranker contract changed: {TARGET}')
    if current_hash == BEFORE_SHA256:
        after = before
        for old, new in (
            ('import math\n', 'import math\nimport torch\n'),
            ('raw_scores = self.model.predict(pairs)',
             'raw_scores = self.model.predict(pairs, activation_fn=torch.nn.Identity(), batch_size=4)'),
        ):
            if after.count(old) != 1:
                raise RuntimeError(f'Upstream reranker contract changed: {TARGET}')
            after = after.replace(old, new)
        ast.parse(after)
        if hashlib.sha256(after.encode()).hexdigest() != AFTER_SHA256:
            raise RuntimeError(f'Unexpected reranker patch output: {TARGET}')
        path.write_text(after)
    records = [{'path': TARGET, 'before_sha256': BEFORE_SHA256, 'after_sha256': AFTER_SHA256,
                'reason': 'CrossEncoder.predict returns logits for one sigmoid; batch_size=4 bounds CPU memory without dropping candidates'}]
    (root / 'catalog-reranker-patches.json').write_text(json.dumps(records, indent=2) + '\n')
    return records


if __name__ == '__main__':
    apply(sys.argv[1] if len(sys.argv) > 1 else '/app')
