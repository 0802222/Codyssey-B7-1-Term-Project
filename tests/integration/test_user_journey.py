"""사용자 한 명의 전체 흐름: 가입 → 로그인 → 대화 → 질문 → 기록 조회 → 로그아웃. (EE-18)"""


def test_signup_to_history_and_logout(user):
    client = user.client

    # 로그인하면 채팅·기록 페이지가 열린다.
    assert client.get("/chat", follow_redirects=False).status_code == 200
    assert client.get("/history", follow_redirects=False).status_code == 200

    # 대화를 만들고 질문 → 같은 대화에 후속 질문
    created = user.post("/api/conversations", json={})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    first = user.ask(conversation_id, "API가 뭐야?", level="easy")
    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert first.json()["answer"]

    follow_up = user.ask(conversation_id, "더 쉽게", level="beginner")
    assert follow_up.status_code == 200
    assert follow_up.json()["conversation_id"] == conversation_id

    # 내 대화 목록: 제목은 첫 질문 (#49)
    conversations = client.get("/api/me/conversations").json()
    assert [item["id"] for item in conversations["items"]] == [conversation_id]
    assert conversations["items"][0]["title"] == "API가 뭐야?"

    # 대화 상세: 턴은 오래된 순, 수준·상태가 저장돼 있다
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    turns = [(t["question"], t["level"], t["status"]) for t in detail["turns"]]
    assert turns == [
        ("API가 뭐야?", "easy", "completed"),
        ("더 쉽게", "beginner", "completed"),
    ]

    # 내 질문 목록: 최신순
    chats = client.get("/api/me/chats").json()
    assert [item["question"] for item in chats["items"]] == ["더 쉽게", "API가 뭐야?"]

    # 로그아웃하면 세션이 끝나 API 는 401, 페이지는 로그인으로 보낸다.
    assert user.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/me/conversations").status_code == 401
    history = client.get("/history", follow_redirects=False)
    assert history.status_code == 303
    assert history.headers["location"] == "/login"
