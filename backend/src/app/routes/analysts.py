from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import crud
from app.db.session import get_db
from app.presenters import claim_out, analyst_summary
from app.schemas import ClaimOut, FollowRequest, AnalystDetail, AnalystSummary, SourceSummary

router = APIRouter(prefix="/api/analysts", tags=["analysts"])


@router.get("", response_model=list[AnalystSummary])
def analysts(followed: bool | None = None, db: Session = Depends(get_db)) -> list[AnalystSummary]:
    return [analyst_summary(analyst) for analyst in crud.list_analysts(db, followed=followed)]


@router.get("/{analyst_id}", response_model=AnalystDetail)
def analyst_detail(analyst_id: str, db: Session = Depends(get_db)) -> AnalystDetail:
    analyst = crud.get_analyst(db, analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found.")
    return AnalystDetail(
        id=analyst.id,
        name=analyst.name,
        followed=analyst.followed,
        claim_count=len(analyst.claims),
        sources=[SourceSummary.model_validate(source) for source in analyst.sources],
        claims=[claim_out(claim) for claim in analyst.claims],
    )


@router.post("/{analyst_id}/follow", response_model=AnalystSummary)
def follow(analyst_id: str, payload: FollowRequest, db: Session = Depends(get_db)) -> AnalystSummary:
    analyst = db.get(crud.Analyst, analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found.")
    analyst.followed = not analyst.followed if payload.followed is None else payload.followed
    db.commit()
    return analyst_summary(analyst)
