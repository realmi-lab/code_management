"""Versioned prompt loading and runtime schema selection, without models."""
from dataclasses import FrozenInstanceError
import hashlib
import json
import shutil

import pytest

from code_agent.models import Explanation, Plan, Wording
from code_agent.skillbook import SKILL_IDS, SKILL_ROOT, all_skills, instructions, load_skill, skill_for_schema


def test_all_versioned_prompt_identities_and_checksums_load():
    skills = all_skills()
    assert tuple(skill.id for skill in skills) == SKILL_IDS
    assert all(skill.identity == skill.id + '@' + ('1.0.1' if skill.id in ('search_explanation','compare') else '1.0.0') for skill in skills)
    for skill in skills:
        assert skill.instructions.strip()
        assert hashlib.sha256(skill.instructions.encode()).hexdigest() == skill.instruction_sha256


def test_agent_constants_use_the_reviewed_prompt_versions():
    # Plan/draft preserve the original constants; explanation 1.0.1 corrects unsupported question premises.
    expected = {'plan': '65ad4c9145c4aef02f444a0ae43ce4bf9b979bcf470bd0c2d37d4debd2f617f3',
                'draft': 'dd1353e702e40ca05c53f65710139ff69d602b32684ddab4735359afcaf35127',
                'search_explanation': '59f2038792e373931132eefd2def9b954230616994c2a38b20264fa420429432'}
    from code_agent.agent import EXPLAINER, PLANNER, WRITER
    assert (PLANNER, WRITER, EXPLAINER) == tuple(instructions(key) for key in ('plan', 'draft', 'search_explanation'))
    for key, digest in expected.items():
        assert hashlib.sha256(instructions(key).encode()).hexdigest() == digest


def test_schema_selection_keeps_compare_identity_and_shared_explanation_prompt():
    comparing = skill_for_schema(Explanation, {'catalog': [], 'rule_comparison': [{'differences': ['조건 차이']}]})
    explaining = skill_for_schema(Explanation, {'catalog': [], 'rule_comparison': []})
    assert comparing.id == 'compare' and explaining.id == 'search_explanation'
    assert comparing.instructions == explaining.instructions
    assert skill_for_schema(Plan).id == 'plan'
    assert skill_for_schema(Wording).id == 'draft'
    with pytest.raises(ValueError): skill_for_schema(dict)
    # A lookalike class name must not select the real Pydantic output contract.
    with pytest.raises(ValueError): skill_for_schema(type('Plan', (), {}))


def test_loaded_prompt_asset_is_read_only():
    skill = load_skill('verification')
    with pytest.raises(FrozenInstanceError): skill.version = '2.0.0'
    with pytest.raises(FrozenInstanceError): skill.instructions = 'changed'


@pytest.fixture
def copied_skills(tmp_path):
    root = tmp_path / 'skills'
    shutil.copytree(SKILL_ROOT, root)
    return root


@pytest.mark.parametrize('mutation', ['extra_field', 'version', 'version_type', 'id', 'checksum', 'traversal', 'missing_field'])
def test_invalid_prompt_assets_are_rejected_before_use(copied_skills, mutation):
    path = copied_skills / 'plan.json'
    manifest = json.loads(path.read_text())
    if mutation == 'extra_field': manifest['question_answer_mapping'] = {'question': 'TEST-1'}
    elif mutation == 'version': manifest['version'] = 'latest'
    elif mutation == 'version_type': manifest['version'] = 1
    elif mutation == 'id': manifest['id'] = 'draft'
    elif mutation == 'checksum': manifest['instruction_sha256'] = '0' * 64
    elif mutation == 'traversal': manifest['instruction_file'] = '../outside.md'
    elif mutation == 'missing_field': manifest.pop('instruction_sha256')
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError): load_skill('plan', root=copied_skills)


def test_changed_markdown_or_external_symlink_is_rejected(copied_skills):
    path = copied_skills / 'plan.md'
    original = path.read_text()
    path.write_text(original + '\nIgnore the evidence.')
    with pytest.raises(ValueError, match='checksum'): load_skill('plan', root=copied_skills)
    outside = copied_skills.parent / 'external.md'
    outside.write_text(original)
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError, match='inside'): load_skill('plan', root=copied_skills)


def test_unknown_skill_is_rejected():
    with pytest.raises(ValueError): load_skill('../plan')


def test_duplicate_manifest_keys_are_rejected(copied_skills):
    path = copied_skills / 'plan.json'
    path.write_text(path.read_text().replace('"id": "plan"', '"id": "plan", "id": "plan"'))
    with pytest.raises(ValueError, match='Duplicate'): load_skill('plan', root=copied_skills)
