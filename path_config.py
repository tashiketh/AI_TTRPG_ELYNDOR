# path_config.py
import os
from pathlib import Path

class PathConfig:
    def __init__(self, base_dir=None):
        if base_dir is None:
            self.base_dir = Path(__file__).parent
        else:
            self.base_dir = Path(base_dir)

        # Define all paths relative to base directory
        self.logs_dir = self.base_dir / "logs"
        self.references_dir = self.base_dir / "references"
        self.models_dir = self.base_dir / "models"

        # Create directories if they don't exist
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories if they don't exist"""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.references_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @property
    def game_state_path(self):
        return self.logs_dir / "game_state.json"

    @property
    def combat_state_path(self):
        return self.logs_dir / "current_combat_state.json"

    @property
    def combat_map_path(self):
        return self.logs_dir / "current_combat_map.json"

    @property
    def enemies_path(self):
        return self.references_dir / "enemies.json"

    @property
    def crafting_path(self):
        return self.references_dir / "craft.json"

    @property
    def magic_path(self):
        return self.references_dir / "magic.json"

    @property
    def spell_library_path(self):
        return self.references_dir / "spell_library.json"

    @property
    def racial_bias_path(self):
        return self.references_dir / "racial_bias.csv"

    @property
    def racial_profiles_path(self):
        return self.references_dir / "racial_profiles.json"

    @property
    def base_stats_path(self):
        return self.references_dir / "base_stats.json"

    @property
    def items_path(self):
        return self.references_dir / "items.csv"

    @property
    def skills_path(self):
        return self.references_dir / "skills.csv"

    @property
    def dc_reference_path(self):
        return self.references_dir / "DC.json"

    @property
    def backup_dir(self):
        return self.logs_dir / "backup"

# Initialize global path configuration
path_config = PathConfig()

# Update all files to use path_config instead of hardcoded paths
