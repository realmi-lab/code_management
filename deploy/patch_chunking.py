"""Connect saved chunking parameters in the pinned build copy, without inference."""
import ast
import hashlib
import json
from pathlib import Path
import sys


def apply(root):
    root = Path(root)
    edits = []
    def patch(path, pairs):
        before = (root/path).read_text()
        after = before
        for old, new in pairs:
            if after.count(old) != 1:
                raise RuntimeError(f'Upstream chunking contract changed: {path}')
            after = after.replace(old, new)
        ast.parse(after)
        edits.append((path, before, after))
    patch('app/tasks/indexing.py', [
        ('        chunking_strategy=rag_settings.chunking_strategy,',
         '        chunking_strategy=rag_settings.chunking_strategy,\n        chunk_size=rag_settings.chunk_size,\n        chunk_overlap=rag_settings.chunk_overlap,'),
    ])
    patch('app/services/document/processor.py', [
        ('        contextual_chunking_max_doc_chars: int = 2000,',
         '        contextual_chunking_max_doc_chars: int = 2000,\n        chunk_size: int = 512,\n        chunk_overlap: int = 50,'),
        ('        self.chunking_strategy = chunking_strategy',
         '        self.chunking_strategy = chunking_strategy\n        self.chunk_size = chunk_size\n        self.chunk_overlap = chunk_overlap'),
        ('"recursive": lambda: RecursiveChunking(),',
         '"recursive": lambda: RecursiveChunking(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap),'),
        ('"header": lambda: SectionHeaderChunking(chunk_size=1024, chunk_overlap=200),',
         '"header": lambda: SectionHeaderChunking(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap),'),
        ('            "auto": lambda: AutoDetectChunking(\n',
         '            "auto": lambda: AutoDetectChunking(\n                chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap,\n'),
        ('            ) if self.embedder else AutoDetectChunking(),',
         '            ) if self.embedder else AutoDetectChunking(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap),'),
    ])
    patch('app/services/chunking/auto_detect.py', [
        ('        max_doc_chars: int = 2000,',
         '        max_doc_chars: int = 2000,\n        chunk_size: int = 1024,\n        chunk_overlap: int = 200,'),
        ('        self.max_doc_chars = max_doc_chars',
         '        self.max_doc_chars = max_doc_chars\n        self.chunk_size = chunk_size\n        self.chunk_overlap = chunk_overlap'),
        ('return SectionHeaderChunking(chunk_size=1024, chunk_overlap=200)',
         'return SectionHeaderChunking(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)'),
        ('return RecursiveChunking(chunk_size=1024, chunk_overlap=200)',
         'return RecursiveChunking(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)'),
    ])
    patch('app/services/chunking/recursive.py', [
        ('        split_overlap = max(1, split_length // 3)',
         '        split_overlap = min(split_length - 1, max(0, round(self.chunk_overlap / max(1, self.chunk_size) * split_length)))'),
    ])
    for path, _, after in edits:
        (root/path).write_text(after)
    records = [dict(path=path, before_sha256=hashlib.sha256(before.encode()).hexdigest(),
                    after_sha256=hashlib.sha256(after.encode()).hexdigest()) for path,before,after in edits]
    (root/'catalog-chunking-patches.json').write_text(json.dumps(records, indent=2))
    return records

if __name__ == '__main__': apply(sys.argv[1] if len(sys.argv)>1 else '/app')
