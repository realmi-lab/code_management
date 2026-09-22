"""Catalogue boundary using upstream detectors; DB originals are never modified."""
from __future__ import annotations
import json
import asyncio
import re
import logging

log=logging.getLogger(__name__)
from .store import DomainError

class NumericGroundingError(DomainError):
    """A generated quantity failed evidence checks; never save the rejected answer."""
    def __init__(self):
        super().__init__('AI 결과에 근거 없는 수치가 포함되어 저장하지 않았습니다.',502)

class GroundingError(DomainError):
    """A well-formed judge rejected generated content, not an input/system error."""
    def __init__(self):
        super().__init__('AI 결과의 근거 검증을 통과하지 못했습니다. 원문과 조건을 확인해주세요.',422)


class StrictJudge:
    """Upstream parsers default missing scores to PASS. Reject malformed output first."""
    def __init__(self, llm, field, verdicts, redact=None):
        self.llm, self.field, self.verdicts = llm, field, verdicts
        self.redact=redact

    def record(self,status,score=None,verdict=None,response=None,error_type=None):
        # Only judge reason fields; never the prompt, answer, or full model output.
        reason_field='distortions' if self.field=='faithfulness_score' else 'ungrounded_claims'
        reasons=[]
        if isinstance(response,str) and self.redact:
            # Judge models may put list items on lines after the field label.
            # Stop at the next known field; never log the prompt/full response.
            block=re.search(r'^\s*'+reason_field+r'\s*:(.*?)(?=^\s*(?:faithfulness_score|grounded_ratio|verdict|distortions|ungrounded_claims)\s*:|\Z)',response,re.I|re.M|re.S)
            if block:
                reasons=[line.strip() for line in block.group(1).splitlines() if line.strip()][:3]
            reasons=[self.redact(value)[:1200] for value in reasons]
        from .operations import _validation_context
        data={**(_validation_context.get() or {}),'stage':self.field,'status':status,
              'score':score,'threshold':0.9 if self.field=='faithfulness_score' else 0.8,
              'verdict':verdict,'reasons':reasons,'error_type':error_type}
        log.info('catalog_validation %s',json.dumps(data,ensure_ascii=False))

    async def generate(self, prompt, system_prompt=None):
        try:
            response = await self.llm.generate(prompt, system_prompt=system_prompt)
        except BaseException as exc:
            self.record('error',error_type=type(exc).__name__)
            raise
        if not isinstance(response,str):
            self.record('malformed')
            raise DomainError('AI 검증 응답이 불완전하여 결과를 저장하지 않았습니다.', 502)
        scores=[line.strip() for line in response.splitlines() if line.strip().lower().startswith(self.field.lower())]
        verdicts=[line.strip() for line in response.splitlines() if line.strip().lower().startswith('verdict')]
        # The upstream parser uses the last field. Reject ambiguous duplicate fields
        # so its score cannot differ from the one validated at this boundary.
        match = re.fullmatch(rf'{re.escape(self.field)}\s*:\s*(0(?:\.\d+)?|1(?:\.0+)?)', scores[0],re.I) if len(scores)==1 else None
        verdict = re.fullmatch(r'verdict\s*:\s*(\w+)',verdicts[0],re.I) if len(verdicts)==1 else None
        if not match or not verdict or verdict.group(1).upper() not in self.verdicts:
            self.record('malformed')
            raise DomainError('AI 검증 응답이 불완전하여 결과를 저장하지 않았습니다.', 502)
        failed=verdict.group(1).upper() in ('UNFAITHFUL','FAIL') or float(match.group(1))<(0.9 if self.field=='faithfulness_score' else 0.8)
        self.record('blocked' if failed else 'passed',float(match.group(1)),verdict.group(1).upper(),response)
        if failed:
            raise GroundingError()
        return response


