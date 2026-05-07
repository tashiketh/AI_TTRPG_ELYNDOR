# path_config.py
from pathlib import Path

class PathConfig:
    def __init__(self, base_dir=None):
        self.core_dir = Path(__file__).resolve().parent
        if base_dir is None:
            self.base_dir = self.core_dir.parent
        else:
            self.base_dir = Path(base_dir).resolve()

        # Define shared data paths relative to the project root.
        self.logs_dir = self.base_dir / "logs"
        self.references_dir = self.base_dir / "references"
        self.models_dir = self.base_dir / "models"
        self.templates_dir = self.base_dir / "templates"
        self.static_dir = self.base_dir / "static"

        # Create directories if they don't exist
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories if they don't exist"""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.references_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def assert_not_reference_write(self, target_path):
        """Raise if live code tries to write into the read-only references directory."""
        target = Path(target_path).resolve()
        references = self.references_dir.resolve()
        if target == references or references in target.parents:
            raise PermissionError(
                f"Refusing to write to read-only reference data: {target}. "
                f"Write live game state to {self.logs_dir} instead."
            )

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
        return self.skill_dc_reference_path

    @property
    def skill_dc_reference_path(self):
        return self.references_dir / "skills_with_dc.json"

    @property
    def trust_reference_path(self):
        return self.references_dir / "trust.json"

    @property
    def backup_dir(self):
        return self.logs_dir / "backup"

    @property
    def story_bible_path(self):
        return self.core_dir / "Story_bible.txt"

# Initialize global path configuration
path_config = PathConfig()
