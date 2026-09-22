"""Versioned prompt assets and schema-to-skill selection.

Execution, output validation and safety rules belong to Agent, the Pydantic
models and CatalogSafety. This module loads instructions and identifies them
in telemetry; it does not implement a second workflow or policy engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any

SKILL_ROOT = Path(__file__).with_name('skills')
SKILL_IDS = ('plan', 'search_explanation', 'compare', 'draft', 'verification')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate application skill manifest key')
        result[key] = value
    return result


@dataclass(frozen=True)
class SkillContract:
    id: str
    version: str
    instructions: str
    instruction_sha256: str

    @property
    def identity(self) -> str:
        return self.id + '@' + self.version


def _read_skill(skill_id: str, root: Path) -> SkillContract:
    if skill_id not in SKILL_IDS:
        raise ValueError('Unknown application skill')
    manifest = json.loads((root / (skill_id + '.json')).read_text(encoding='utf-8'),
                          object_pairs_hook=_unique_object)
    fields = {'id', 'version', 'instruction_file', 'instruction_sha256'}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValueError('Invalid application skill manifest fields')
    if manifest['id'] != skill_id:
        raise ValueError('Application skill identity mismatch')
    if not isinstance(manifest['version'], str) or not re.fullmatch(r'[1-9][0-9]*\.[0-9]+\.[0-9]+', manifest['version']):
        raise ValueError('Invalid application skill version')
    filename = manifest['instruction_file']
    if not isinstance(filename, str) or not re.fullmatch(r'[a-z_]+\.md', filename):
        raise ValueError('Invalid application skill instruction path')
    path = root / filename
    if path.resolve().parent != root.resolve():
        raise ValueError('Application skill instructions must stay inside the asset directory')
    instruction = path.read_text(encoding='utf-8')
    checksum = hashlib.sha256(instruction.encode('utf-8')).hexdigest()
    if not instruction.strip() or manifest['instruction_sha256'] != checksum:
        raise ValueError('Application skill instruction checksum mismatch')
    return SkillContract(id=skill_id, version=manifest['version'], instructions=instruction,
                         instruction_sha256=checksum)


@lru_cache(maxsize=len(SKILL_IDS))
def _load_builtin(skill_id: str) -> SkillContract:
    return _read_skill(skill_id, SKILL_ROOT)


def load_skill(skill_id: str, *, root: Path | None = None) -> SkillContract:
    """Load an immutable prompt asset; alternate roots support isolated tests."""
    return _load_builtin(skill_id) if root is None else _read_skill(skill_id, Path(root))


def instructions(skill_id: str) -> str:
    return load_skill(skill_id).instructions


def skill_for_schema(schema, payload: Any = None) -> SkillContract:
    """Select the existing operation; comparison retains the Explanation schema."""
    from .models import Explanation, Plan, Wording
    if schema is Plan:
        return load_skill('plan')
    if schema is Wording:
        return load_skill('draft')
    if schema is Explanation:
        comparing = isinstance(payload, dict) and bool(payload.get('rule_comparison'))
        return load_skill('compare' if comparing else 'search_explanation')
    raise ValueError('No application skill for this output schema')


def all_skills() -> tuple[SkillContract, ...]:
    return tuple(load_skill(skill_id) for skill_id in SKILL_IDS)
