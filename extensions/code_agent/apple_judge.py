"""Apple 온디바이스 판정 전송.

Mac 쪽 브리지(extensions/apple_bridge)의 OpenAI 호환 엔드포인트로 판정을 보낸다. 판정 기준(충실도 0.9·근거 0.8)과
StrictJudge 검사, 원본 FaithfulnessChecker/HallucinationDetector의 호출 구조는 그대로 두고, 작은 온디바이스 모델이
감당할 수 있도록 판정 입력만 바꾼다.

1. 원본 판정 프롬프트에서 근거(JSON)와 답변(JSON)을 꺼내, 근거는 한국어 표찰이 붙은 문장으로 다시 적고 답변은 줄 단위
   주장으로 나눈다. 영문 키 JSON과 한국어 표찰 문장을 글자 그대로 비교하던 오판을 없애기 위한 것이다.
2. `메시지코드:` 줄로 시작하는 블록의 `문구`·`메뉴`·`노출 조건` 같은 표찰 줄은 그 코드의 DB 원문과 정규화 후 문자 단위로
   비교한다. 같으면 뒷받침, 다르면 왜곡으로 확정하며 모델에 묻지 않는다. 원문 우선 원칙을 기계적으로 적용한 것이다.
3. 근거 문장 안에 글자 그대로 들어 있지 않은 자유 서술 줄만 모델에 번호를 붙여 묻고, 구조화 출력(JSON Schema)으로
   각 줄의 뒷받침 여부를 받는다.
4. 결과를 StrictJudge가 읽는 세 줄(`점수 / 목록 / verdict`)로 되돌려 쓴다. 뒷받침되지 않는 주장이 하나라도 있으면
   verdict를 UNFAITHFUL/FAIL로 적어 답변 길이와 무관하게 차단한다.

프롬프트가 원본 서식과 다르면 답변 전체를 한 번에 판정하는 방식으로 대신하고, 브리지에 닿지 못하면 생성 모델로
되돌아가지 않고 503으로 중단한다.
"""
from __future__ import annotations
import json
import copy
import os
import re
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from .store import DomainError

REQUEST_TIMEOUT = 90
MAX_TOKENS = 600
NONE_LABEL = '없음'

# 답변 줄의 한국어 표찰 → 카탈로그 행 필드. EXPLAINER/WRITER 프롬프트가 쓰는 표찰을 우선한다.
LABELS = {'메시지코드': 'code', '코드': 'code', '문구': 'message', '등록 문구': 'message', '메뉴': 'menu', '노출 조건': 'trigger',
          '노출조건': 'trigger', '비고': 'notes', '업무': 'business', '목적': 'purpose', '유형': 'message_type', '제목': 'title',
          '영문 제목': 'title_en', '영문 문구': 'contents_en', '영문': 'contents_en', '상태': 'status', '설명': 'explanation'}
KOREAN = {'user':'요청', 'code': '메시지코드', 'message': '문구', 'menu': '메뉴', 'trigger': '노출 조건', 'notes': '비고', 'business': '업무',
          'purpose': '목적', 'message_type': '유형', 'title': '제목', 'title_en': '영문 제목', 'contents_en': '영문 문구',
          'status': '상태', 'revision': '리비전', 'added_date': '등록일', 'spelling_check': '맞춤법', 'question': '질문',
          'request': '요청', 'history': '이전 대화', 'previous_draft': '이전 초안', 'candidates': '후보', 'catalog': '후보',
          'rule_comparison': '규칙 비교', 'references': '참조 코드', 'text': '본문', 'explanation': '설명', 'role': '역할',
          'content': '내용', 'payload': '내용', 'message_code': '메시지코드'}
SKIP_KEYS = {'id', 'updated_at', 'source', 'catalog_fields', 'owner', 'version'}
CODE_PATTERN = re.compile(r'[A-Za-z]{1,6}-\d{2,8}')
LABEL_LINE = re.compile(r'^\s*[-*•·]?\s*(?P<label>[가-힣A-Za-z ]{1,12}?)\s*[:：]\s*(?P<value>.+?)\s*$')
PROMPT_BLOCKS = re.compile(r'검색된 문서:\n(?P<documents>.*?)\n\n생성된 답변:\n(?P<answer>.*?)\n\n(?:특히 다음 항목|다음 형식으로)', re.S)


def _schema(list_field, list_description, score_field, score_description, verdicts):
    return {'type': 'object', 'propertyOrder': [list_field, score_field, 'verdict'],
            'required': [list_field, score_field, 'verdict'],
            'properties': {list_field: {'type': 'array', 'description': list_description, 'items': {'type': 'string'}},
                           score_field: {'type': 'number', 'description': score_description},
                           'verdict': {'type': 'string', 'enum': list(verdicts)}}}


