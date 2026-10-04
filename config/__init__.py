"""Expose the Django configuration package from the system directory."""
from pathlib import Path


_system_config = Path(__file__).resolve().parents[1] / "system" / "config"
if str(_system_config) not in __path__:
    __path__.append(str(_system_config))
