from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import Analyst
from app.db.session import get_db
from app.presenters import analyst_summary, category_scores, claim_out, meta_analysis, stance_out
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
    analysis = meta_analysis(analyst)
    summary = analyst_summary(analyst, analysis=analysis)
    return AnalystDetail(
        id=analyst.id,
        name=analyst.name,
        followed=analyst.followed,
        claim_count=summary.claim_count,
        resolved_count=summary.resolved_count,
        open_count=summary.open_count,
        last_active_at=summary.last_active_at,
        primary_source_type=summary.primary_source_type,
        reliability_score=summary.reliability_score,
        categories=category_scores(analyst, analysis),
        sources=[SourceSummary.model_validate(source) for source in analyst.sources],
        claims=[claim_out(claim) for claim in analyst.claims],
        stances=[stance_out(stance) for stance in analyst.stances],
        overall_summary=analysis.overall_summary if analysis else None,
        strengths=analysis.strengths if analysis else [],
        weaknesses=analysis.weaknesses if analysis else [],
        consistency_notes=analysis.consistency_notes if analysis else None,
    )


@router.get("/{analyst_id}/stances")
def analyst_stances(analyst_id: str, db: Session = Depends(get_db)):
    if not db.get(Analyst, analyst_id):
        raise HTTPException(status_code=404, detail="Analyst not found.")
    return [stance_out(stance) for stance in crud.list_stances(db, analyst_id=analyst_id)]


@router.post("/{analyst_id}/follow", response_model=AnalystSummary)
def follow(analyst_id: str, payload: FollowRequest, db: Session = Depends(get_db)) -> AnalystSummary:
    analyst = db.get(crud.Analyst, analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found.")
    analyst.followed = not analyst.followed if payload.followed is None else payload.followed
    db.commit()
    return analyst_summary(analyst)