JUDGES = {
    'faithfulness_score': {
        'name': 'faithfulness_judgement', 'list_field': 'distortions', 'verdicts': ('FAITHFUL', 'UNFAITHFUL'),
        'threshold': 0.9, 'pass': 'FAITHFUL', 'fail': 'UNFAITHFUL',
        'schema': _schema('distortions', '답변이 문서의 사실을 왜곡하거나 변형한 항목. 없으면 빈 목록',
                          'faithfulness_score', '원문 충실도 점수 0.0~1.0', ('FAITHFUL', 'UNFAITHFUL'))},
    'grounded_ratio': {
        'name': 'grounding_judgement', 'list_field': 'ungrounded_claims', 'verdicts': ('PASS', 'FAIL'),
        'threshold': 0.8, 'pass': 'PASS', 'fail': 'FAIL',
        'schema': _schema('ungrounded_claims', '문서에서 확인할 수 없는 답변의 주장. 없으면 빈 목록',
                          'grounded_ratio', '문서에서 직접 확인되는 주장의 비율 0.0~1.0', ('PASS', 'FAIL'))},
}
CLAIM_SCHEMA = {'type': 'object', 'required': ['judgements'],
                'properties': {'judgements': {'type': 'array', 'description': '번호가 붙은 문장마다 하나씩',
                                              'items': {'type': 'object', 'required': ['index', 'supported'], 'propertyOrder': ['index', 'supported'],
                                                        'properties': {'index': {'type': 'integer', 'description': '문장 번호'},
                                                                       'supported': {'type': 'boolean', 'description': '문서가 이 문장을 뒷받침하면 true'}}}}}}
CLAIM_INSTRUCTIONS = ('[검사할 답변]에 있는 문장만 판정하세요. [참고 자료]의 항목을 판정하거나 번호를 붙이지 마세요. '
                      '각 답변 문장이 참고 자료의 내용으로 뒷받침되는지 판정하세요. '
                      '문서에 없는 내용을 말하거나 문서와 다른 수치·기간·조건·메뉴·채널·코드를 말하는 문장은 뒷받침되지 않는 것입니다. '
                      '문서의 내용을 다른 말로 요약하거나 옮겨 적은 문장, 문서에 해당 항목이 없다고 말하는 문장은 뒷받침되는 것입니다. '
                      '질문과 검색된 코드의 주제가 다르므로 관련 코드를 찾지 못했다는 설명도 뒷받침됩니다. '
                      '문장마다 번호와 true/false를 하나씩 답하세요.')


def judge_field(prompt):
    """원본 판정 프롬프트가 요구하는 점수 항목으로 판정 종류를 고른다. 항목이 없거나 둘 다 있으면 자유 서식."""
    found = [field for field in JUDGES if re.search(r'^\s*' + field + r'\s*:', prompt or '', re.M)]
    return found[0] if len(found) == 1 else None


def malformed():
    return DomainError('AI 검증 응답이 불완전하여 결과를 저장하지 않았습니다.', 502)


def normalize(value):
    text = re.sub(r'\s+', ' ', str(value)).strip()
    text = text.strip('"\'“”‘’「」『』()[]')
    return text.rstrip('.。!?').strip().lower()


def split_prompt(prompt):
    """원본 판정 서식에서 (근거 목록, 답변)을 꺼낸다. 서식이 다르거나 JSON이 아니면 None."""
    match = PROMPT_BLOCKS.search(prompt or '')
    if not match:
        return None
    try:
        answer = json.loads(match.group('answer'))
    except ValueError:
        return None
    documents = []
    for part in match.group('documents').split('\n---\n'):
        try:
            documents.append(json.loads(part))
        except ValueError:
            documents.append(part)
    return documents, answer


def is_row(value):
    return isinstance(value, dict) and isinstance(value.get('code'), str) and 'message' in value


