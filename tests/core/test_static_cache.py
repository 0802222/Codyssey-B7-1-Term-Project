"""배포 후에도 브라우저가 예전 정적 파일을 쓰지 않는다. (L, EE-24)"""

import pytest

STATIC_FILES = ["/static/js/chat.js", "/static/js/api.js", "/static/css/style.css"]


@pytest.mark.parametrize("path", STATIC_FILES)
def test_static_files_must_be_revalidated(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"]


def test_unchanged_static_file_is_304_without_body(client):
    first = client.get("/static/js/chat.js")

    again = client.get("/static/js/chat.js", headers={"If-None-Match": first.headers["etag"]})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["cache-control"] == "no-cache"
