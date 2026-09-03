from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import Guru
from app.db.session import get_db
from app.jobs.claim_finder import run_claim_finder
from app.matching import match_guru
from app.presenters import claim_out, guru_summary
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
        existing_guru = db.get(Guru, existing.guru_id)
        claim = existing.claims[0] if existing.claims else None
        return LinkResponse(
            status="pending",
            source_type=existing.type,
            matched_guru=guru_summary(existing_guru),
            guru=guru_summary(existing_guru),
            source_id=existing.id,
            claims=[claim_out(claim)] if claim else [],
            message="Claim extraction pending" if claim and claim.extraction_status == "pending" else None,
        )

    if payload.guru_id:
        guru = db.get(Guru, payload.guru_id)
        if not guru:
            raise HTTPException(status_code=404, detail="Guru not found.")
    elif payload.guru_name:
        normalized_name = payload.guru_name.strip()
        guru = db.scalar(select(Guru).where(Guru.name == normalized_name))
        if guru is None:
            guru = crud.create_guru(db, name=normalized_name)
    else:
        guru = None if payload.force_new else match_guru(db, fetched)
        if guru is None:
            return LinkResponse(status="requires_guru_name", source_type=fetched.type)
        return LinkResponse(
            status="matched",
            source_type=fetched.type,
            matched_guru=guru_summary(guru),
        )

    try:
        source, claim = crud.create_source_with_placeholder(
            db,
            guru=guru,
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
        raise HTTPException(status_code=409, detail="This source or guru already exists.") from exc

    # Deliberately a seam only; this function is a no-op until the separately-owned finder lands.
    run_claim_finder(source.id)
    return LinkResponse(
        status="pending",
        source_type=source.type,
        matched_guru=guru_summary(guru),
        guru=guru_summary(guru),
        source_id=source.id,
        claims=[claim_out(claim)],
        message="Claim extraction pending",
    )
