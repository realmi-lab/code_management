"""Verify the vendored module's pinned local checksum."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
manifest=json.loads((root/'vendor'/'urstory_rag'/'provenance.json').read_text())
for path,digest in manifest['bundled_sha256'].items():
    actual=hashlib.sha256((root/path).read_bytes()).hexdigest()
    if actual!=digest:raise SystemExit('Checksum mismatch: '+path)
print('Vendor checksums verified. Source commit:',manifest['upstream_commit'])
