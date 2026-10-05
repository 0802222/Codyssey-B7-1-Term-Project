def test_logged_in_client_passes_auth_and_reaches_handler(logged_in_client):
    # 로그인 검사(EE-08)를 지나 채팅 핸들러(EE-13)까지 도달한다.
    response = logged_in_client.post("/api/chat")
    assert response.status_code == 501
    assert "EE-13" in response.json()["error"]["message"]


def test_client_without_login_stops_at_auth(client):
    response = client.post("/api/chat")
    assert response.status_code == 501
    assert "EE-08" in response.json()["error"]["message"]
