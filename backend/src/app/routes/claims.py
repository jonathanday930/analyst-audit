from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import crud
from app.db.session import get_db
from app.presenters import claim_out
from app.schemas import ClaimOut, ResolutionUpdate

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.get("", response_model=list[ClaimOut])
def claims(
    status: str | None = Query(default=None, pattern="^(open|resolved|expired)$"),
    verdict: str | None = Query(default=None, pattern="^(good|bad|ambiguous)$"),
    guru_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[ClaimOut]:
    return [claim_out(claim) for claim in crud.list_claims(db, status=status, verdict=verdict, guru_id=guru_id)]


@router.get("/{claim_id}", response_model=ClaimOut)
def claim_detail(claim_id: str, db: Session = Depends(get_db)) -> ClaimOut:
    claim = crud.get_claim(db, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    return claim_out(claim)


@router.patch("/{claim_id}/resolution", response_model=ClaimOut)
def resolve_claim(claim_id: str, payload: ResolutionUpdate, db: Session = Depends(get_db)) -> ClaimOut:
    claim = crud.get_claim(db, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    crud.update_claim_resolution(
        db,
        claim=claim,
        verdict=payload.verdict,
        rationale=payload.rationale,
        benchmark=payload.benchmark,
        status=payload.status,
    )
    db.commit()
    db.refresh(claim)
    return claim_out(crud.get_claim(db, claim_id))
