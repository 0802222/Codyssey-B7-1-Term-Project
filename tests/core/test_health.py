def test_health_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
    assert response.headers["X-Request-ID"]


def test_health_creates_db_file(client, settings, tmp_path):
    client.get("/health")

    assert (tmp_path / "test.db").exists()
