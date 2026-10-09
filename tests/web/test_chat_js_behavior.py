"""채팅 화면 JS 의 다시 보내기·요청 번호 규칙을 실제로 실행해 확인한다. (C 담당, EE-14)

pytest 는 JS 를 실행하지 못해서 Node 의 기본 테스트 도구(node:test)로 tests/web/js/*.test.mjs 를
돌린다. chat.js·api.js 는 그대로 불러오고, 브라우저 대신 DOM·fetch·sessionStorage 만 흉내 낸다
(tests/web/js/fake_dom.mjs). 서버도 흉내 내서 같은 요청 번호면 저장한 답을 돌려주므로,
AI 호출 수로 중복 호출이 생겼는지 알 수 있다. 새 패키지는 쓰지 않는다.

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
        timeout=120,
    )

    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
