"""Pinned-source transform and scoring contract; no model weights or providers."""
import ast
import asyncio
from dataclasses import dataclass, replace
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('reranker_patch', ROOT / 'deploy/patch_reranker.py')
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


@dataclass
class Document:
    content: str
    score: float = 0.0

    def model_copy(self, update):
        return replace(self, **update)


class Identity:
    def __call__(self, value):
        return value


class CrossEncoder:
    """Installed default: predict applies sigmoid unless an activation is passed."""
    def __init__(self, model_name):
        self.calls = []

    def predict(self, pairs, activation_fn=None, batch_size=32):
        self.calls.append((activation_fn, batch_size, pairs))
        activation = activation_fn or (lambda value: 1 / (1 + math.exp(-value)))
        return [activation(value) for value in (-8.0, 0.0, 8.0)][:len(pairs)]


class RerankerPatch(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / PATCH.TARGET
        self.path.parent.mkdir(parents=True)
        shutil.copy(ROOT / 'upstream/backend' / PATCH.TARGET, self.path)

    def load_patched_class(self):
        PATCH.apply(self.root)
        source = ast.parse(self.path.read_text())
        nodes = [node for node in source.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
        scope = {'math': math, 'torch': SimpleNamespace(nn=SimpleNamespace(Identity=Identity)),
                 'CrossEncoder': CrossEncoder, 'SearchResult': Document}
        exec('from __future__ import annotations\n' + '\n'.join(ast.unparse(node) for node in nodes), scope)
        return scope['KoreanCrossEncoder']()

    def test_calibrated_scores_apply_exactly_one_sigmoid_to_raw_logits(self):
        model = self.load_patched_class()
        documents = [Document(str(value)) for value in (-8, 0, 8)]
        ranked = asyncio.run(model.rerank('query', documents, top_k=3, alpha=0.7))
        self.assertEqual([doc.content for doc in ranked], ['8', '0', '-8'])
        for rank, (doc, logit) in enumerate(zip(ranked, (8, 0, -8)), 1):
            expected = 0.7 / (1 + math.exp(-logit)) + 0.3 / rank
            self.assertAlmostEqual(doc.score, expected, places=12)
        self.assertIsInstance(model.model.calls[0][0], Identity)
        # The runtime batch is smaller; every candidate and upstream prefix is retained.
        self.assertEqual(model.model.calls[0][1], 4)
        self.assertEqual(len(model.model.calls[0][2]), 3)
        # Zero evidence is 0.5 probability, not sigmoid(0.5).
        self.assertAlmostEqual(ranked[1].score, 0.5, places=12)

    def test_replace_mode_returns_raw_logits(self):
        model = self.load_patched_class()
        ranked = asyncio.run(model.rerank('query', [Document('a'), Document('b'), Document('c')],
                                          top_k=3, score_mode='replace'))
        self.assertEqual([doc.score for doc in ranked], [8.0, 0.0, -8.0])

    def test_repeat_is_idempotent_and_records_original_and_output_hashes(self):
        original = self.path.read_bytes()
        first = PATCH.apply(self.root)
        patched = self.path.read_bytes()
        manifest = (self.root / 'catalog-reranker-patches.json').read_bytes()
        self.assertEqual(PATCH.apply(self.root), first)
        self.assertEqual(self.path.read_bytes(), patched)
        self.assertEqual((self.root / 'catalog-reranker-patches.json').read_bytes(), manifest)
        self.assertEqual(hashlib.sha256(original).hexdigest(), PATCH.BEFORE_SHA256)
        self.assertEqual(hashlib.sha256(patched).hexdigest(), PATCH.AFTER_SHA256)
        self.assertEqual(json.loads(manifest)[0]['before_sha256'], PATCH.BEFORE_SHA256)

    def test_any_pinned_source_drift_is_rejected_before_writing(self):
        self.path.write_text(self.path.read_text().replace('max_chars = 512', 'max_chars = 511'))
        drifted = self.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'contract changed'):
            PATCH.apply(self.root)
        self.assertEqual(self.path.read_bytes(), drifted)
        self.assertFalse((self.root / 'catalog-reranker-patches.json').exists())

    def test_modified_patched_source_is_not_mistaken_for_idempotent_success(self):
        PATCH.apply(self.root)
        self.path.write_text(self.path.read_text() + '\n# unexpected edit\n')
        with self.assertRaisesRegex(RuntimeError, 'contract changed'):
            PATCH.apply(self.root)

    def test_docker_build_executes_patch(self):
        dockerfile = (ROOT / 'deploy/backend.Dockerfile').read_text()
        self.assertIn('COPY deploy/patch_reranker.py /tmp/patch_reranker.py', dockerfile)
        self.assertIn('RUN python /tmp/patch_reranker.py /app', dockerfile)


if __name__ == '__main__':
    unittest.main()
