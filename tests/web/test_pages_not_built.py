"""아직 만들지 않은 웹 페이지 테스트. (C 담당)

각 화면 작업에서 페이지를 만들 때 이 목록에서 해당 경로를 지운다.
(/chat 은 EE-12, /history 는 EE-17. /signup·/login 은 EE-09 에서 만들어 지웠다)
"""

import pytest


@pytest.mark.parametrize("path", ["/chat", "/history"])
def test_pages_not_built_yet_do_not_fake_success(client, path):
    response = client.get(path)

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"
