import pytest

from app.chat.prompts import LEVEL_GUIDANCE, build_system_prompt


@pytest.mark.parametrize(
    ("level", "required_guidance"),
    [
        ("easy", ["일상적인 단어", "간단한 비유", "생소한 용어를 풀어"]),
        ("beginner", ["기본 용어", "뜻을 풀고", "작은 예시", "작동 흐름"]),
        ("advanced", ["전문 용어", "원리", "전제·한계"]),
    ],
)
def test_each_level_has_korean_guidance_for_its_audience(level, required_guidance):
    prompt = build_system_prompt(level)

    assert "한국어" in prompt
    assert f"현재 설명 수준은 {level}" in prompt
    for guidance in required_guidance:
        assert guidance in prompt


@pytest.mark.parametrize("level", ["easy", "beginner", "advanced"])
def test_each_level_receives_friendly_tone_and_plain_text_instructions(level):
    # 지침 전달을 검증한다. 실제 모델이 지키는지는 수집한 답변으로 별도 확인한다.
    prompt = build_system_prompt(level)

    assert "모든 설명 수준에서 친절한 한국어 '~해요'체" in prompt
    assert "일반 텍스트로 작성" in prompt
    assert "Markdown 제목·굵게·가로선·표·코드펜스와 HTML은 사용하지 않는다" in prompt
    assert "문단·줄바꿈·간단한 숫자 목록을 사용할 수 있고" in prompt
    assert "짧은 코드도 일반 텍스트로 적을 수 있다" in prompt


@pytest.mark.parametrize("level", ["easy", "beginner", "advanced"])
def test_initial_explanation_format_has_the_agreed_order(level):
    prompt = build_system_prompt(level)

    definition = prompt.index("1. 한 줄 정의")
    explanation = prompt.index("2. 수준에 맞는 설명 또는 비유")
    example = prompt.index("3. 짧은 예시")
    summary = prompt.index("4. 핵심 정리")
    assert definition < explanation < example < summary


@pytest.mark.parametrize("level", ["easy", "beginner", "advanced"])
def test_followup_requests_use_context_without_forcing_the_initial_format(level):
    prompt = build_system_prompt(level)

    assert "같은 대화의 문맥" in prompt
    assert "더 쉽게" in prompt
    assert "예시 하나 더" in prompt
    assert "핵심만" in prompt
    assert "매번 같은 서식을 강제하지 않는다" in prompt


@pytest.mark.parametrize("level", ["easy", "beginner", "advanced"])
def test_clear_new_questions_get_an_explanation_and_missing_context_is_not_invented(level):
    prompt = build_system_prompt(level)

    assert "새 대화라도 질문이 명확하면 바로 설명한다" in prompt
    assert "현재 질문과 전달받은 문맥을 함께 확인해도 설명 대상이 불분명할 때만" in prompt
    assert "확인 질문 하나" in prompt
    assert "전달받지 않은 예전 내용을 아는 척하지 않는다" in prompt


@pytest.mark.parametrize("level", ["easy", "beginner", "advanced"])
def test_short_repeated_questions_are_explained_at_the_current_level(level):
    # 지침 포함 여부만 확인하며 실제 AI의 해석은 실제 답변으로 별도 검증한다.
    prompt = build_system_prompt(level)

    assert "이미 설명한 주제를 다시 묻거나 설명 수준을 바꿔 묻더라도" in prompt
    assert "현재 설명 수준으로 다시 설명한다" in prompt
    assert "이전 답변의 난이도·말투나 이전 턴의 “더 쉽게” 요청보다" in prompt
    assert "서버가 지정한 현재 설명 수준을 우선한다" in prompt
    assert "질문이 짧거나 이전 질문과 같다는 이유만으로 모호하다고 판단하지 않는다" in prompt
    assert "현재 질문과 전달받은 문맥에서 설명 대상이 확인되면 바로 설명한다" in prompt
    assert "전달받은 문맥이 있는데 이전 대화 내용을 전달받지 못했다고 말하지 않는다" in prompt


@pytest.mark.parametrize("level", ["easy", "beginner", "advanced"])
def test_uncertainty_sources_and_unavailable_tools_are_described_honestly(level):
    prompt = build_system_prompt(level)

    assert "불확실성을 밝히고" in prompt
    assert "출처를 지어내지 않는다" in prompt
    assert "실시간 검색을 했다고 말하지 않는다" in prompt
    assert "도구 실행·파일 접근·외부 검색 기능이 있는 것처럼 말하지 않는다" in prompt


def test_beginner_explains_topic_specific_terms_and_flow_beyond_an_analogy():
    guidance = LEVEL_GUIDANCE["beginner"]

    assert "주제에 필요한 기본 용어" in guidance
    assert "1~2개" in guidance
    assert "뜻을 풀고" in guidance
    assert "작은 예시로 작동 흐름을 설명" in guidance
    assert "비유만 반복하지 않는다" in guidance


def test_advanced_explains_mechanisms_now_instead_of_offering_them_later():
    guidance = LEVEL_GUIDANCE["advanced"]

    assert "이전 비유를 요약하거나" in guidance
    assert "더 깊은 설명을 나중에 제공하겠다는 제안으로 대신하지 않고" in guidance
    assert "이번 답변에서 원리와 전제·한계를 설명한다" in guidance


@pytest.mark.parametrize("level", ["easy", "beginner", "advanced"])
def test_analogies_and_unverified_service_examples_do_not_claim_false_facts(level):
    prompt = build_system_prompt(level)

    assert "비유나 단순화로 실제와 다른 동작을 단정하지 않는다" in prompt
    assert "비유를 썼다면 본문과 핵심 정리에서 같은 대상과 역할을 유지한다" in prompt
    assert "특정 서비스의 확인되지 않은 동작이나 URL·수치" in prompt
    assert "가정 또는 가상 예시라고 밝힌다" in prompt


@pytest.mark.parametrize("level", ["", "EASY", "expert", "easy\n"])
def test_unknown_level_is_rejected_instead_of_using_a_default(level):
    with pytest.raises(ValueError):
        build_system_prompt(level)


def test_changing_the_current_level_does_not_keep_the_previous_guidance():
    easy = build_system_prompt("easy")
    advanced = build_system_prompt("advanced")
    beginner = build_system_prompt("beginner")

    assert easy != advanced
    assert beginner != easy
    assert beginner != advanced
    assert "일상적인 단어" in easy
    assert "전제·한계" in advanced
    assert "주제에 필요한 기본 용어" in beginner
    assert "일상적인 단어" not in advanced
    assert "전제·한계" not in easy
    assert build_system_prompt("easy") == easy
    for prompt in (advanced, beginner, build_system_prompt("easy")):
        assert "모든 설명 수준에서 친절한 한국어 '~해요'체" in prompt
        assert "일반 텍스트로 작성" in prompt
        assert "Markdown 제목·굵게·가로선·표·코드펜스와 HTML은 사용하지 않는다" in prompt
        assert "본문과 핵심 정리에서 같은 대상과 역할을 유지한다" in prompt
