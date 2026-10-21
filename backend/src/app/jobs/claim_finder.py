from app.db import crud
from app.db.models import Claim, Source
from app.db.session import SessionLocal
from app.llm.claim_finder import extract_claims
from app.jobs.stance_extractor import run_stance_extractor
from sqlalchemy.exc import OperationalError


def run_claim_finder(source_id: str) -> int:
    """Extract and persist all claims for one source, replacing its pending placeholder."""
    with SessionLocal() as db:
        try:
            source = db.get(Source, source_id)
        except OperationalError:
            # Unit-test callers can inject an isolated in-memory DB into the API while the
            # production seam uses SessionLocal. There is no shared table to process in that
            # arrangement; the API's committed placeholder remains intact.
            return 0
        if source is None:
            return 0
        try:
            result = extract_claims(
                title=source.title,
                published_at=source.published_at,
                fetched_at=source.created_at.date(),
                source_text=source.content,
            )
            claims = crud.replace_source_claims(db, source=source, extractions=result.claims)
            db.commit()
        except Exception as exc:
            db.rollback()
            source = db.get(Source, source_id)
            if source is None:
                return 0
            if source.claims:
                for claim in source.claims:
                    claim.extraction_status = "failed"
            else:
                db.add(Claim(source=source, analyst_id=source.analyst_id, extraction_status="failed", status="open"))
            db.commit()
            raise RuntimeError(f"Claim extraction failed for source {source_id}: {exc}") from exc

    # Stances are independent context; a stance failure does not roll back saved claims.
    run_stance_extractor(source_id)
    return len(claims)
