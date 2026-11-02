"""Export the published JSON Schemas under schemas/ (FR-016).

Why: consumers (the player, integrations, third parties) validate against files in
the repo, and a test keeps them equal to what the models generate.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from audio_smith.blocks import BlockDoc
from audio_smith.paths import atomic_write
from audio_smith.profiles.loader import json_schema as profile_json_schema
from audio_smith.publish.manifest import Manifest
from audio_smith.script.markdown import ScriptMeta
from audio_smith.voices.registry import VoiceRecord

SCHEMA_BASE_URL = "https://getaudiosmith.com/schemas"
MODELS: dict[str, tuple[type[BaseModel], str]] = {
    "manifest": (Manifest, "audio-smith/manifest@1"),
    "blocks": (BlockDoc, "audio-smith/blocks@1"),
    "script": (ScriptMeta, "audio-smith/script@1"),
    "voice": (VoiceRecord, "audio-smith/voice@1"),
}


def schema_text(name: str) -> str:
    """Return the deterministic JSON text of one published schema."""
    if name == "profile":
        return profile_json_schema()
    model, title = MODELS[name]
    schema = model.model_json_schema(by_alias=True)
    schema["$id"] = f"{SCHEMA_BASE_URL}/{name}.schema.json"
    schema["title"] = title
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def export_all(dest: Path) -> list[Path]:
    """Write every published schema into dest and return the paths."""
    return [atomic_write(dest / f"{name}.schema.json", schema_text(name)) for name in (*MODELS, "profile")]
