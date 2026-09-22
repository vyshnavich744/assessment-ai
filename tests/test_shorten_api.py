def test_shorten_creates_code(client):
    r = client.post("/api/urls", json={"long_url": "https://example.com/foo"})
    assert r.status_code == 201
    body = r.json()
    assert len(body["code"]) == 7
    assert body["long_url"] == "https://example.com/foo"


def test_shorten_rejects_invalid_url(client):
    r = client.post("/api/urls", json={"long_url": "not-a-url"})
    assert r.status_code == 422


def test_custom_alias_used_verbatim(client):
    r = client.post("/api/urls", json={"long_url": "https://example.com/bar", "custom_alias": "mybrand1"})
    assert r.status_code == 201
    assert r.json()["code"] == "mybrand1"


def test_custom_alias_conflict_returns_409(client):
    client.post("/api/urls", json={"long_url": "https://example.com/a", "custom_alias": "dupe1234"})
    r2 = client.post("/api/urls", json={"long_url": "https://example.com/b", "custom_alias": "dupe1234"})
    assert r2.status_code == 409


def test_custom_alias_rejects_non_alnum(client):
    r = client.post("/api/urls", json={"long_url": "https://example.com/a", "custom_alias": "bad-alias!"})
    assert r.status_code == 422


def test_list_urls(client):
    client.post("/api/urls", json={"long_url": "https://example.com/1"})
    client.post("/api/urls", json={"long_url": "https://example.com/2"})
    r = client.get("/api/urls")
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_ttl_sets_expiry(client):
    r = client.post("/api/urls", json={"long_url": "https://example.com/exp", "ttl_seconds": 3600})
    assert r.status_code == 201
    assert r.json()["expires_at"] is not None
