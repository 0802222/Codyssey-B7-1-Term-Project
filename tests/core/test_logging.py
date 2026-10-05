import logging


def test_request_events_share_request_id(client, caplog):
    with caplog.at_level(logging.INFO, logger="easyexplain"):
        response = client.get("/health")

    request_id = response.headers["X-Request-ID"]
    messages = [record.getMessage() for record in caplog.records]
    received = [m for m in messages if m.startswith("request_received")]
    completed = [m for m in messages if m.startswith("request_completed")]

    assert received == [f"request_received request_id={request_id} method=GET path=/health"]
    assert len(completed) == 1
    assert f"request_id={request_id}" in completed[0]
    assert "status=200" in completed[0]


def test_each_request_gets_new_request_id(client):
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]

    assert first != second
