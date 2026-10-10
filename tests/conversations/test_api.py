from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, create_engine, select

from app.conversations.repository import complete_turn, create_pending_turn, fail_turn
from app.db.models import ChatTurn, Conversation, User
from app.db.session import init_db

PASSWORD = "1234567890"


def _signup_and_login(test_client, settings, email):
    origin = {"Origin": settings.site_origin}
    body = {"email": email, "password": PASSWORD}
    signup = test_client.post("/api/auth/signup", headers=origin, json=body)
    assert signup.status_code == 201
    login = test_client.post("/api/auth/login", headers=origin, json=body)
    assert login.status_code == 200
    return {"X-CSRF-Token": login.json()["csrf_token"]}


def _me_id(test_client):
    return test_client.get("/api/auth/me").json()["user"]["id"]


def _create_conversation(test_client, headers):
    response = test_client.post("/api/conversations", headers=headers, json={})
    assert response.status_code == 201
    return response.json()


def _seed_turn(settings, conversation_id, user_id, question, status="completed"):
    """저장소 함수로 턴을 직접 만든다. status: completed / failed / pending"""
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            turn = create_pending_turn(
                session=session,
                conversation_id=UUID(conversation_id),
                user_id=user_id,
                client_request_id=uuid4(),
                request_id=f"req-{uuid4().hex[:8]}",
                level="easy",
                question=question,
            )
            turn_id = turn.id
            if status == "completed":
                complete_turn(
                    session=session, turn_id=turn_id, user_id=user_id, answer=f"{question} 답변"
                )
            elif status == "failed":
                fail_turn(
                    session=session, turn_id=turn_id, user_id=user_id, error_code="AI_TIMEOUT"
                )
            return turn_id
    finally:
        engine.dispose()


def _error_core(response):
    """request_id 는 요청마다 달라서 code, message 만 비교한다."""
    error = response.json()["error"]
    return error["code"], error["message"]


@pytest.fixture
def user_a(client, settings):
    """첫 번째 사용자. (client, CSRF 헤더, user_id)"""
    headers = _signup_and_login(client, settings, "a@example.com")
    return client, headers, _me_id(client)


@pytest.fixture
def user_b(app, settings, user_a):
    """두 번째 사용자. 쿠키가 따로인 별도 client 를 쓴다."""
    with TestClient(app, raise_server_exceptions=False) as other:
        headers = _signup_and_login(other, settings, "b@example.com")
        yield other, headers, _me_id(other)


