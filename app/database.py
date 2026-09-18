"""Configuración de la base de datos.

Usa la variable de entorno DATABASE_URL:
    - Si no está definida, usa SQLite local (taller.db) para desarrollo.
    - Railway inyecta automáticamente una URL de PostgreSQL en producción.

No hace falta tocar este archivo para pasar de SQLite a PostgreSQL.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

DATABASE_URL = settings.DATABASE_URL

# Railway (y algunos proveedores) entregan la URL como "postgres://...",
# pero SQLAlchemy 2.x requiere el prefijo "postgresql://".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: entrega una sesión de base de datos por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
