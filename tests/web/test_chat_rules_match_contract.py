"""채팅 화면의 값(CHAT_INPUT_RULES)이 API 명세·B 의 프롬프트와 같은지 확인한다. (C 담당, EE-12)

화면이 보내는 값은 서버가 받는 값이어야 한다. 질문 최대 글자 수와 level 값은 API 명세 3장,
후속 버튼 문구와 수준 이름은 app/chat/prompts.py(EE-10)가 기준이다. 한쪽만 바뀌면 여기서 실패한다.
(실제 POST /api/chat 과 직접 맞춰 보는 테스트는 EE-14 의 test_chat_retry_rules_match_server.py)
"""

from pathlib import Path
from typing import get_args

from app.chat.prompts import COMMON_GUIDANCE, LEVEL_GUIDANCE, ExplanationLevel
from app.web.router import CHAT_INPUT_RULES as RULES

API_SPEC = Path(__file__).parents[2] / "docs" / "spec" / "api.md"


def test_levels_match_the_levels_the_prompt_knows():
    values = [level.value for level in RULES.levels]

    assert values == list(get_args(ExplanationLevel)) == list(LEVEL_GUIDANCE)
    assert RULES.default_level in values


def test_level_labels_match_prompt_guidance():
    # prompts.py 의 수준 안내는 "아주 쉽게: …", "입문자: …", "전공자: …" 로 시작한다
    for level in RULES.levels:
        assert LEVEL_GUIDANCE[level.value].startswith(f"{level.label}:"), level


def test_follow_up_phrases_are_the_ones_the_prompt_handles():
    # 프롬프트가 "“더 쉽게”, “예시 하나 더”, “핵심만”에는 요청한 형태로 답하고…" 라고 따로 안내한다
    for phrase in RULES.follow_ups:
        assert f"“{phrase}”" in COMMON_GUIDANCE, phrase


def test_question_limit_and_levels_match_api_spec():
    spec = API_SPEC.read_text(encoding="utf-8")

    assert f"`question`: 앞뒤 공백 제거 후 1~{RULES.question_max_length:,}자" in spec
    levels = " | ".join(f"`{level.value}`" for level in RULES.levels)
    assert f"`level`: {levels}" in spec
