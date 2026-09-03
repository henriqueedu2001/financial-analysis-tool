from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from finance.db.bootstrap import create_schema
from finance.db.session import create_db_engine, create_session_factory


@pytest.fixture
def db_session(tmp_path) -> Iterator[Session]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.sqlite'}")
    create_schema(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        yield session
    engine.dispose()
