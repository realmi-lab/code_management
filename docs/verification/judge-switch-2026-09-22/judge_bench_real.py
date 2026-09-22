"""Judge bench in the real pipeline format: CatalogSafety.validate with demo catalog rows as evidence.

Runs inside a throwaway container of the api image with the working tree mounted at /ext.
Usage: python /bench.py <label> [runs]
The judge transport is chosen by the container env (CODE_LLM_JUDGE_PROVIDER=apple or empty = generation model).
"""
import asyncio
import json
import os
import sys
import time

sys.path[:0] = ['/ext', '/app']
from code_agent.models import Explanation  # noqa: E402
from code_agent.operations import TrackedLLM  # noqa: E402
from code_agent.routing import RoutingLLM  # noqa: E402
from code_agent.safety import CatalogSafety, GroundingError, NumericGroundingError  # noqa: E402
from code_agent.store import DomainError  # noqa: E402

LABEL = sys.argv[1]
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
CANDIDATES = [
    {"code": "EX-0104", "message": "30초 이내에 인증을 완료해주세요.", "menu": "기기 인증", "trigger": "인증 시작 후 완료 제한시간 안내",
     "notes": "AT-1923과 시간의 방향이 다른 합성 예시", "status": "active", "revision": 1, "business": "기기 인증", "message_type": "alert",
     "purpose": "인증 시작 후 완료 제한시간 안내", "title": "30초 이내에 인증을 완료해주세요.",
     "title_en": "Please complete authentication within 30 seconds.", "contents_en": "Please complete authentication within 30 seconds."},
    {"code": "EX-0105", "message": "인증번호는 {seconds}초 후에 다시 요청할 수 있습니다.", "menu": "휴대폰 인증", "trigger": "재발송 대기시간 안내",
     "notes": "변수명은 변경하지 않습니다. 합성 예시", "status": "active", "revision": 1, "business": "휴대폰 인증", "message_type": "alert",
     "purpose": "재발송 대기시간 안내", "title": "인증번호는 {seconds}초 후에 다시 요청할 수 있습니다.",
     "title_en": "You can request another verification code in {seconds} seconds.", "contents_en": "You can request another verification code in {seconds} seconds."},
    {"code": "EX-0101", "message": "인증번호를 발송했습니다.", "menu": "휴대폰 인증", "trigger": "인증번호 전송 성공", "notes": "합성 예시",
     "status": "active", "revision": 1, "business": "휴대폰 인증", "message_type": "alert", "purpose": "인증번호 전송 성공",
     "title": "인증번호를 발송했습니다.", "title_en": "A verification code has been sent.", "contents_en": "A verification code has been sent."},
]
EVIDENCE = {'question': '인증을 30초 안에 끝내야 한다는 안내', 'catalog': CANDIDATES, 'rule_comparison': []}
GOOD = '메시지코드: EX-0104\n문구: 30초 이내에 인증을 완료해주세요.\n메뉴: 기기 인증\n노출 조건: 인증 시작 후 완료 제한시간 안내'
VARIANTS = {
    'good': (GOOD, 'passed'),
    'good_two_codes': (GOOD + '\n\n메시지코드: EX-0105\n문구: 인증번호는 {seconds}초 후에 다시 요청할 수 있습니다.\n메뉴: 휴대폰 인증\n노출 조건: 재발송 대기시간 안내', 'passed'),
    'bad_numeric_60s': (GOOD.replace('30초', '60초'), 'blocked'),
    'bad_added_claim': (GOOD + '\n이 알림은 이메일 인증 화면에서도 표시됩니다.', 'blocked'),
    'bad_menu_swap': (GOOD.replace('메뉴: 기기 인증', '메뉴: 휴대폰 인증'), 'blocked'),
    'bad_wrong_code': (GOOD.replace('EX-0104', 'EX-0105'), 'blocked'),
}


async def one(text):
    safety = CatalogSafety()
    llm = TrackedLLM(RoutingLLM(), 'Explanation')
    started = time.monotonic()
    try:
        await asyncio.wait_for(safety.validate(Explanation(text=text, references=['EX-0104']), EVIDENCE, llm), 150)
        status, detail = 'passed', None
    except NumericGroundingError as exc:
        status, detail = 'blocked_numeric', exc.message[:60]
    except GroundingError as exc:
        status, detail = 'blocked', exc.message[:60]
    except DomainError as exc:
        status, detail = f'error_{exc.status}', exc.message[:80]
    except BaseException as exc:  # noqa: BLE001
        status, detail = 'error', (type(exc).__name__ + ': ' + str(exc)[:120]).replace(os.environ.get('COMMANDCODE_API_KEY', '#'), '[KEY]')
    return {'status': status, 'seconds': round(time.monotonic() - started, 1), 'detail': detail}


async def main():
    from code_agent.provider import public_settings
    settings = public_settings()
    report = {'label': LABEL, 'judge_provider': settings.get('judge_provider'), 'judge_model': settings.get('judge_model'), 'runs': RUNS, 'variants': {}}
    for name, (text, expected) in VARIANTS.items():
        rows = [await one(text) for _ in range(RUNS)]
        outcomes = [row['status'] for row in rows]
        ok = all(o == expected or (expected == 'blocked' and o.startswith('blocked')) for o in outcomes)
        report['variants'][name] = {'expected': expected, 'outcomes': outcomes, 'seconds': [row['seconds'] for row in rows],
                                    'details': sorted({row['detail'] for row in rows if row['detail']}), 'as_expected': ok}
        print(json.dumps({'variant': name, 'expected': expected, 'outcomes': outcomes, 'seconds': [row['seconds'] for row in rows]}, ensure_ascii=False), flush=True)
    print('REPORT ' + json.dumps(report, ensure_ascii=False), flush=True)


asyncio.run(main())
