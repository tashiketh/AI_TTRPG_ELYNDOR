# logging_system.py
import json
import os
import shutil
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from path_config import path_config

# Log categories and their file prefixes
LOG_CATEGORIES = {
    "combat": "combat",
    "social": "social",
    "quest": "quest",
    "crafting": "crafting",
    "inventory": "inventory",
    "magic": "magic",
    "system": "system",
    "error": "error",
    "session": "session"
}

# Log verbosity levels
LOG_LEVELS = {
    "debug": 0,
    "info": 1,
    "warning": 2,
    "error": 3,
    "critical": 4
}

class LoggingSystem:
    def __init__(self, max_log_size: int = 1000, max_backups: int = 5):
        """
        Initialize the logging system.

        Args:
            max_log_size: Maximum number of entries per log file
            max_backups: Maximum number of backup files to keep
        """
        self.max_log_size = max_log_size
        self.max_backups = max_backups
        self.current_logs = {category: [] for category in LOG_CATEGORIES}

        # Ensure log directory exists
        path_config.logs_dir.mkdir(parents=True, exist_ok=True)

        # Load existing logs if they exist
        self._load_existing_logs()

    def _load_existing_logs(self):
        """Load existing log files if they exist."""
        for category, prefix in LOG_CATEGORIES.items():
            log_file = path_config.logs_dir / f"{prefix}_log.json"
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        self.current_logs[category] = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"Warning: Could not load {category} log: {e}")
                    self.current_logs[category] = []

    def _save_logs(self, category: str):
        """Save logs for a specific category to file."""
        if not self.current_logs[category]:
            return

        log_file = path_config.logs_dir / f"{LOG_CATEGORIES[category]}_log.json"

        # Create backup if file exists and is not empty
        if log_file.exists() and log_file.stat().st_size > 0:
            self._create_backup(log_file)

        # Save current logs
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(self.current_logs[category], f, indent=2)

        # Clear current logs after saving
        self.current_logs[category] = []

    def _create_backup(self, log_file: Path):
        """Create a backup of a log file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = path_config.logs_dir / f"{log_file.stem}_{timestamp}.json.bak"

        # Rotate backups if we have too many
        backups = sorted(
            log_file.parent.glob(f"{log_file.stem}_*.json.bak"),
            key=os.path.getmtime,
            reverse=True
        )

        # Remove oldest backups if we have too many
        for old_backup in backups[self.max_backups:]:
            old_backup.unlink()

        # Create new backup
        shutil.copy(log_file, backup_file)

    def _add_log_entry(self, category: str, entry: Dict):
        """Add a log entry to the specified category."""
        self.current_logs[category].append(entry)

        # Save logs if we've reached the maximum size
        if len(self.current_logs[category]) >= self.max_log_size:
            self._save_logs(category)

    def _create_log_entry(self, category: str, level: str, message: str,
                         context: Dict = None, timestamp: str = None) -> Dict:
        """Create a standardized log entry."""
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        entry = {
            "timestamp": timestamp,
            "category": category,
            "level": level,
            "message": message,
            "context": context or {}
        }

        return entry

    def log_combat_action(self, action: str, participant: str, target: str = None,
                         result: Dict = None, context: Dict = None):
        """
        Log a combat action.

        Args:
            action: Type of action (attack, spell, block, etc.)
            participant: Entity performing the action
            target: Entity targeted (if applicable)
            result: Result of the action
            context: Additional context
        """
        context = context or {}
        context.update({
            "action": action,
            "participant": participant,
            "target": target,
            "result": result
        })

        entry = self._create_log_entry(
            "combat",
            "info",
            f"{participant} performed {action}" + (f" on {target}" if target else ""),
            context
        )

        self._add_log_entry("combat", entry)

    def log_social_interaction(self, npc_id: str, interaction_type: str,
                              result: Dict, context: Dict = None):
        """
        Log a social interaction.

        Args:
            npc_id: ID of the NPC involved
            interaction_type: Type of interaction
            result: Result of the interaction
            context: Additional context
        """
        context = context or {}
        context.update({
            "npc_id": npc_id,
            "interaction_type": interaction_type,
            "result": result
        })

        npc_name = context.get("npc_name", npc_id)
        trust_change = result.get("trust_change", 0)
        old_relationship = result.get("old_relationship", "unknown")
        new_relationship = result.get("new_relationship", "unknown")

        message = f"Social interaction with {npc_name}: {interaction_type} " + \
                 f"(Trust: {old_relationship} → {new_relationship}, Δ{trust_change:.1f})"

        entry = self._create_log_entry(
            "social",
            "info",
            message,
            context
        )

        self._add_log_entry("social", entry)

    def log_quest_event(self, quest_id: str, event_type: str,
                       details: Dict = None, context: Dict = None):
        """
        Log a quest-related event.

        Args:
            quest_id: ID of the quest
            event_type: Type of event (accepted, completed, failed, etc.)
            details: Details about the event
            context: Additional context
        """
        context = context or {}
        context.update({
            "quest_id": quest_id,
            "event_type": event_type,
            "details": details
        })

        quest_title = context.get("quest_title", quest_id)
        message = f"Quest '{quest_title}': {event_type}"

        entry = self._create_log_entry(
            "quest",
            "info",
            message,
            context
        )

        self._add_log_entry("quest", entry)

    def log_crafting_event(self, item_id: str, crafting_type: str,
                          result: Dict, context: Dict = None):
        """
        Log a crafting event.

        Args:
            item_id: ID of the item crafted
            crafting_type: Type of crafting
            result: Result of the crafting attempt
            context: Additional context
        """
        context = context or {}
        context.update({
            "item_id": item_id,
            "crafting_type": crafting_type,
            "result": result
        })

        item_name = context.get("item_name", item_id)
        quality = result.get("quality", "unknown")
        message = f"Crafted {item_name} ({crafting_type}): {quality} quality"

        entry = self._create_log_entry(
            "crafting",
            "info",
            message,
            context
        )

        self._add_log_entry("crafting", entry)

    def log_inventory_event(self, action: str, item_id: str,
                           result: Dict, context: Dict = None):
        """
        Log an inventory event.

        Args:
            action: Type of action (add, remove, equip, etc.)
            item_id: ID of the item
            result: Result of the action
            context: Additional context
        """
        context = context or {}
        context.update({
            "action": action,
            "item_id": item_id,
            "result": result
        })

        item_name = context.get("item_name", item_id)
        message = f"Inventory: {action} {item_name}"

        entry = self._create_log_entry(
            "inventory",
            "info",
            message,
            context
        )

        self._add_log_entry("inventory", entry)

    def log_magic_event(self, spell_name: str, event_type: str,
                       result: Dict, context: Dict = None):
        """
        Log a magic-related event.

        Args:
            spell_name: Name of the spell
            event_type: Type of event (cast, learned, studied, etc.)
            result: Result of the event
            context: Additional context
        """
        context = context or {}
        context.update({
            "spell_name": spell_name,
            "event_type": event_type,
            "result": result
        })

        message = f"Magic: {event_type} {spell_name}"

        entry = self._create_log_entry(
            "magic",
            "info",
            message,
            context
        )

        self._add_log_entry("magic", entry)

    def log_system_event(self, event_type: str, message: str,
                        context: Dict = None, level: str = "info"):
        """
        Log a system event.

        Args:
            event_type: Type of system event
            message: Description of the event
            context: Additional context
            level: Log level
        """
        context = context or {}
        context.update({
            "event_type": event_type
        })

        entry = self._create_log_entry(
            "system",
            level,
            f"System: {message}",
            context
        )

        self._add_log_entry("system", entry)

    def log_error(self, error_type: str, message: str,
                 context: Dict = None, exception: Exception = None):
        """
        Log an error.

        Args:
            error_type: Type of error
            message: Error message
            context: Additional context
            exception: Exception object (if applicable)
        """
        context = context or {}
        context.update({
            "error_type": error_type,
            "exception_type": type(exception).__name__ if exception else None,
            "exception_message": str(exception) if exception else None
        })

        entry = self._create_log_entry(
            "error",
            "error",
            f"Error ({error_type}): {message}",
            context
        )

        self._add_log_entry("error", entry)

    def log_session_event(self, event_type: str, message: str,
                         context: Dict = None, level: str = "info"):
        """
        Log a session-level event.

        Args:
            event_type: Type of session event
            message: Description of the event
            context: Additional context
            level: Log level
        """
        context = context or {}
        context.update({
            "event_type": event_type
        })

        entry = self._create_log_entry(
            "session",
            level,
            f"Session: {message}",
            context
        )

        self._add_log_entry("session", entry)

    def save_all_logs(self):
        """Save all current logs to their respective files."""
        for category in self.current_logs:
            if self.current_logs[category]:
                self._save_logs(category)

    def get_recent_logs(self, category: str = None, limit: int = 20) -> List[Dict]:
        """
        Get recent log entries.

        Args:
            category: Specific category to get logs from (None for all)
            limit: Maximum number of entries to return

        Returns:
            List of log entries
        """
        if category:
            categories = [category] if category in self.current_logs else []
        else:
            categories = list(self.current_logs.keys())

        recent_logs = []
        for cat in categories:
            # Get from memory first
            if self.current_logs[cat]:
                recent_logs.extend(self.current_logs[cat][-limit:])

            # Try to load from file if we need more
            if len(recent_logs) < limit:
                log_file = path_config.logs_dir / f"{LOG_CATEGORIES[cat]}_log.json"
                if log_file.exists():
                    try:
                        with open(log_file, "r", encoding="utf-8") as f:
                            file_logs = json.load(f)
                            recent_logs.extend(file_logs[- (limit - len(recent_logs)):])
                    except (json.JSONDecodeError, OSError):
                        pass

        # Sort by timestamp (newest first)
        recent_logs.sort(key=lambda x: x["timestamp"], reverse=True)

        return recent_logs[:limit]

    def get_log_summary(self) -> Dict:
        """
        Get a summary of all logs.

        Returns:
            Dictionary with log statistics
        """
        summary = {
            "categories": {},
            "total_entries": 0,
            "by_level": {}
        }

        # Count entries in memory
        for category, logs in self.current_logs.items():
            summary["categories"][category] = len(logs)
            summary["total_entries"] += len(logs)

            for log in logs:
                level = log.get("level", "info")
                summary["by_level"][level] = summary["by_level"].get(level, 0) + 1

        # Count entries in files
        for category, prefix in LOG_CATEGORIES.items():
            log_file = path_config.logs_dir / f"{prefix}_log.json"
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        file_logs = json.load(f)
                        summary["categories"][category] = summary["categories"].get(category, 0) + len(file_logs)
                        summary["total_entries"] += len(file_logs)

                        for log in file_logs:
                            level = log.get("level", "info")
                            summary["by_level"][level] = summary["by_level"].get(level, 0) + 1
                except (json.JSONDecodeError, OSError):
                    pass

        return summary

    def clear_logs(self, category: str = None):
        """
        Clear logs for a specific category or all categories.

        Args:
            category: Specific category to clear (None for all)
        """
        if category:
            categories = [category] if category in self.current_logs else []
        else:
            categories = list(self.current_logs.keys())

        for cat in categories:
            self.current_logs[cat] = []

            # Also clear the log file
            log_file = path_config.logs_dir / f"{LOG_CATEGORIES[cat]}_log.json"
            if log_file.exists():
                try:
                    log_file.unlink()
                except OSError as e:
                    print(f"Warning: Could not clear {cat} log file: {e}")

    def export_logs(self, format: str = "json", category: str = None) -> str:
        """
        Export logs in a specific format.

        Args:
            format: Format to export ("json" or "text")
            category: Specific category to export (None for all)

        Returns:
            Exported logs as string
        """
        if category:
            categories = [category] if category in self.current_logs else []
        else:
            categories = list(self.current_logs.keys())

        all_logs = []
        for cat in categories:
            # Get from memory
            all_logs.extend(self.current_logs[cat])

            # Get from file
            log_file = path_config.logs_dir / f"{LOG_CATEGORIES[cat]}_log.json"
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        all_logs.extend(json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass

        # Sort by timestamp
        all_logs.sort(key=lambda x: x["timestamp"])

        if format == "json":
            return json.dumps(all_logs, indent=2)
        else:  # text format
            text_lines = []
            for log in all_logs:
                timestamp = log.get("timestamp", "unknown")
                category = log.get("category", "unknown")
                level = log.get("level", "info")
                message = log.get("message", "")
                text_lines.append(f"[{timestamp}] [{category.upper()}] [{level.upper()}] {message}")

            return "\n".join(text_lines)

# Global logging system instance
logging_system = LoggingSystem()

# Integration with combat_tools.py
def integrate_combat_logging():
    """Patch combat_tools.py to use the logging system."""
    import combat_tools

    original_resolve_attack = combat_tools.CombatTools.resolve_attack
    original_resolve_spell = combat_tools.CombatTools.resolve_spell
    original_resolve_block = combat_tools.CombatTools.resolve_block

    def patched_resolve_attack(self, attacker_id, target_id, style="normal", weapon_id=None):
        result = original_resolve_attack(self, attacker_id, target_id, style, weapon_id)

        # Log the combat action
        attacker_key = self.resolve_combat_key(attacker_id)
        target_key = self.resolve_combat_key(target_id)

        context = {
            "attacker": attacker_key,
            "target": target_key,
            "style": style,
            "weapon_id": weapon_id,
            "damage": result.get("final_damage", 0),
            "block_success": result.get("block_success", False),
            "current_second": self.state["current_second"]
        }

        logging_system.log_combat_action(
            "attack",
            attacker_key,
            target_key,
            result,
            context
        )

        return result

    def patched_resolve_spell(self, caster_id, spell_key, target_id=None, target_pos=None, charge_percent=100.0):
        result = original_resolve_spell(self, caster_id, spell_key, target_id, target_pos, charge_percent)

        # Log the spell casting
        caster_key = self.resolve_combat_key(caster_id)

        context = {
            "caster": caster_key,
            "spell": spell_key,
            "target": target_id,
            "target_pos": target_pos,
            "charge_percent": charge_percent,
            "mp_cost": result.get("mp_cost", 0),
            "current_second": self.state["current_second"]
        }

        logging_system.log_combat_action(
            "spell",
            caster_key,
            target_id,
            result,
            context
        )

        return result

    def patched_resolve_block(self, entity_id, item_id=None):
        result = original_resolve_block(self, entity_id, item_id)

        # Log the block action
        entity_key = self.resolve_combat_key(entity_id)

        context = {
            "entity": entity_key,
            "item_id": item_id,
            "block_item": result.get("block_item", "unknown"),
            "block_hp": result.get("block_hp", 0),
            "current_second": self.state["current_second"]
        }

        logging_system.log_combat_action(
            "block",
            entity_key,
            None,
            result,
            context
        )

        return result

    # Apply patches
    combat_tools.CombatTools.resolve_attack = patched_resolve_attack
    combat_tools.CombatTools.resolve_spell = patched_resolve_spell
    combat_tools.CombatTools.resolve_block = patched_resolve_block

# Initialize combat logging integration
integrate_combat_logging()

# Example usage
if __name__ == "__main__":
    # Test logging system
    print("=== Testing Logging System ===")

    # Log some test events
    logging_system.log_social_interaction(
        "npc_kraelra",
        "gift",
        {
            "success": True,
            "trust_change": 2.5,
            "old_relationship": "friend",
            "new_relationship": "close friend"
        },
        {
            "npc_name": "Kraelra",
            "gift_value": 100,
            "location": "camp"
        }
    )

    logging_system.log_quest_event(
        "quest_hunt_wolves",
        "completed",
        {
            "rewards": {
                "gold": 500,
                "reputation": 8,
                "items": ["wolf pelt cloak"]
            }
        },
        {
            "quest_title": "Wolf Pack Culling",
            "location": "Blackthorn Forest"
        }
    )

    logging_system.log_crafting_event(
        "steel_sword_001",
        "smithing",
        {
            "success": True,
            "quality": "fine"
        },
        {
            "item_name": "Steel Sword",
            "materials": ["steel", "leather"],
            "tools_quality": "high_quality"
        }
    )

    # Get recent logs
    recent_logs = logging_system.get_recent_logs()
    print(f"\nRecent logs ({len(recent_logs)} entries):")
    for log in recent_logs:
        print(f"[{log['timestamp']}] [{log['category'].upper()}] {log['message']}")

    # Get log summary
    summary = logging_system.get_log_summary()
    print(f"\nLog summary:")
    print(f"Total entries: {summary['total_entries']}")
    for category, count in summary['categories'].items():
        print(f"  {category}: {count} entries")

    # Save all logs
    logging_system.save_all_logs()
    print("\nLogs saved to files.")
