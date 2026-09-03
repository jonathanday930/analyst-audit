from sqlalchemy.orm import Session

from app.db.crud import find_analyst_for_source
from app.db.models import Analyst
from app.sources.fetcher import FetchedSource


def match_analyst(db: Session, source: FetchedSource) -> Analyst | None:
    identity = source.matching_identity
    if not identity:
        return None
    return find_analyst_for_source(db, source_type=source.type, identity=identity)