def render(value, indent=0):
    """근거를 한국어 표찰이 붙은 줄로 적는다. 카탈로그 행은 메시지코드·문구·메뉴·노출 조건을 먼저 쓴다."""
    pad = '  ' * indent
    lines = []
    if is_row(value):
        ordered = ['code', 'message', 'menu', 'trigger'] + [k for k in value if k not in ('code', 'message', 'menu', 'trigger')]
        for key in ordered:
            item = value.get(key)
            if key in SKIP_KEYS or item in (None, '', [], {}) or isinstance(item, (dict, list)):
                continue
            lines.append(f'{pad}{KOREAN.get(key, key)}: {item}')
        return lines
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SKIP_KEYS or item in (None, '', [], {}):
                continue
            label = KOREAN.get(key, key)
            if isinstance(item, (dict, list)):
                lines.append(f'{pad}{label}:')
                lines.extend(render(item, indent + 1))
            else:
                lines.append(f'{pad}{label}: {item}')
        return lines
    if isinstance(value, list):
        for index, item in enumerate(value, 1):
            if isinstance(item, (dict, list)):
                lines.append(f'{pad}- 항목')
                lines.extend(render(item, indent + 1))
            else:
                lines.append(f'{pad}- {item}')
        return lines
    return [f'{pad}{value}']


def collect(value, strings, rows):
    """근거 안의 모든 문자열 값과 카탈로그 행을 모은다."""
    if is_row(value):
        rows.setdefault(value['code'].upper(), value)
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SKIP_KEYS:
                continue
            collect(item, strings, rows)
    elif isinstance(value, list):
        for item in value:
            collect(item, strings, rows)
    elif isinstance(value, str) and value.strip():
        strings.append(normalize(value))


def claims_of(answer):
    """답변 JSON을 줄 단위 주장으로 나눈다. Explanation은 text 줄과 참조 코드, Wording은 표찰 줄이다."""
    if isinstance(answer, dict) and isinstance(answer.get('text'), str):
        lines = [line.strip() for line in answer['text'].splitlines() if line.strip()]
        for code in answer.get('references') or []:
            if isinstance(code, str) and code.strip():
                lines.append(f'참조 코드: {code.strip()}')
        return lines
    if isinstance(answer, dict) and isinstance(answer.get('message'), str):
        lines = []
        for key in ('message', 'menu', 'trigger', 'explanation'):
            item = answer.get(key)
            if isinstance(item, str) and item.strip():
                lines.extend(f'{KOREAN[key]}: {part.strip()}' for part in item.splitlines() if part.strip())
        return lines
    return [line for line in render(answer) if line.strip()]


def supported_literally(value, strings):
    target = normalize(value)
    if not target:
        return True
    return any(target == text or (len(target) >= 4 and target in text) for text in strings)


def classify(claims, strings, rows):
    """각 주장을 뒷받침·왜곡·모델 확인 필요 세 갈래로 가른다. 왜곡은 '원문: X → 답변: Y' 형식으로 적는다."""
    supported, distortions, pending = [], [], []
    current = None
    for index, claim in enumerate(claims):
        match = LABEL_LINE.match(claim)
        label = match.group('label').strip() if match else None
        value = match.group('value').strip() if match else claim
        field = LABELS.get(label) if label else None
        if field == 'code' or (label in ('참조 코드', '다른 코드') and CODE_PATTERN.fullmatch(value.strip())):
            code = value.strip().upper()
            if CODE_PATTERN.fullmatch(code) and code in rows:
                current = rows[code]
                supported.append(index)
            else:
                current = None
                distortions.append((index, f'문서에 없는 코드: {value.strip()}'))
            continue
        if field and current is not None and field in current and current.get(field) not in (None, ''):
            original = str(current[field])
            if normalize(value) == normalize(original):
                supported.append(index)
            else:
                distortions.append((index, f'원문: {original} → 답변: {value}'))
            continue
        if supported_literally(value, strings) or supported_literally(claim, strings):
            supported.append(index)
            continue
        pending.append(index)
    return supported, distortions, pending


