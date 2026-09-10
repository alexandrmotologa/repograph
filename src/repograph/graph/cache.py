"""Graph serialization and incremental cache management."""

import json
import logging
from pathlib import Path

from repograph.models import ParsedFile

logger = logging.getLogger(__name__)


class GraphCache:
    """Manages serialization of parsed files and graph metadata to disk for sub-second reloads."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / "cache.json"

    def load(self) -> tuple[dict[str, ParsedFile], dict[str, str]]:
        """Load cached parsed files and their content hashes.

        Returns (parsed_files, file_hashes).
        """
        if not self.cache_file.exists():
            return {}, {}

        try:
            with open(self.cache_file, encoding="utf-8") as f:
                data = json.load(f)

            hashes: dict[str, str] = data.get("hashes", {})
            raw_files: dict[str, dict] = data.get("files", {})
            parsed_files: dict[str, ParsedFile] = {}

            for path, p_data in raw_files.items():
                parsed_files[path] = ParsedFile.model_validate(p_data)

            return parsed_files, hashes
        except Exception as e:
            logger.warning("Failed to load repograph cache: %s. Starting fresh.", e)
            return {}, {}

    def save(self, parsed_files: dict[str, ParsedFile]) -> None:
        """Save parsed files and their hashes to disk."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            hashes = {path: pf.content_hash for path, pf in parsed_files.items()}
            files_dict = {path: pf.model_dump() for path, pf in parsed_files.items()}

            data = {
                "version": "1.0",
                "hashes": hashes,
                "files": files_dict,
            }

            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save repograph cache: %s", e)
