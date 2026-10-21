from datetime import date

from app.db import crud
from app.llm.schemas import StanceExtraction, StanceMarketSnapshot


def test_stance_crud_and_read_endpoint(client, db, monkeypatch) -> None:
    analyst = crud.create_analyst(db, name="Stance analyst")
    source, _ = crud.create_source_with_placeholder(
        db,
        analyst=analyst,
        source_type="blog",
        url="https://example.com/post",
        canonical_url="https://example.com/post",
        source_key="https://example.com/post",
        title="Market view",
        content="I am long gold.",
        published_at=date(2025, 1, 1),
        blog_domain="example.com",
    )
    stance = crud.create_stance(
        db,
        analyst=analyst,
        source=source,
        extraction=StanceExtraction(
            kind="position",
            asset_description="gold",
            suggested_ticker="GC=F",
            direction="long",
            sentiment=None,
            scope=None,
            supporting_quotes=["I am long gold."],
        ),
    )
    db.commit()
    monkeypatch.setattr(
        "app.presenters.compute_stance_snapshot",
        lambda **_: StanceMarketSnapshot(
            ticker="GC=F", call_date=date(2025, 1, 1), as_of=date(2026, 1, 1), days_since_call=365,
            call_price=1.0, current_price=2.0, high_since_call=2.0, high_date=date(2026, 1, 1),
            low_since_call=1.0, low_date=date(2025, 1, 1), change_since_call_pct=100.0,
        ),
    )
    response = client.get(f"/api/analysts/{analyst.id}/stances")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == stance.id
    assert body[0]["direction"] == "long"
    assert body[0]["snapshot"]["ticker"] == "GC=F"

