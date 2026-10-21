from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import Analyst, Source
from app.db.session import get_db
from app.jobs.claim_finder import run_claim_finder
from app.matching import match_analyst
from app.presenters import claim_out, analyst_summary
from app.schemas import LinkCreate, LinkResponse
from app.sources import SourceFetchError, fetch_source

router = APIRouter(prefix="/api/links", tags=["links"])


@router.post("", response_model=LinkResponse)
def add_link(payload: LinkCreate, db: Session = Depends(get_db)) -> LinkResponse:
    try:
        fetched = fetch_source(str(payload.url))
    except SourceFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = crud.find_source(db, source_type=fetched.type, source_key=fetched.source_key)
    if existing:
        existing_analyst = db.get(Analyst, existing.analyst_id)
        claim = existing.claims[0] if existing.claims else None
        return LinkResponse(
            status="pending",
            source_type=existing.type,
            matched_analyst=analyst_summary(existing_analyst),
            analyst=analyst_summary(existing_analyst),
            source_id=existing.id,
            claims=[claim_out(claim)] if claim else [],
            message="Claim extraction pending" if claim and claim.extraction_status == "pending" else None,
        )

    if payload.analyst_id:
        analyst = db.get(Analyst, payload.analyst_id)
        if not analyst:
            raise HTTPException(status_code=404, detail="Analyst not found.")
    elif payload.analyst_name:
        normalized_name = payload.analyst_name.strip()
        analyst = db.scalar(select(Analyst).where(Analyst.name == normalized_name))
        if analyst is None:
            analyst = crud.create_analyst(db, name=normalized_name)
    else:
        analyst = None if payload.force_new else match_analyst(db, fetched)
        if analyst is None:
            return LinkResponse(status="requires_analyst_name", source_type=fetched.type)
        return LinkResponse(
            status="matched",
            source_type=fetched.type,
            matched_analyst=analyst_summary(analyst),
        )

    try:
        source, claim = crud.create_source_with_placeholder(
            db,
            analyst=analyst,
            source_type=fetched.type,
            url=fetched.original_url,
            canonical_url=fetched.canonical_url,
            source_key=fetched.source_key,
            title=fetched.title,
            content=fetched.content,
            published_at=fetched.published_at,
            youtube_video_id=fetched.youtube_video_id,
            youtube_channel_id=fetched.youtube_channel_id,
            blog_domain=fetched.blog_domain,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This source or analyst already exists.") from exc

    run_claim_finder(source.id)
    db.expire_all()
    persisted_source = db.get(Source, source.id)
    persisted_claims = list(persisted_source.claims) if persisted_source else [claim]
    completed = bool(persisted_claims) and all(item.extraction_status == "complete" for item in persisted_claims)
    return LinkResponse(
        status="review_ready" if completed else "pending",
        source_type=source.type,
        matched_analyst=analyst_summary(analyst),
        analyst=analyst_summary(analyst),
        source_id=source.id,
        claims=[claim_out(item) for item in persisted_claims],
        message=None if completed else "Claim extraction pending",
    )
