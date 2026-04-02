from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def check_db_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
