from datetime import date

from fastapi.testclient import TestClient

from app.db import crud
from app.sources.fetcher import FetchedSource


def _youtube(channel: str = "UC-one", video: str = "dQw4w9WgXcQ") -> FetchedSource:
    return FetchedSource(
        type="video",
        original_url=f"https://youtu.be/{video}",
        canonical_url=f"https://www.youtube.com/watch?v={video}",
        source_key=video,
        title="A market call",
        content="Transcript",
        published_at=date(2026, 1, 2),
        youtube_video_id=video,
        youtube_channel_id=channel,
    )


def test_health_and_missing_api(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/nope").status_code == 404


def test_unmatched_link_requests_only_a_name(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.routes.links.fetch_source", lambda _url: _youtube())
    response = client.post("/api/links", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert response.status_code == 200
    assert response.json()["status"] == "requires_guru_name"
    assert response.json()["source_type"] == "video"
    assert client.get("/api/gurus").json() == []


def test_named_link_creates_guru_source_and_pending_claim(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.routes.links.fetch_source", lambda _url: _youtube())
    called: list[str] = []
    monkeypatch.setattr("app.routes.links.run_claim_finder", called.append)
    response = client.post("/api/links", json={"url": "https://youtu.be/dQw4w9WgXcQ", "guru_name": "Jane Doe"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched_guru"]["name"] == "Jane Doe"
    assert body["claims"][0]["extraction_status"] == "pending"
    assert body["claims"][0]["asset_description"] is None
    assert body["claims"][0]["source"]["title"] == "A market call"
    assert called == [body["source_id"]]

    guru_id = body["matched_guru"]["id"]
    assert client.get(f"/api/gurus/{guru_id}").json()["claim_count"] == 1
    assert len(client.get("/api/claims?status=open").json()) == 1


def test_channel_match_and_idempotent_existing_source(client: TestClient, monkeypatch) -> None:
    sources = iter([_youtube(), _youtube(video="9bZkp7q19f0"), _youtube(video="9bZkp7q19f0"), _youtube()])
    monkeypatch.setattr("app.routes.links.fetch_source", lambda _url: next(sources))
    first = client.post("/api/links", json={"url": "https://youtu.be/dQw4w9WgXcQ", "guru_name": "Jane"}).json()
    second = client.post("/api/links", json={"url": "https://youtu.be/9bZkp7q19f0"}).json()
    assert second["status"] == "matched"
    assert second["matched_guru"]["id"] == first["matched_guru"]["id"]
    persisted = client.post("/api/links", json={"url": "https://youtu.be/9bZkp7q19f0", "guru_id": first["matched_guru"]["id"]}).json()
    duplicate = client.post("/api/links", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).json()
    assert duplicate["source_id"] == first["source_id"]
    assert persisted["status"] == "pending"


def test_force_new_overrides_an_identity_match(client: TestClient, monkeypatch) -> None:
    sources = iter([_youtube(), _youtube(video="9bZkp7q19f0")])
    monkeypatch.setattr("app.routes.links.fetch_source", lambda _url: next(sources))
    first = client.post(
        "/api/links",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "guru_name": "First"},
    ).json()
    second = client.post(
        "/api/links",
        json={
            "url": "https://youtu.be/9bZkp7q19f0",
            "guru_name": "Second",
            "force_new": True,
        },
    ).json()
    assert second["guru"]["name"] == "Second"
    assert second["guru"]["id"] != first["guru"]["id"]


def test_blog_domain_matches_existing_guru_without_persisting_probe(client: TestClient, monkeypatch) -> None:
    posts = iter([
        FetchedSource(type="blog", original_url="https://news.example/a", canonical_url="https://news.example/a", source_key="https://news.example/a", title="A", content="A", blog_domain="news.example"),
        FetchedSource(type="blog", original_url="https://news.example/b", canonical_url="https://news.example/b", source_key="https://news.example/b", title="B", content="B", blog_domain="news.example"),
    ])
    monkeypatch.setattr("app.routes.links.fetch_source", lambda _url: next(posts))
    first = client.post("/api/links", json={"url": "https://news.example/a", "guru_name": "Blogger"}).json()
    matched = client.post("/api/links", json={"url": "https://news.example/b"}).json()
    assert matched["status"] == "matched"
    assert matched["matched_guru"]["id"] == first["guru"]["id"]
    assert len(client.get("/api/claims").json()) == 1


def test_follow_and_resolution_filters(client: TestClient, db, monkeypatch) -> None:
    monkeypatch.setattr("app.routes.links.fetch_source", lambda _url: _youtube())
    created = client.post("/api/links", json={"url": "https://youtu.be/dQw4w9WgXcQ", "guru_name": "Jane"}).json()
    guru_id = created["matched_guru"]["id"]
    claim_id = created["claims"][0]["id"]
    toggled = client.post(f"/api/gurus/{guru_id}/follow", json={}).json()
    assert toggled["followed"] is False

    response = client.patch(
        f"/api/claims/{claim_id}/resolution",
        json={"verdict": "good", "rationale": "It rose", "benchmark": {"ticker": "SPY"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["evaluations"][-1]["verdict"] == "good"
    assert len(client.get("/api/claims?status=resolved&verdict=good").json()) == 1
    assert client.get("/api/claims?status=open").json() == []


def test_not_found_and_fetch_errors(client: TestClient, monkeypatch) -> None:
    from app.sources import SourceFetchError

    monkeypatch.setattr("app.routes.links.fetch_source", lambda _url: (_ for _ in ()).throw(SourceFetchError("no article")))
    assert client.post("/api/links", json={"url": "https://example.com/x"}).status_code == 422
    assert client.get("/api/gurus/missing").status_code == 404
    assert client.get("/api/claims/missing").status_code == 404
    assert client.post("/api/gurus/missing/follow", json={}).status_code == 404


def test_crud_status_check_rejects_invalid_state(db) -> None:
    guru = crud.create_guru(db, name="Bad state test")
    _, claim = crud.create_source_with_placeholder(
        db, guru=guru, source_type="blog", url="https://example.com", canonical_url="https://example.com/",
        source_key="https://example.com/", title="x", content="long enough", blog_domain="example.com",
    )
    claim.status = "invalid"
    try:
        db.commit()
    except Exception:
        db.rollback()
    else:
        raise AssertionError("claim status constraint should reject invalid values")
