from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import crud
from app.db.session import get_db
from app.presenters import claim_out, guru_summary
from app.schemas import ClaimOut, FollowRequest, GuruDetail, GuruSummary, SourceSummary

router = APIRouter(prefix="/api/gurus", tags=["gurus"])


@router.get("", response_model=list[GuruSummary])
def gurus(followed: bool | None = None, db: Session = Depends(get_db)) -> list[GuruSummary]:
    return [guru_summary(guru) for guru in crud.list_gurus(db, followed=followed)]


@router.get("/{guru_id}", response_model=GuruDetail)
def guru_detail(guru_id: str, db: Session = Depends(get_db)) -> GuruDetail:
    guru = crud.get_guru(db, guru_id)
    if not guru:
        raise HTTPException(status_code=404, detail="Guru not found.")
    return GuruDetail(
        id=guru.id,
        name=guru.name,
        followed=guru.followed,
        claim_count=len(guru.claims),
        sources=[SourceSummary.model_validate(source) for source in guru.sources],
        claims=[claim_out(claim) for claim in guru.claims],
    )


@router.post("/{guru_id}/follow", response_model=GuruSummary)
def follow(guru_id: str, payload: FollowRequest, db: Session = Depends(get_db)) -> GuruSummary:
    guru = db.get(crud.Guru, guru_id)
    if not guru:
        raise HTTPException(status_code=404, detail="Guru not found.")
    guru.followed = not guru.followed if payload.followed is None else payload.followed
    db.commit()
    return guru_summary(guru)
