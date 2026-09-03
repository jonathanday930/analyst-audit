from sqlalchemy.orm import Session

from app.db.crud import find_guru_for_source
from app.db.models import Guru
from app.sources.fetcher import FetchedSource


def match_guru(db: Session, source: FetchedSource) -> Guru | None:
    identity = source.matching_identity
    if not identity:
        return None
    return find_guru_for_source(db, source_type=source.type, identity=identity)
