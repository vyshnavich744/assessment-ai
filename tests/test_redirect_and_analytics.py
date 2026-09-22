def test_redirect_returns_302_and_records_click(client):
    r = client.post("/api/urls", json={"long_url": "https://example.com/target"})
    code = r.json()["code"]

    g = client.get(f"/{code}", follow_redirects=False)
    assert g.status_code == 302
    assert g.headers["location"] == "https://example.com/target"

    a = client.get(f"/api/urls/{code}/analytics")
    assert a.status_code == 200
    assert a.json()["total_clicks"] == 1


def test_redirect_unknown_code_404(client):
    g = client.get("/doesnotexist", follow_redirects=False)
    assert g.status_code == 404


def test_analytics_counts_multiple_clicks(client):
    r = client.post("/api/urls", json={"long_url": "https://example.com/multi"})
    code = r.json()["code"]
    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)
    a = client.get(f"/api/urls/{code}/analytics")
    assert a.json()["total_clicks"] == 3
    assert len(a.json()["last_10_clicks"]) == 3


def test_analytics_unknown_code_404(client):
    a = client.get("/api/urls/doesnotexist/analytics")
    assert a.status_code == 404


def test_delete_then_analytics_still_readable_but_redirect_404(client):
    r = client.post("/api/urls", json={"long_url": "https://example.com/soft-delete"})
    code = r.json()["code"]
    client.delete(f"/api/urls/{code}")

    g = client.get(f"/{code}", follow_redirects=False)
    assert g.status_code == 404

    a = client.get(f"/api/urls/{code}/analytics")
    assert a.status_code == 200
    assert a.json()["is_active"] is False
