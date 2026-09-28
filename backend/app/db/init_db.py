"""Database initialization and schema creation."""

import logging
from app.db.database import Base, engine
from app.db import models  # Ensure all models are registered with Base

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Create all database tables if they do not exist."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")


if __name__ == "__main__":
    init_db()