class CatalogSafety:
    def __init__(self):
        from app.services.guardrails.pii import KoreanPIIDetector
        self.pii = KoreanPIIDetector(llm=None)

    def redact(self, value):
        if isinstance(value, str):
            # Complete redaction for outbound data, not the upstream partial display mask.
            for match in sorted(self.pii.regex_scan(value), key=lambda m: m.start, reverse=True):
                value = value[:match.start] + '[PII:' + match.pii_type + ']' + value[match.end:]
            return value
        if isinstance(value, dict):
            return {key: self.redact(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.redact(item) for item in value]
        return value

    def diagnostic_redact(self,value):
        # Reasons can quote evidence. Apply the same PII masking plus credential masking.
        import os
        from . import ai_config
        for key in ('OPENAI_API_KEY','COMMANDCODE_API_KEY','DEEPSEEK_API_KEY','ANTHROPIC_API_KEY','LOCAL_EMBEDDING_TOKEN'):
            secret=ai_config.key(key) or os.getenv(key,'')
            if secret:value=value.replace(secret,'[SECRET]')
        value=re.sub(r'(?i)bearer\s+[^\s,;\]"\']+','Bearer [SECRET]',value)
        value=re.sub(r'(?i)(?:sk-|cc_)[A-Za-z0-9_-]{12,}','[SECRET]',value)
        return self.redact(value)

    def judge_llm(self, llm, stage):
        """One judge transport per stage: CODE_LLM_JUDGE_* pins a separate model, else the caller's LLM."""
        from .provider import judge_configured
        judge=None
        if judge_configured():
            from .routing import JudgeLLM
            judge=JudgeLLM()
        if hasattr(llm,'for_stage'):return llm.for_stage(stage,judge)
        return judge or llm

    async def prepare(self, payload, llm):
        from app.services.guardrails.injection import PromptInjectionDetector
        safe = self.redact(payload)
        detector = PromptInjectionDetector(llm=llm.for_stage('input-check') if hasattr(llm,'for_stage') else llm)
        result = await detector.detect(json.dumps(safe, ensure_ascii=False))
        if result.blocked:
            raise DomainError('입력 또는 참고 자료에 지시를 우회하는 내용이 있어 AI 처리를 중단했습니다.', 422)
        return safe

    async def validate(self, result, evidence, llm):
        from app.services.guardrails.faithfulness import FaithfulnessChecker
        from app.services.guardrails.hallucination import HallucinationDetector
        from app.services.guardrails.numeric_verifier import NumericVerifier
        from .models import Explanation, Wording
        if not isinstance(result, (Explanation, Wording)):
            return
        payload = result.model_dump()
        if self.redact(payload) != payload:
            raise DomainError('AI가 개인정보를 포함한 결과를 생성하여 저장하지 않았습니다.', 502)
        answer = json.dumps(payload, ensure_ascii=False)
        documents = [json.dumps(evidence, ensure_ascii=False)]
        from .compare import signature
        output_quantities={(u,v) for u,v,_ in signature(answer)['quantities']}
        evidence_quantities={(u,v) for u,v,_ in signature(documents[0])['quantities']}
        numeric=NumericVerifier().verify(answer, documents)
        from .operations import _validation_context
        missing=sorted(output_quantities-evidence_quantities)
        log.info('catalog_validation %s',json.dumps({**(_validation_context.get() or {}),
            'stage':'numeric','status':'blocked' if missing or not numeric.passed else 'passed',
            'missing_quantities':missing,
            'ungrounded_numbers':[self.diagnostic_redact(v)[:120] for v in numeric.ungrounded_numbers[:10]]},ensure_ascii=False))
        if not output_quantities.issubset(evidence_quantities):
            raise NumericGroundingError()
        if not numeric.passed:
            raise NumericGroundingError()
        faith_llm=self.judge_llm(llm,'faithfulness')
        hall_llm=self.judge_llm(llm,'grounding')
        # Independent checks inspect the same immutable answer/evidence; both must pass.
        checks=await asyncio.gather(
            FaithfulnessChecker(StrictJudge(faith_llm, 'faithfulness_score', {'FAITHFUL','UNFAITHFUL'},self.diagnostic_redact)).verify(answer, documents),
            HallucinationDetector(StrictJudge(hall_llm, 'grounded_ratio', {'PASS','FAIL'},self.diagnostic_redact)).verify(answer, documents),
            return_exceptions=True)
        errors=[result for result in checks if isinstance(result,BaseException)]
        if errors:
            # A malformed/unavailable judge is not a repairable content failure.
            raise next((error for error in errors if not isinstance(error,GroundingError)),errors[0])
        faith,hall=checks
        if faith.verdict != 'FAITHFUL' or hall.verdict != 'PASS':
            raise GroundingError()
