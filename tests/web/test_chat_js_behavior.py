"""화면 JS 를 실제로 실행해 확인한다. (C 담당, EE-14·EE-17)

pytest 는 JS 를 실행하지 못해서 Node 의 기본 테스트 도구(node:test)로 tests/web/js/*.test.mjs 를
돌린다. chat.js·history.js·api.js 는 그대로 불러오고, 브라우저 대신 DOM·fetch·sessionStorage·
주소와 방문 기록만 흉내 낸다(tests/web/js/fake_dom.mjs). 새 패키지는 쓰지 않는다.
- chat_retry.test.mjs: 채팅의 다시 보내기·요청 번호 규칙 (EE-14). 서버도 흉내 내서 같은 요청 번호면
  저장한 답을 돌려주므로, AI 호출 수로 중복 호출이 생겼는지 알 수 있다
- history.test.mjs: 내 기록의 목록·더 보기·제목 대체·상세·실패 턴·주소 전환 (EE-17)
- chat_resume.test.mjs: 채팅의 이어서 질문과 주소 맞추기 (EE-17)
- auth_form.test.mjs: 가입·로그인 오류 안내 뒤 버튼 잠금 해제 (EE-21 — auth.js 를 node:vm 으로 실행)
- skip_link.test.mjs: 본문으로 건너뛰기가 주소를 바꾸지 않고 본문으로 포커스 (EE-21)

CI(ubuntu-latest)에는 node 가 있어 실행된다. node 가 없는 컴퓨터에서는 이 테스트만 건너뛴다(skip).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = sorted((Path(__file__).parent / "js").glob("*.test.mjs"))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node 가 없어 JS 동작 테스트를 건너뛴다 (CI 에는 있다)")
def test_chat_script_behaviour_in_node():
    assert JS_TESTS, "tests/web/js/*.test.mjs 가 없다"

    result = subprocess.run(
        [NODE, "--test", *map(str, JS_TESTS)],
        capture_output=True,
        text=True,
        encoding="utf-8",  # Node의 한글 출력도 Windows 기본 인코딩 대신 UTF-8로 읽는다.
        timeout=120,
    )

    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
