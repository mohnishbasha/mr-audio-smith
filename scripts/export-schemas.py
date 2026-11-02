"""Regenerate schemas/*.schema.json from the pydantic models."""

from pathlib import Path

from audio_smith.publish.schemas import export_all

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

if __name__ == "__main__":
    export_all(SCHEMAS_DIR)
