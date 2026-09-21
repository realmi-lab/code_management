from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extensions"))

from code_agent.agent import Agent
from code_agent.compare import compare_message
from code_agent.importer import parse_upload
from code_agent.models import Actor, Approval, Explanation, ImportCommit, Plan, Turn, Wording
from code_agent.store import Store

ADMIN = Actor(id=101, role="admin", name="샘플 관리자")
USER = Actor(id=202, role="user", name="샘플 기획자")
SAMPLE = ROOT / "examples" / "sample_code_catalog_200.xlsx"


def tokens(text: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[가-힣A-Za-z0-9{}]+", text) if len(x) >= 2]


class SampleGateway:
    """Deterministic test double for external RAG/LLM only.

    Store/import/agent/approval paths are the production extension code. Retrieval and
    generation are deterministic here so this test can run without an OpenAI key.
    """

    def __init__(self, store: Store):
        self.store = store

    async def search(self, query: str):
        _, items = self.store.snapshot()
        q = tokens(query)
        ranked = []
        for rec in items:
            msg = rec["message"].lower()
            menu = rec["menu"].lower()
            trigger = rec["trigger"].lower()
            code = rec["code"].lower()
            score = 0
            for tok in q:
                if tok in msg:
                    score += 8
                if tok in trigger:
                    score += 5
                if tok in menu:
                    score += 3
                if tok in code:
                    score += 20
            if query.strip() in rec["message"]:
                score += 30
            if score:
                ranked.append((score, rec["code"], rec))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        found = [x[2] for x in ranked[:8]]
        return found, [{"name": "SAMPLE_TEST_RETRIEVAL", "count": len(found)}]

    async def json(self, schema, system, payload):
        if schema is Plan:
            return Plan(action="search", query=payload["user"])
        if schema is Wording:
            request = payload["request"]
            # Preserve the explicit numeric condition from the request.
            if "48시간" in request and "출금" in request:
                return Wording(
                    message="보안 설정 변경 후 48시간 동안 출금이 제한됩니다.",
                    menu="보안설정",
                    trigger="보안 설정 변경",
                    explanation="48시간 출금 제한을 안내하는 합성 테스트 초안입니다.",
                )
            return Wording(
                message="서비스 이용 조건을 확인해주세요.",
                menu="공통",
                trigger="조건 확인 필요",
                explanation="합성 테스트 초안입니다.",
            )
        if schema is Explanation:
            refs = [c["code"] for c in payload.get("catalog", [])]
            return Explanation(
                text="조회한 기존 코드와 새 문구의 조건 차이를 확인했습니다. 재사용 여부는 노출 조건까지 검토해야 합니다.",
                references=refs,
            )
        raise AssertionError(schema)


async def main():
    t0 = time.perf_counter()
    parsed = parse_upload(SAMPLE.read_bytes(), SAMPLE.name)
    assert len(parsed["records"]) == 200, len(parsed["records"])
    assert parsed["errors"] == [], parsed["errors"]
    assert parsed["warnings"] == [], parsed["warnings"]

    with tempfile.TemporaryDirectory() as td:
        store = Store("sqlite:///" + str(Path(td) / "sample200.db"))
        store.initialize()
        preview = store.save_preview(ADMIN, parsed)
        assert preview["counts"] == {"new": 200, "unchanged": 0, "conflict": 0}
        committed = store.apply_preview(
            ADMIN,
            preview["id"],
            ImportCommit(expected_catalog_version=preview["catalog_version"]),
        )
        assert committed["changed"] == 200

        state, active = store.snapshot()
        _, all_rows = store.snapshot(True)
        assert len(active) == 190
        assert len(all_rows) == 200
        assert store.get_code("AT-2001")["message"] == "메뉴 확인 후 30초 이후에 인증해주세요."
        assert store.get_code("AT-2200")["status"] == "retired"

        gateway = SampleGateway(store)
        agent = Agent(store, gateway)
        th = store.create_thread(USER, "샘플 200건 검증")

        # 1) Natural-language search should surface the intended existing code.
        r1 = await agent.turn(
            USER,
            th["id"],
            Turn(
                request_id=uuid.uuid4(),
                expected_version=0,
                text="이미 가입된 휴대폰 번호라는 안내 찾아줘",
                action="search",
            ),
        )
        assert r1["candidates"] and r1["candidates"][0]["code"] == "AT-2011", r1["candidates"][:3]

        # 2) Compare a planner-authored candidate against the existing code.
        r2 = await agent.turn(
            USER,
            th["id"],
            Turn(
                request_id=uuid.uuid4(),
                expected_version=1,
                text="첫 번째 후보와 '이미 가입된 전화번호입니다.'를 비교해줘",
                action="compare",
                selected_code="AT-2011",
                proposed_message="이미 가입된 전화번호입니다.",
                menu="회원가입",
                trigger="휴대폰 번호 중복",
            ),
        )
        assert r2["comparisons"] and r2["comparisons"][0]["code"] == "AT-2011"

        # 3) Compare the intentional direction difference: 이후 vs 이내.
        direct = compare_message(
            "메뉴 확인 후 30초 이내에 인증해주세요.",
            store.get_code("AT-2001"),
            menu="본인인증",
            trigger="메뉴 확인 후 30초 미경과",
        )
        assert direct["differences"], direct
        assert any("이후" in json.dumps(x, ensure_ascii=False) or "이내" in json.dumps(x, ensure_ascii=False) for x in direct["differences"])

        # 4) Ask the agent to create a new draft. The synthetic LLM preserves 48 hours.
        r3 = await agent.turn(
            USER,
            th["id"],
            Turn(
                request_id=uuid.uuid4(),
                expected_version=2,
                text="보안 설정을 바꾸면 48시간 동안 출금 제한 안내가 필요해. 새 문구 만들어줘",
                action="draft",
            ),
        )
        draft = r3["draft"]
        assert draft and draft["payload"]["message"] == "보안 설정 변경 후 48시간 동안 출금이 제한됩니다."
        assert any(c["code"] == "AT-2127" for c in r3["candidates"]), r3["candidates"]

        # 5) Formal registration stays outside the model and requires admin confirmation.
        old_authority = os.environ.get("CODE_CATALOG_AUTHORITY")
        os.environ["CODE_CATALOG_AUTHORITY"] = "excel"
        try:
            approved = store.approve(
                ADMIN,
                draft["id"],
                Approval(
                    expected_catalog_version=r3["catalog_version"],
                    expected_draft_revision=draft["revision"],
                    code="AT-2301",
                    reason="샘플 E2E 신규 문구 등록 검증",
                    duplicate_ack=True,
                    external_registered=True,
                ),
            )
        finally:
            if old_authority is None:
                os.environ.pop("CODE_CATALOG_AUTHORITY", None)
            else:
                os.environ["CODE_CATALOG_AUTHORITY"] = old_authority

        assert approved["code"] == "AT-2301"
        assert store.get_code("AT-2301")["message"] == "보안 설정 변경 후 48시간 동안 출금이 제한됩니다."
        audit = store.audit_log(ADMIN)
        assert len(audit) == 200  # API는 최신 200건으로 제한
        assert any(x['action'] == 'approve' and x['entity'] == 'AT-2301' for x in audit)

        report = {
            "sample_file": str(SAMPLE),
            "parsed_records": len(parsed["records"]),
            "active_records": len(active),
            "retired_records": len(all_rows) - len(active),
            "catalog_version_after_import": state["version"],
            "exact_lookup": {"code": "AT-2001", "message": store.get_code("AT-2001")["message"]},
            "natural_search_top": r1["candidates"][0]["code"],
            "comparison_target": r2["comparisons"][0]["code"],
            "direction_difference_detected": True,
            "draft_message": draft["payload"]["message"],
            "draft_similar_candidate_found": "AT-2127" in [c["code"] for c in r3["candidates"]],
            "approved_new_code": approved["code"],
            "final_catalog_count": len(store.snapshot(True)[1]),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            "external_services": "RAG retrieval/LLM are deterministic test doubles; production store/import/agent/approval code is real.",
            "passed": True,
        }
        out = ROOT / "docs" / "verification" / "sample-200-e2e.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        store.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
