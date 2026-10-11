"""Configuration loaded from the repository, independent of working directory."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(os.getenv("SMARTCOURSE_ENV_FILE", str(ROOT_DIR / ".env")), override=False)


def env_int(name, default, minimum=1, maximum=100000):
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"Invalid configuration for {name}.")
    return value


def get_settings():
    return {
        "HOST": os.getenv("HOST", "127.0.0.1"),
        "PORT": env_int("PORT", 5000, maximum=65535),
        "DEBUG": os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"},
        "MAX_MESSAGE_LENGTH": env_int("MAX_MESSAGE_LENGTH", 4000),
        "MEMORY_MESSAGES": env_int("MEMORY_MESSAGES", 20, maximum=30),
        "MAX_CONTENT_LENGTH": 32768,
    }
