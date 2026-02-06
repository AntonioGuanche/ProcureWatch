"""Pytest configuration. Set DATABASE_URL before any test module imports app."""
import os

# Use a single test database so all tests that use the global engine see the same DB.
# Set as early as possible so app.db.session creates the engine with this URL.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test.db")