@pytest.mark.parametrize(
    "path",
    [
        "/api/me/conversations",
        "/api/me/chats",
        f"/api/conversations/{uuid4()}",
    ],
)
def test_get_endpoints_require_login(client, path):
    response = client.get(path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_app_restart_marks_saved_pending_turn_interrupted(app, settings):
    seed_engine = create_engine(settings.database_url)
    try:
        init_db(seed_engine)
        with Session(seed_engine) as session:
            user = User(email="restart@example.com", password_hash="hash")
            session.add(user)
            session.commit()
            session.refresh(user)

            conversation = Conversation(user_id=user.id, title="재시작 테스트")
            session.add(conversation)
            session.commit()
            session.refresh(conversation)

            pending = ChatTurn(
                conversation_id=conversation.id,
                user_id=user.id,
                client_request_id=uuid4(),
                request_id="request-pending",
                level="easy",
                question="처리 중 질문",
                status="pending",
            )
            session.add(pending)
            session.commit()
            pending_id = pending.id
    finally:
        seed_engine.dispose()

    # TestClient 시작 시 앱 lifespan 이 init_db()를 실행한다.
    with TestClient(app, raise_server_exceptions=False):
        with Session(app.state.engine) as session:
            recovered = session.exec(
                select(ChatTurn).where(ChatTurn.id == pending_id)
            ).one()

    assert recovered.status == "interrupted"
    assert recovered.completed_at is not None


def test_create_conversation_requires_login(client):
    response = client.post("/api/conversations", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_create_conversation_success(user_a):
    client, headers, _ = user_a

    response = client.post("/api/conversations", headers=headers, json={})

    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "title", "created_at"}
    assert UUID(data["id"])
    assert data["title"]
    assert data["created_at"]


def test_first_chat_question_updates_title_of_api_created_conversation(user_a):
    client, headers, _ = user_a
    conversation = _create_conversation(client, headers)
    question = "첫 질문으로 대화 제목을 정해요"

    response = client.post(
        "/api/chat",
        headers=headers,
        json={
            "conversation_id": conversation["id"],
            "question": question,
            "level": "easy",
            "client_request_id": str(uuid4()),
        },
    )

    assert response.status_code == 200
    detail = client.get(f"/api/conversations/{conversation['id']}")

    assert detail.status_code == 200
    assert detail.json()["conversation"]["title"] == question


def test_created_conversation_appears_in_my_list(user_a):
    client, headers, _ = user_a
    created = _create_conversation(client, headers)

    response = client.get("/api/me/conversations")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [created["id"]]


def test_create_conversation_without_csrf(user_a):
    client, _, _ = user_a

    response = client.post("/api/conversations", json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"


def test_create_conversation_with_wrong_csrf(user_a):
    client, _, _ = user_a

    response = client.post(
        "/api/conversations",
        headers={"X-CSRF-Token": "wrong-token"},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"


def test_create_conversation_db_failure_returns_503_and_logs(user_a, monkeypatch):
    client, headers, _ = user_a
    events = []
    rollback_calls = 0

    def fake_log_event(name, **fields):
        events.append((name, fields))

    def failing_commit(self):
        raise OperationalError("INSERT", {}, Exception("boom"))

    original_rollback = Session.rollback

    def track_rollback(self):
        nonlocal rollback_calls
        rollback_calls += 1
        return original_rollback(self)

    # 로그인은 이미 끝났으므로 이 시점부터 commit 이 실패하게 한다.
    monkeypatch.setattr("app.conversations.repository.log_event", fake_log_event)
    monkeypatch.setattr(Session, "commit", failing_commit)
    monkeypatch.setattr(Session, "rollback", track_rollback)

    response = client.post("/api/conversations", headers=headers, json={})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_ERROR"
    assert [name for name, _ in events] == ["db_save_failed"]
    assert events[0][1]["entity"] == "conversation"
    assert events[0][1]["error_type"] == "OperationalError"
    assert rollback_calls == 1

    conversations = client.get("/api/me/conversations")
    assert conversations.status_code == 200
    assert conversations.json()["items"] == []


def test_get_own_conversation_with_turns_oldest_first(user_a, settings):
    client, headers, user_id = user_a
    conversation = _create_conversation(client, headers)
    first = _seed_turn(settings, conversation["id"], user_id, "첫 질문", "completed")
    second = _seed_turn(settings, conversation["id"], user_id, "둘째 질문", "pending")

    response = client.get(f"/api/conversations/{conversation['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["conversation"]["id"] == conversation["id"]
    assert [turn["id"] for turn in data["turns"]] == [first, second]
    assert data["turns"][0]["status"] == "completed"
    assert data["turns"][0]["answer"] == "첫 질문 답변"
    assert data["turns"][1]["status"] == "pending"
    assert data["turns"][1]["answer"] is None


def test_turn_item_has_documented_fields(user_a, settings):
    client, headers, user_id = user_a
    conversation = _create_conversation(client, headers)
    _seed_turn(settings, conversation["id"], user_id, "질문", "failed")

    turn = client.get(f"/api/conversations/{conversation['id']}").json()["turns"][0]

    assert set(turn) == {
        "id",
        "conversation_id",
        "level",
        "question",
        "answer",
        "status",
        "error_code",
        "created_at",
    }
    assert turn["status"] == "failed"
    assert turn["error_code"] == "AI_TIMEOUT"
    assert turn["answer"] is None


def test_other_users_conversation_returns_404(user_a, user_b):
    client_a, headers_a, _ = user_a
    client_b, _, _ = user_b
    conversation = _create_conversation(client_a, headers_a)

    response = client_b.get(f"/api/conversations/{conversation['id']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_other_users_and_missing_conversation_look_identical(user_a, user_b):
    client_a, headers_a, _ = user_a
    client_b, _, _ = user_b
    conversation = _create_conversation(client_a, headers_a)

    others = client_b.get(f"/api/conversations/{conversation['id']}")
    missing = client_b.get(f"/api/conversations/{uuid4()}")

    assert others.status_code == missing.status_code == 404
    assert _error_core(others) == _error_core(missing)


def test_other_users_turns_are_not_exposed(user_a, user_b, settings):
    client_a, headers_a, id_a = user_a
    client_b, _, _ = user_b
    conversation = _create_conversation(client_a, headers_a)
    _seed_turn(settings, conversation["id"], id_a, "비밀 질문")

    response = client_b.get(f"/api/conversations/{conversation['id']}")

    assert response.status_code == 404
    assert "비밀 질문" not in response.text


def test_invalid_conversation_id_format_returns_422(user_a):
    client, _, _ = user_a

    response = client.get("/api/conversations/abc")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_my_conversations_only_returns_own(user_a, user_b):
    client_a, headers_a, _ = user_a
    client_b, headers_b, _ = user_b
    mine = _create_conversation(client_a, headers_a)
    theirs = _create_conversation(client_b, headers_b)

    response = client_a.get("/api/me/conversations")

    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [mine["id"]]
    assert theirs["id"] not in ids


def test_my_conversations_item_fields_and_defaults(user_a):
    client, headers, _ = user_a
    _create_conversation(client, headers)

    data = client.get("/api/me/conversations").json()

    assert data["limit"] == 20
    assert data["offset"] == 0
    assert data["has_more"] is False
    assert set(data["items"][0]) == {"id", "title", "created_at", "updated_at"}


def test_my_conversations_pagination(user_a):
    client, headers, _ = user_a
    created = {_create_conversation(client, headers)["id"] for _ in range(3)}

    page1 = client.get("/api/me/conversations?limit=2&offset=0").json()
    page2 = client.get("/api/me/conversations?limit=2&offset=2").json()

    assert len(page1["items"]) == 2
    assert page1["has_more"] is True
    assert (page1["limit"], page1["offset"]) == (2, 0)
    assert len(page2["items"]) == 1
    assert page2["has_more"] is False
    assert (page2["limit"], page2["offset"]) == (2, 2)

    ids = [item["id"] for item in page1["items"] + page2["items"]]
    assert len(set(ids)) == 3
    assert set(ids) == created


def test_my_conversations_has_more_false_when_exactly_limit(user_a):
    client, headers, _ = user_a
    for _ in range(3):
        _create_conversation(client, headers)

    data = client.get("/api/me/conversations?limit=3").json()

    assert len(data["items"]) == 3
    assert data["has_more"] is False


def test_my_conversations_offset_past_end_is_empty(user_a):
    client, headers, _ = user_a
    _create_conversation(client, headers)

    data = client.get("/api/me/conversations?offset=10").json()

    assert data["items"] == []
    assert data["has_more"] is False


def test_my_chats_only_returns_own_turns(user_a, user_b, settings):
    client_a, headers_a, id_a = user_a
    client_b, headers_b, id_b = user_b
    conv_a = _create_conversation(client_a, headers_a)
    conv_b = _create_conversation(client_b, headers_b)
    mine = _seed_turn(settings, conv_a["id"], id_a, "내 질문")
    theirs = _seed_turn(settings, conv_b["id"], id_b, "남의 질문")

    response = client_a.get("/api/me/chats")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [mine]
    assert theirs not in ids
    assert "남의 질문" not in response.text


def test_my_chats_includes_all_statuses_newest_first(user_a, settings):
    client, headers, user_id = user_a
    conversation = _create_conversation(client, headers)
    done = _seed_turn(settings, conversation["id"], user_id, "완료", "completed")
    failed = _seed_turn(settings, conversation["id"], user_id, "실패", "failed")
    pending = _seed_turn(settings, conversation["id"], user_id, "진행 중", "pending")

    items = client.get("/api/me/chats").json()["items"]

    assert [item["id"] for item in items] == [pending, failed, done]
    assert [item["status"] for item in items] == ["pending", "failed", "completed"]


def test_my_chats_pagination(user_a, settings):
    client, headers, user_id = user_a
    conversation = _create_conversation(client, headers)
    t1 = _seed_turn(settings, conversation["id"], user_id, "1")
    t2 = _seed_turn(settings, conversation["id"], user_id, "2")
    t3 = _seed_turn(settings, conversation["id"], user_id, "3")

    page1 = client.get("/api/me/chats?limit=2&offset=0").json()
    page2 = client.get("/api/me/chats?limit=2&offset=2").json()

    assert [item["id"] for item in page1["items"]] == [t3, t2]
    assert page1["has_more"] is True
    assert [item["id"] for item in page2["items"]] == [t1]
    assert page2["has_more"] is False


def test_my_chats_has_more_false_when_exactly_limit(user_a, settings):
    client, headers, user_id = user_a
    conversation = _create_conversation(client, headers)
    for index in range(2):
        _seed_turn(settings, conversation["id"], user_id, str(index))

    data = client.get("/api/me/chats?limit=2").json()

    assert len(data["items"]) == 2
    assert data["has_more"] is False


@pytest.mark.parametrize("path", ["/api/me/conversations", "/api/me/chats"])
@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=-1",
        "limit=abc",
        "offset=-1",
        "offset=abc",
        "offset=1000001",
        f"offset={10**100}",
    ],
)
def test_invalid_pagination_params_return_422(user_a, path, query):
    client, _, _ = user_a

    response = client.get(f"{path}?{query}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("path", ["/api/me/conversations", "/api/me/chats"])
@pytest.mark.parametrize("limit", [1, 100])
def test_limit_boundaries_are_accepted(user_a, path, limit):
    client, _, _ = user_a

    response = client.get(f"{path}?limit={limit}")

    assert response.status_code == 200
    assert response.json()["limit"] == limit


def test_responses_do_not_leak_internal_fields(user_a, settings):
    client, headers, user_id = user_a
    conversation = _create_conversation(client, headers)
    _seed_turn(settings, conversation["id"], user_id, "질문")

    responses = [
        client.get("/api/me/conversations"),
        client.get("/api/me/chats"),
        client.get(f"/api/conversations/{conversation['id']}"),
    ]

    for response in responses:
        assert response.status_code == 200
        for forbidden in ("password", "token_hash", "user_id", "request_id", "client_request_id"):
            assert forbidden not in response.text


def test_created_at_has_utc_marker(user_a):
    client, headers, _ = user_a
    created_at = _create_conversation(client, headers)["created_at"]
    assert created_at.endswith("Z") or created_at.endswith("+00:00")
