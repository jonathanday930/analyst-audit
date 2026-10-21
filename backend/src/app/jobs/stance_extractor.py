from app.db import crud
from app.db.models import Source
from app.db.session import SessionLocal
from app.llm.stance_extractor import extract_stances


def run_stance_extractor(source_id: str) -> int:
    """Extract and persist non-scored position/sentiment context for one source."""
    with SessionLocal() as db:
        source = db.get(Source, source_id)
        if source is None:
            return 0
        result = extract_stances(source_text=source.content)
        for extraction in result.stances:
            crud.create_stance(db, analyst=source.analyst, source=source, extraction=extraction)
        db.commit()
        return len(result.stances)
