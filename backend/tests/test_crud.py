from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import crud


def _source(db: Session, name: str = "Analyst", channel: str = "UC123"):
    analyst = crud.create_analyst(db, name=name)
    source, claim = crud.create_source_with_placeholder(
        db,
        analyst=analyst,
        source_type="video",
        url="https://youtu.be/dQw4w9WgXcQ",
        canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        source_key="dQw4w9WgXcQ",
        title="Video",
        content="Transcript",
        published_at=date(2026, 1, 1),
        youtube_video_id="dQw4w9WgXcQ",
        youtube_channel_id=channel,
    )
    db.commit()
    return analyst, source, claim


def test_create_list_get_and_match(db: Session) -> None:
    analyst, source, claim = _source(db)
    assert crud.get_analyst(db, analyst.id).sources[0].id == source.id
    assert crud.find_analyst_for_source(db, source_type="video", identity="UC123").id == analyst.id
    assert crud.find_source(db, source_type="video", source_key="dQw4w9WgXcQ").id == source.id
    assert crud.list_claims(db, status="open")[0].id == claim.id
    assert claim.extraction_status == "pending"
    assert claim.asset_description is None


def test_resolution_history_and_verdict_filter(db: Session) -> None:
    _, _, claim = _source(db)
    crud.update_claim_resolution(db, claim=claim, verdict="good", rationale="Rose", benchmark={"ticker": "SPY"})
    db.commit()
    loaded = crud.get_claim(db, claim.id)
    assert loaded.status == "resolved"
    assert loaded.evaluations[-1].verdict == "good"
    assert crud.list_claims(db, verdict="good")[0].id == claim.id
    crud.update_claim_resolution(db, claim=claim, verdict="bad", rationale="Later check")
    db.commit()
    assert crud.list_claims(db, verdict="good") == []
    assert crud.list_claims(db, verdict="bad")[0].id == claim.id


def test_duplicate_source_is_rejected(db: Session) -> None:
    analyst, _, _ = _source(db)
    try:
        crud.create_source_with_placeholder(
            db, analyst=analyst, source_type="video", url="x", canonical_url="x",
            source_key="dQw4w9WgXcQ", title="duplicate", content="x",
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    else:
        raise AssertionError("duplicate source should violate its unique constraint")
