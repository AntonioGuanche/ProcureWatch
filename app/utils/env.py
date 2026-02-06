"""Environment variable loading utilities for CLI scripts."""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def load_env_if_present(env_file: Optional[str] = None) -> bool:
    """
    Load .env file if python-dotenv is available and file exists.
    
    Args:
        env_file: Path to .env file (default: .env in project root)
    
    Returns:
        True if .env was loaded, False otherwise (no error if dotenv missing)
    
    Never prints secret values. Safe to call at module level in CLI scripts.
    """
    if env_file is None:
        # Find project root (where this file is: app/utils/env.py -> project root)
        project_root = Path(__file__).resolve().parent.parent.parent
        env_file = str(project_root / ".env")
    
    env_path = Path(env_file)
    if not env_path.exists():
        return False
    
    try:
        from dotenv import load_dotenv
        # override=False: don't overwrite existing env vars (CLI args take precedence)
        loaded = load_dotenv(env_file, override=False)
        if loaded:
            logger.debug("Loaded environment variables from %s", env_file)
        return loaded
    except ImportError:
        # python-dotenv not installed - that's OK, just skip loading
        logger.debug("python-dotenv not available, skipping .env loading")
        return False
    except Exception as e:
        # Don't crash on .env loading errors (malformed file, etc.)
        logger.warning("Failed to load .env file %s: %s", env_file, e)
        return False
