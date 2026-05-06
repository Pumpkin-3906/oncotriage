"""SQLAlchemy 引擎 + Session 工厂"""
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=(settings.app_env == "dev"),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """所有 ORM 模型继承自此"""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