class AppleJudge:
    """브리지 호출 한 번이 판정 한 번이다. 연결 오류만 한 번 재시도하고 그 밖에는 곧바로 실패한다."""

    def __init__(self):
        self.last_usage = None
        self.last_detail = None

    @property
    def model(self):
        from .provider import judge_options
        return judge_options()['model']

    @staticmethod
    def client(base_url):
        token = os.getenv('CODE_APPLE_BRIDGE_TOKEN', '').strip()
        return AsyncOpenAI(api_key=token or 'local-bridge', base_url=base_url, timeout=REQUEST_TIMEOUT, max_retries=1)

    async def complete(self, messages, schema_name=None, schema=None):
        from .provider import judge_options
        options = judge_options()
        kwargs = {'model': options['model'], 'messages': messages, 'temperature': 0, 'max_tokens': MAX_TOKENS}
        if schema:
            kwargs['response_format'] = {'type': 'json_schema', 'json_schema': {'name': schema_name, 'schema': schema}}
        client = self.client(options['base_url'])
        self.last_usage = None
        try:
            response = await client.chat.completions.create(**kwargs)
        except (APIConnectionError, APITimeoutError) as exc:
            raise DomainError('Apple 온디바이스 판정 브리지에 연결할 수 없어 결과를 저장하지 않았습니다. Mac에서 브리지 실행 상태를 확인해주세요.', 503) from exc
        except APIStatusError as exc:
            from .apple import model_error
            raise model_error(exc, '판정') from exc
        finally:
            await client.close()
        self.last_usage = response.usage.model_dump() if response.usage else None
        content = response.choices[0].message.content if response.choices else None
        if not isinstance(content, str) or not content.strip():
            raise malformed()
        return content

    async def generate(self, prompt, system_prompt=None):
        field = judge_field(prompt)
        parts = split_prompt(prompt) if field else None
        if parts:
            return await self.judge_claims(field, *parts)
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        if not field:
            return await self.complete(messages)
        spec = JUDGES[field]
        content = await self.complete(messages, spec['name'], spec['schema'])
        try:
            payload = json.loads(content)
        except ValueError as exc:
            raise malformed() from exc
        return render_whole(field, payload)

    async def judge_claims(self, field, documents, answer):
        spec = JUDGES[field]
        if isinstance(answer,dict) and 'text' in answer:
            documents=[{k:d[k] for k in ('catalog','rule_comparison') if k in d} if isinstance(d,dict) and 'catalog' in d else d for d in documents]
        strings, rows = [], {}
        for document in documents:
            collect(document, strings, rows)
        claims = claims_of(answer)
        if not claims:
            raise malformed()
        supported, distortions, pending = classify(claims, strings, rows)
        model_calls = 0
        if pending:
            model_calls = 1
            evidence = '\n'.join(line for document in documents for line in render(document))
            numbered = '\n'.join(f'{n}. {claims[index]}' for n, index in enumerate(pending, 1))
            prompt = f'{CLAIM_INSTRUCTIONS}\n\n[참고 자료]\n{evidence}\n\n[검사할 답변: {len(pending)}개]\n{numbered}'
            schema = copy.deepcopy(CLAIM_SCHEMA)
            schema['properties']['judgements'].update(minItems=len(pending), maxItems=len(pending))
            content = await self.complete([{'role': 'user', 'content': prompt}], 'claim_support', schema)
            try:
                judgements = json.loads(content).get('judgements')
            except (ValueError, AttributeError) as exc:
                raise malformed() from exc
            if not isinstance(judgements, list):
                raise malformed()
            verdicts = {}
            for item in judgements:
                if (not isinstance(item, dict) or type(item.get('index')) is not int
                        or not isinstance(item.get('supported'), bool)
                        or not 1 <= item['index'] <= len(pending) or item['index'] in verdicts):
                    raise malformed()
                verdicts[item['index']] = item['supported']
            for n, index in enumerate(pending, 1):
                # 모델이 답하지 않은 문장은 뒷받침되지 않은 것으로 본다(닫힌 실패).
                if verdicts.get(n) is True:
                    supported.append(index)
                else:
                    distortions.append((index, claims[index]))
        total = len(claims)
        score = len(supported) / total
        verdict = spec['pass'] if not distortions and score >= spec['threshold'] else spec['fail']
        items = [' '.join(text.split()) for _, text in sorted(distortions)]
        self.last_detail = {'claims': total, 'supported': len(supported), 'model_checked': len(pending), 'model_calls': model_calls}
        return f"{field}: {score:.2f}\n{spec['list_field']}: {'; '.join(items) if items else NONE_LABEL}\nverdict: {verdict}"


def render_whole(field, payload):
    """답변 전체를 한 번에 판정한 구조화 응답을 세 줄로 바꾼다(원본 서식이 아닐 때만 쓰는 예비 경로)."""
    spec = JUDGES[field]
    if not isinstance(payload, dict):
        raise malformed()
    try:
        score = float(payload[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise malformed() from exc
    if not 0.0 <= score <= 1.0:
        raise malformed()
    verdict = str(payload.get('verdict', '')).strip().upper()
    if verdict not in spec['verdicts']:
        raise malformed()
    items = payload.get(spec['list_field']) or []
    if not isinstance(items, list):
        raise malformed()
    items = [' '.join(str(item).split()) for item in items if str(item).strip()]
    return f"{field}: {score:.2f}\n{spec['list_field']}: {'; '.join(items) if items else NONE_LABEL}\nverdict: {verdict}"


# 이전 이름과의 호환. 테스트와 문서는 render_whole을 쓴다.
render_payload = render_whole
