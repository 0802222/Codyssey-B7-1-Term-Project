def test_logged_in_client_passes_auth_and_reaches_handler(logged_in_client):
    # 로그인·CSRF 검사를 지나, 구현된 채팅 API의 필수 본문 검증까지 도달한다.
    response = logged_in_client.post("/api/chat")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_without_login_stops_at_auth(client):
    response = client.post("/api/chat")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
