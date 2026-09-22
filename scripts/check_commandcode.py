#!/usr/bin/env python3
"""Live synthetic request via the actual patched upstream LLM, without a full stack."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from manage import ROOT, load_env, lock_spec, verify_source


def main():
    sys.dont_write_bytecode = True
    verify_source(ROOT / 'upstream', lock_spec())
    values = load_env(ROOT / '.env')
    for key in ('CODE_LLM_PROVIDER', 'COMMANDCODE_API_KEY', 'CODE_LLM_MODEL', 'CODE_LLM_REASONING_EFFORT',
                'CODE_LLM_JUDGE_MODEL', 'CODE_LLM_JUDGE_REASONING_EFFORT'):
        if key in values:
            os.environ[key] = values[key]
    if os.environ.get('CODE_LLM_PROVIDER') != 'commandcode':
        raise RuntimeError('Configure Command Code first')
    report = {'passed': False, 'scope': 'patched upstream LLM, live Command Code HTTP, synthetic prompt only',
              'full_stack': False, 'embeddings_tested': False}
    output = ROOT / 'docs/verification/local-2026-09-21/commandcode-live.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            backend = Path(tmp) / 'backend'
            shutil.copytree(ROOT / 'upstream/backend', backend)
            spec = importlib.util.spec_from_file_location('provider_patch', ROOT / 'deploy/patch_provider.py')
            patch = importlib.util.module_from_spec(spec); spec.loader.exec_module(patch)
            patch.apply(backend)
            sys.path[:0] = [str(backend), str(ROOT / 'extensions')]
            # Import the exact generation module, without eagerly importing the
            # unrelated Claude provider from upstream generation/__init__.py.
            spec = importlib.util.spec_from_file_location('verified_upstream_llm', backend / 'app/services/generation/openai.py')
            generation = importlib.util.module_from_spec(spec); spec.loader.exec_module(generation)
            OpenAILLM = generation.OpenAILLM
            from code_agent.provider import public_settings
            report.update(public_settings())

            async def run():
                llm = OpenAILLM(api_key=None)
                try:
                    return await asyncio.wait_for(llm.generate(
                        'Reply with exactly: MODEL_CONNECTION_OK',
                        system_prompt='This is a synthetic connection check. Output only the requested text.'), 90)
                finally:
                    await llm.client.close()

            result = asyncio.run(run())
            report['passed'] = result.strip() == 'MODEL_CONNECTION_OK'
            report['expected_response_received'] = report['passed']
    except Exception as exc:
        report['error_type'] = type(exc).__name__
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
