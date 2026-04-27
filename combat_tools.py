# combat_tools.py
import json
import os
import glob
import shutil
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
from path_config import path_config

from helper_functions import roll_generic_check
from crafting import calculate_spell_cast_time, is_spell_learned, normalize_spell_collection
from map_tools import initialize_combat_map, add_entity, move_entity, get_current_map, end_combat as map_end_combat, get_distance_meters

class CombatTools:
    def __init__(self):
        self.state = self._load_combat_state()
        self.enemy_templates = self._load_enemies()

    # ==================== STATE MANAGEMENT ====================
    def _load_combat_state(self) -> Dict:
        """Load combat state from file with fallback to default."""
        if path_config.combat_state_path.exists():
            try:
                with open(path_config.combat_state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Could not load combat state: {e}")
        return {"active": False, "current_second": 0.0, "participants": {}, "map_linked": False, "log": []}

    def _load_enemies(self) -> Dict:
        """Load enemy templates from file."""
        try:
            with open(path_config.enemies_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {enemy["name"].strip(): enemy for enemy in data.get("enemies", [])}
        except Exception as e:
            print(f"Warning: Could not load enemies.json: {e}")
            return {}

    def _save_combat_state(self, state: Dict) -> None:
        """Save combat state with backup."""
        state["last_updated"] = datetime.now().isoformat()
        self._backup_and_save_combat(state)

    def _backup_and_save_combat(self, state: Dict) -> None:
        """Create backup then overwrite combat state file."""
        if path_config.combat_state_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = path_config.backup_dir / f"combat_state_backup_{ts}.json"
            shutil.copy(path_config.combat_state_path, backup_path)

            # Keep only 5 newest backups
            backups = sorted(
                path_config.backup_dir.glob("combat_state_backup_*.json"),
                key=os.path.getmtime,
                reverse=True
            )
            for old in backups[5:]:
                old.unlink()

        with open(path_config.combat_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    # ==================== NEW COMBAT METHODS ====================
    def get_combat_participants(self):
        """Get all participants in current combat"""
        return self.state.get('participants', {})

    def add_combat_participant(self, unit_data, team='enemy'):
        """Add unit to combat with proper structure"""
        combat_id = f"{team}_{len(self.state.get('participants', {})) + 1}"
        unit_data['combat_id'] = combat_id
        unit_data['team'] = team
        unit_data['current_hp'] = unit_data.get('hp', 10)
        unit_data['max_hp'] = unit_data.get('hp', 10)
        unit_data['status_effects'] = unit_data.get('status_effects', [])
        unit_data['initiative'] = unit_data.get('initiative', 10)
        unit_data['actions_taken'] = 0

        if 'participants' not in self.state:
            self.state['participants'] = {}

        self.state['participants'][combat_id] = unit_data
        self._save_combat_state(self.state)
        return combat_id

    def calculate_initiative(self):
        """Calculate turn order for all participants"""
        participants = self.get_combat_participants()
        initiative_order = []

        for unit_id, unit in participants.items():
            base_initiative = unit.get('initiative', 10)
            initiative_order.append((unit_id, base_initiative))

        # Sort by initiative (highest first)
        initiative_order.sort(key=lambda x: x[1], reverse=True)
        return [unit_id for unit_id, initiative in initiative_order]

    def get_current_combat_state(self):
        """Get full combat state for external use"""
        return {
            'active': self.state.get('active', False),
            'participants': self.state.get('participants', {}),
            'current_second': self.state.get('current_second', 0),
            'map_linked': self.state.get('map_linked', False),
            'log': self.state.get('log', [])
        }

    def log_combat_action(self, action_data):
        """Record action in combat log"""
        if 'log' not in self.state:
            self.state['log'] = []
        
        self.state['log'].append({
            'timestamp': datetime.now().isoformat(),
            'action': action_data
        })
        
        # Keep log manageable
        if len(self.state['log']) > 50:
            self.state['log'] = self.state['log'][-50:]
        
        self._save_combat_state(self.state)

    def advance_combat_time(self, seconds=1):
        """Advance combat timer"""
        self.state['current_second'] = self.state.get('current_second', 0) + seconds
        self._save_combat_state(self.state)

    def end_combat(self):
        """Clean up combat state"""
        self.state['active'] = False
        self.state['current_second'] = 0
        self.state['participants'] = {}
        self.state['map_linked'] = False
        self.state['log'] = []
        self._save_combat_state(self.state)

    # ==================== IDENTITY HELPERS ====================
    def resolve_combat_key(self, ref: str) -> Optional[str]:
        """Resolve any reference (combat_key, original_id, or display_name) to the active combat_key."""
        if not self.state.get("active") or not ref:
            return None
        # Exact combat_key
        if ref in self.state["participants"]:
            return ref
        # By original_id
        for ck, data in self.state["participants"].items():
            if data.get("original_id") == ref:
                return ck
        # By display_name (LLM-friendly)
        ref_lower = ref.strip().lower()
        for ck, data in self.state["participants"].items():
            if data.get("display_name", "").lower() == ref_lower:
                return ck
        return None

    def get_original_id(self, combat_key: str) -> Optional[str]:
        """Return the original game_state ID for a combat participant."""
        participant = self.state["participants"].get(combat_key)
        return participant.get("original_id") if participant else None

    # ==================== COMMAND DISPATCHER ====================
    def execute_combat_command(self, command: Dict) -> Dict:
        """Execute a combat command based on the action type."""
        action = command.get("action", "").lower().strip()
        if action == "start_combat":
            return self.start_combat(command.get("participants", []))
        elif action == "attack":
            return self.resolve_attack(
                attacker_id=command["attacker"],
                target_id=command["target"],
                style=command.get("style", "normal"),
                weapon_id=command.get("weapon_id")
            )
        elif action == "spell":
            return self.resolve_spell(
                caster_id=command["caster"],
                spell_key=command["spell_key"],
                target_id=command.get("target"),
                target_pos=command.get("target_pos"),
                charge_percent=command.get("charge_percent", 100.0)
            )
        elif action == "block":
            return self.resolve_block(
                entity_id=command["entity"],
                item_id=command.get("item_id")
            )
        elif action == "delay":
            return self.delay_action(
                entity_id=command["entity"],
                seconds=command.get("seconds", 1.0)
            )
        elif action == "move":
            return self.resolve_move(command["entity"], command["to"])
        elif action == "advance_time":
            return self.advance_time(command.get("seconds", 1.0))
        elif action == "end_combat":
            return self.end_combat()
        else:
            return {"success": False, "message": f"Unknown combat action: {action}"}

    # ==================== START COMBAT ====================
    def start_combat(self, participants: List[Dict]) -> Dict:
        """Initialize combat with participants."""
        if not participants:
            return {"success": False, "message": "No participants provided"}

        self.state = {
            "active": True,
            "current_second": 0.0,
            "participants": {},
            "active_conditions": {},
            "map_linked": True,
            "log": []
        }

        initialize_combat_map(width=10, height=10)

        enemy_counter = {}
        game_state = {}
        try:
            with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                game_state = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load game state: {e}")

        for p in participants:
            entity_id = p["entity_id"]
            display_name = p.get("display_name", entity_id)
            team = p.get("team", "enemy")
            pos = p.get("pos", [3, 3])

            base_key = f"{team}_{display_name.replace(' ', '_')}"
            count = enemy_counter.get(base_key, 0) + 1
            enemy_counter[base_key] = count
            combat_key = f"{base_key}_{count}"

            # Determine original_id
            if entity_id == "player" or display_name.lower() == "aburi":
                original_id = "player"
            elif entity_id.startswith("npc_"):
                original_id = entity_id
            else:
                original_id = None

            # Load stats / HP
            if original_id == "player":
                hp = game_state.get("player", {}).get("derived", {}).get("HP", 320)
                max_hp = game_state.get("player", {}).get("derived", {}).get("HP_max", 320)
                stats = game_state.get("player", {}).get("stats", {"Str": 16, "Agi": 15, "Vit": 16, "Ins": 14, "Will": 15, "Crea": 16})
            elif original_id and original_id.startswith("npc_") and original_id in game_state.get("npcs", {}):
                npc_data = game_state["npcs"][original_id]
                hp = npc_data.get("hp", 80)
                max_hp = npc_data.get("max_hp", hp)
                stats = npc_data.get("stats", {"Str": 10, "Agi": 10, "Vit": 10, "Ins": 8, "Will": 8, "Crea": 8})
            else:
                template = self.enemy_templates.get(display_name, {})
                hp = template.get("Vit", 8) * 8 + 10
                max_hp = hp
                stats = {stat: template.get(stat, 8) for stat in ["Str", "Agi", "Vit", "Ins", "Will", "Crea"]}

            agi = stats.get("Agi", 10)
            base_delay = max(0.0, 5.0 - (agi * 0.15))
            suggested_delay = p.get("suggested_delay", 0.0)
            initial_delay = max(0.0, min(5.0, suggested_delay)) if suggested_delay > 0 else base_delay

            self.state["participants"][combat_key] = {
                "display_name": display_name,
                "template_id": display_name,
                "team": team,
                "stats": stats,
                "hp": hp,
                "max_hp": max_hp,
                "pos": pos,
                "next_action_second": initial_delay,
                "conditions": [],
                "tags": [],
                "ai_profile": ["melee"],
                "role": "melee",
                "combat_key": combat_key,
                "original_id": original_id,
                "instance": count,
                "is_blocking": False,
                "block_item_id": None,
                "block_item_hp": 0
            }

            add_entity(entity_id=combat_key, pos=pos, display_name=display_name, team=team)

        self._save_combat_state(self.state)
        current_map = get_current_map()

        return {
            "success": True,
            "message": f"Combat started with {len(participants)} participants (1m grid)",
            "combat_state": self.state,
            "map_grid": current_map["map_grid"],
            "legend": current_map["legend"],
            "current_second": 0.0
        }

    # ==================== NEXT ACTOR ====================
    def get_next_actor(self) -> Optional[dict]:
        """Determine which participant should act next."""
        if not self.state["active"]:
            return None

        enemies_alive = any(data["hp"] > 0 and data["team"] == "enemy" for data in self.state["participants"].values())
        if not enemies_alive:
            self.end_combat()
            return {"end_combat": True, "reason": "All enemies defeated"}

        candidates = []
        for key, data in self.state["participants"].items():
            if data["hp"] <= 0:
                continue
            team_priority = 0 if data["team"] == "player" else 1 if data["team"] == "ally" else 2
            candidates.append((data["next_action_second"], team_priority, data["display_name"], key))

        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        next_key = candidates[0][3]
        return {
            "actor_key": next_key,
            "display_name": self.state["participants"][next_key]["display_name"],
            "team": self.state["participants"][next_key]["team"],
            "next_action_second": self.state["participants"][next_key]["next_action_second"]
        }

    # ==================== BLOCK RESOLUTION ====================
    def _get_block_item_data(self, entity_id: str, item_id: str = None) -> Dict:
        """Get block item data for a participant."""
        combat_key = self.resolve_combat_key(entity_id)
        if not combat_key or combat_key not in self.state["participants"]:
            return {"name": "unarmed", "hp": 0, "speed": 2.0}

        participant = self.state["participants"][combat_key]
        original_id = self.get_original_id(combat_key)
        base_item = None

        if original_id:
            try:
                with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                    gs = json.load(f)
                if original_id == "player":
                    inventory = gs.get("player", {}).get("inventory", {})
                else:
                    inventory = gs.get("npcs", {}).get(original_id, {}).get("inventory", {})

                if item_id and item_id in inventory:
                    base_item = inventory[item_id]
                else:
                    # Find best shield first
                    best_shield = None
                    best_shield_hp = -1
                    for item_id, item in inventory.items():
                        if "shield" in item.get("tags", []):
                            hp = item.get("hp", 0)
                            if hp > best_shield_hp:
                                best_shield_hp = hp
                                best_shield = item

                    # If no shield, find best weapon
                    if not best_shield:
                        best = None
                        best_hp = -1
                        for item_id, item in inventory.items():
                            if "weapon" in item.get("tags", []):
                                hp = item.get("hp", 0)
                                if hp > best_hp:
                                    best_hp = hp
                                    best = item
                        base_item = best
                    else:
                        base_item = best_shield
            except Exception as e:
                print(f"Warning: Inventory load failed for {entity_id}: {e}")

        if not base_item:
            # Default to basic shield if nothing found
            base_item = {"name": "basic shield", "hp": 5, "speed": 2.0}

        return {
            "name": base_item.get("name", "shield"),
            "hp": base_item.get("hp", 5),
            "speed": base_item.get("speed", 2.0)
        }

    def resolve_block(self, entity_id: str, item_id: str = None) -> Dict:
        """Resolve a block action."""
        entity_key = self.resolve_combat_key(entity_id)
        if not entity_key or entity_key not in self.state["participants"]:
            return {"success": False, "message": "Invalid entity or combat state"}

        if self.state["participants"][entity_key]["hp"] <= 0:
            return {"success": False, "message": f"{entity_key} is dead and cannot act"}

        # Get block item data
        block_item = self._get_block_item_data(entity_key, item_id)

        # Find next opponent's action time
        next_opponent_time = float('inf')
        for key, data in self.state["participants"].items():
            if key != entity_key and data["hp"] > 0 and data["team"] != self.state["participants"][entity_key]["team"]:
                if data["next_action_second"] < next_opponent_time:
                    next_opponent_time = data["next_action_second"]

        if next_opponent_time == float('inf'):
            return {"success": False, "message": "No opponents to block against"}

        # Calculate block duration (next opponent time + item speed)
        block_duration = next_opponent_time - self.state["current_second"] + block_item["speed"]

        # Set blocking flags
        self.state["participants"][entity_key]["is_blocking"] = True
        self.state["participants"][entity_key]["block_item_id"] = item_id or "default"
        self.state["participants"][entity_key]["block_item_hp"] = block_item["hp"]
        self.state["participants"][entity_key]["next_action_second"] = self.state["current_second"] + block_duration

        msg = f"At {self.state['current_second']:.1f}s: {entity_key} is now blocking with {block_item['name']} (HP: {block_item['hp']}) until {self.state['participants'][entity_key]['next_action_second']:.1f}s"
        self.state["log"].append(msg)
        self._save_combat_state(self.state)

        return {
            "success": True,
            "entity": entity_key,
            "block_item": block_item["name"],
            "block_hp": block_item["hp"],
            "block_until": self.state["participants"][entity_key]["next_action_second"],
            "message": msg
        }

    # ==================== ATTACK RESOLUTION ====================
    def _get_attack_data(self, attacker_id: str, weapon_id: str = None) -> Dict:
        """Get attack data for a participant."""
        combat_key = self.resolve_combat_key(attacker_id)
        if not combat_key or combat_key not in self.state["participants"]:
            return {"name": "unarmed", "range": {"min": 0, "soft_cap": 1.0, "hard_cap": 1.0}, "damage": 10, "tags": [], "speed": 2.0}

        participant = self.state["participants"][combat_key]
        original_id = self.get_original_id(combat_key)
        base_weapon = None

        if original_id:
            try:
                with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                    gs = json.load(f)
                if original_id == "player":
                    inventory = gs.get("player", {}).get("inventory", {})
                else:
                    inventory = gs.get("npcs", {}).get(original_id, {}).get("inventory", {})

                if weapon_id and weapon_id in inventory:
                    base_weapon = inventory[weapon_id]
                else:
                    best = None
                    best_dmg = -1
                    for item_id, item in inventory.items():
                        if "weapon" in item.get("tags", []):
                            dmg = item.get("damage", 0)
                            if dmg > best_dmg:
                                best_dmg = dmg
                                best = item
                    base_weapon = best
            except Exception as e:
                print(f"Warning: Inventory load failed for {attacker_id}: {e}")

        if not base_weapon:
            stats = participant.get("stats", {})
            str_stat = stats.get("Str", 10)
            if participant.get("role") == "ranged":
                base_weapon = {"name": "ranged attack", "range": 8.0, "damage": round(5 + str_stat * 0.9, 1), "tags": ["ranged"]}
            else:
                base_weapon = {"name": "melee attack", "range": 1.0, "damage": round(4 + str_stat * 1.5, 1), "tags": ["edged"]}

        final_damage = base_weapon.get("damage", 20)
        final_tags = list(base_weapon.get("tags", []))

        raw_range = base_weapon.get("range")
        if isinstance(raw_range, list) and len(raw_range) >= 3:
            range_data = {"min": raw_range[0], "soft_cap": raw_range[1], "hard_cap": raw_range[2]}
        else:
            range_data = {"min": 0.0, "soft_cap": float(raw_range or 1.0), "hard_cap": float(raw_range or 1.0)}

        return {
            "name": base_weapon.get("name", "attack"),
            "range": range_data,
            "damage": round(final_damage, 1),
            "tags": final_tags,
            "speed": base_weapon.get("speed", 2.0)
        }

    def resolve_attack(self, attacker_id: str, target_id: str, style: str = "normal", weapon_id: str = None) -> Dict:
        """Resolve an attack action."""
        attacker_key = self.resolve_combat_key(attacker_id)
        target_key = self.resolve_combat_key(target_id)
        if not attacker_key or not target_key:
            return {"success": False, "message": "Invalid attacker or target"}

        if self.state["participants"][attacker_key]["hp"] <= 0:
            return {"success": False, "message": f"{attacker_key} is dead and cannot act"}
        if self.state["participants"][target_key]["hp"] <= 0:
            return {"success": False, "message": f"{target_key} is already dead", "final_damage": 0}

        distance = get_distance_meters(attacker_key, target_key)
        weapon = self._get_attack_data(attacker_key, weapon_id)

        r = weapon["range"]
        if distance < r["min"]:
            msg = f"Attack failed — too close ({distance:.1f}m < {r['min']}m)"
            full_msg = f"At {self.state['current_second']:.1f}s: {msg}"
            self.state["log"].append(full_msg)
            self._save_combat_state(self.state)
            return {"success": False, "message": full_msg, "final_damage": 0}
        if distance > r["hard_cap"]:
            msg = f"Attack failed — out of range ({distance:.1f}m > {r['hard_cap']}m)"
            full_msg = f"At {self.state['current_second']:.1f}s: {msg}"
            self.state["log"].append(full_msg)
            self._save_combat_state(self.state)
            return {"success": False, "message": full_msg, "final_damage": 0}

        # Roll
        original_id = self.get_original_id(attacker_key)
        roll_entity_id = "player" if original_id == "player" else attacker_key
        check_result = roll_generic_check(
            entity_id=roll_entity_id,
            stats_used=["Str"] if "ranged" not in weapon.get("tags", []) else ["Agi"],
            skill_used="ranged weapons" if "ranged" in weapon.get("tags", []) else "melee weapons",
            difficulty_class=50,
            situational_bonus=0.0
        )
        margin = check_result.get("margin", 0)
        # Time cost
        base_seconds = weapon.get("speed", 2.0)
        skill_name = "ranged weapons" if "ranged" in weapon.get("tags", []) else "melee weapons"
        skill_bonus = self.state["participants"][attacker_key].get("stats", {}).get(skill_name, 0.0)
        modified_seconds = base_seconds / (1 + 0.04 * skill_bonus)
        if style == "light":
            time_cost = modified_seconds * 0.75
        elif style == "heavy":
            time_cost = modified_seconds * 3.0
        else:
            time_cost = modified_seconds
        agi = self.state["participants"][attacker_key].get("stats", {}).get("Agi", 10)
        agi_multiplier = 4.0 ** ((10 - agi) / 13.0)
        time_cost = max(0.5, round(time_cost * agi_multiplier, 1))

        self.state["participants"][attacker_key]["next_action_second"] = self.state["current_second"] + time_cost

        if margin < 0:
            result = {
                "success": True,
                "attacker": attacker_key,
                "target": target_key,
                "final_damage": 0,
                "time_cost": time_cost,
                "message": f"At {self.state['current_second']:.1f}s: {attacker_key} misses {target_key} ({style} style) [time cost {time_cost}s]"
            }
            self.state["log"].append(result["message"])
            self._save_combat_state(self.state)
            return result

        # Check if target is blocking
        target_data = self.state["participants"][target_key]
        block_success = False
        block_damage_reduced = 0
        block_item_damage = 0

        if target_data.get("is_blocking", False):
            # Target is blocking - they get a defensive roll
            block_roll = roll_generic_check(
                entity_id=self.get_original_id(target_key) or target_key,
                stats_used=["Agi", "Str"],
                skill_used="shields",
                difficulty_class=50 + margin,  # DC is attacker's margin
                situational_bonus=0.0
            )

            if block_roll.get("success", False):
                block_success = True
                # Calculate damage reduction based on block item HP
                base_damage = weapon.get("damage", 20)
                hit_quality = max(0, min(3.0, 0.13 * (margin ** 0.8)))
                if style == "light": hit_quality *= 0.75
                elif style == "heavy": hit_quality *= 1.25
                raw_damage = round(base_damage * hit_quality, 1)

                # Reduce damage by block item HP (but not below 0)
                block_damage_reduced = min(raw_damage, target_data.get("block_item_hp", 0))
                final_damage = max(0, raw_damage - block_damage_reduced)

                # Damage the block item
                block_item_damage = block_damage_reduced
                remaining_block_hp = max(0, target_data.get("block_item_hp", 0) - block_item_damage)

                # Update block item HP
                target_data["block_item_hp"] = remaining_block_hp

                # If block item is destroyed, end blocking
                if remaining_block_hp <= 0:
                    target_data["is_blocking"] = False
                    target_data["block_item_id"] = None
                    target_data["block_item_hp"] = 0
            else:
                # Block failed - calculate normal damage
                hit_quality = max(0, min(3.0, 0.13 * (margin ** 0.8)))
                if style == "light": hit_quality *= 0.75
                elif style == "heavy": hit_quality *= 1.25
                base_damage = weapon.get("damage", 20)
                final_damage = round(base_damage * hit_quality, 1)
        else:
            # Normal attack (no blocking)
            hit_quality = max(0, min(3.0, 0.13 * (margin ** 0.8)))
            if style == "light": hit_quality *= 0.75
            elif style == "heavy": hit_quality *= 1.25
            base_damage = weapon.get("damage", 20)
            final_damage = round(base_damage * hit_quality, 1)

        target_data["hp"] = max(0, target_data["hp"] - final_damage)

        if "edged" in weapon.get("tags", []) and final_damage > target_data["max_hp"] * 0.15:
            bleed_tier = 1
            if final_damage > target_data["max_hp"] * 0.25: bleed_tier = 2
            if final_damage > target_data["max_hp"] * 0.40: bleed_tier = 3
            if target_key not in self.state["active_conditions"]:
                self.state["active_conditions"][target_key] = {}
            self.state["active_conditions"][target_key]["bleeding"] = {
                "type": "damage_over_time",
                "damage_per_second": bleed_tier,
                "start_second": self.state["current_second"]
            }

        # Build result message
        if block_success:
            msg = f"At {self.state['current_second']:.1f}s: {attacker_key} hits {target_key} for {final_damage} damage (blocked {block_damage_reduced}, item took {block_item_damage} damage) ({style} style) [time cost {time_cost}s]"
        else:
            msg = f"At {self.state['current_second']:.1f}s: {attacker_key} hits {target_key} for {final_damage} damage ({style} style) [time cost {time_cost}s]"

        result = {
            "success": True,
            "attacker": attacker_key,
            "target": target_key,
            "roll_result": check_result,
            "final_damage": final_damage,
            "time_cost": time_cost,
            "target_hp_remaining": target_data["hp"],
            "block_success": block_success,
            "block_damage_reduced": block_damage_reduced,
            "block_item_damage": block_item_damage,
            "message": msg
        }

        self.state["log"].append(result["message"])
        self._save_combat_state(self.state)
        return result

    # ==================== MOVEMENT ====================
    def resolve_move(self, entity_id: str, new_pos: list) -> Dict:
        """Resolve a movement action."""
        entity_key = self.resolve_combat_key(entity_id)
        if not entity_key or entity_key not in self.state["participants"]:
            return {"success": False, "message": "Invalid entity or combat state"}

        if self.state["participants"][entity_key]["hp"] <= 0:
            return {"success": False, "message": f"{entity_key} is dead and cannot move"}

        distance = get_distance_meters(entity_key, target_pos=new_pos)
        if distance <= 0.1:
            return {"success": True, "message": f"At {self.state['current_second']:.1f}s: {entity_key} is already at the target position"}

        agi = self.state["participants"][entity_key].get("stats", {}).get("Agi", 10)
        agi_factor = 4.0 ** ((agi - 10) / 15.0)
        speed_mps = 2.25 * agi_factor
        speed_mps = max(0.3, min(15.0, speed_mps))
        time_cost = distance / speed_mps
        time_cost = max(0.5, round(time_cost, 1))

        move_result = move_entity(entity_key, new_pos)
        if not move_result.get("success", False):
            return {"success": False, "message": f"Move failed: {move_result.get('message')}"}

        self.state["participants"][entity_key]["pos"] = new_pos
        self.state["participants"][entity_key]["next_action_second"] = self.state["current_second"] + time_cost

        msg = f"At {self.state['current_second']:.1f}s: {entity_key} moves {distance:.1f}m at {speed_mps:.1f} m/s [time cost {time_cost}s]"
        self.state["log"].append(msg)
        self._save_combat_state(self.state)

        return {
            "success": True,
            "entity": entity_key,
            "distance": round(distance, 1),
            "speed_mps": round(speed_mps, 1),
            "time_cost": time_cost,
            "new_pos": new_pos,
            "message": msg
        }

    # ==================== SPELL CASTING ====================
    def resolve_spell(self, caster_id: str, spell_key: str, target_id: str = None, target_pos: list = None, charge_percent: float = 100.0) -> Dict:
        """Resolve a spell casting action."""
        caster_key = self.resolve_combat_key(caster_id)
        if not caster_key or caster_key not in self.state["participants"]:
            return {"success": False, "message": "Invalid caster"}

        original_id = self.get_original_id(caster_key)
        if not original_id:
            return {"success": False, "message": "Cannot cast spells with this entity"}

        try:
            with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                gs = json.load(f)

            if original_id == "player":
                spells_dict = normalize_spell_collection(gs.get("player", {}).get("spells", {}))
                mp_current = gs.get("player", {}).get("derived", {}).get("MP", 0)
            else:
                spells_dict = normalize_spell_collection(gs.get("npcs", {}).get(original_id, {}).get("spells", {}))
                mp_current = gs.get("npcs", {}).get(original_id, {}).get("mp", 0)

            # First try to load from spell library
            try:
                with open(path_config.spell_library_path, "r", encoding="utf-8") as f:
                    spell_library = json.load(f)
                spell = None
            except:
                spell = None

            # Fallback to game state spells if not found in library
            if not spell:
                lookup_key = str(spell_key or "").strip()
                spell = (
                    spells_dict.get(lookup_key)
                    or spells_dict.get(lookup_key.lower())
                    or spells_dict.get(lookup_key.lower().replace(" ", "_"))
                )

            if not spell:
                return {"success": False, "message": f"Spell '{spell_key}' not found"}

            if not is_spell_learned(spell):
                return {"success": False, "message": f"Spell '{spell_key}' is not fully learned"}

        except Exception as e:
            return {"success": False, "message": f"Failed to load spell data: {e}"}

        base_mp_cost = float(spell.get("MP_cost", spell.get("base_mp_cost", spell.get("base_MP_cost", 200))))
        base_damage = spell.get("spell_damage", spell.get("damage", 0))
        is_aoe = "area_of_effect" in spell.get("tags", [])
        has_explosion = "explosion" in spell.get("tags", [])
        radius = spell.get("radius", 0)

        charge_factor = max(0.1, min(2.0, charge_percent / 100.0))
        mp_cost = base_mp_cost * charge_factor
        base_damage_after_charge = base_damage * charge_factor

        if mp_current < mp_cost:
            return {"success": False, "message": f"Not enough MP (need {mp_cost:.0f}, have {mp_current:.0f})"}

        # Time cost
        if original_id == "player":
            try:
                gs["player"]["derived"]["MP"] = max(0, gs["player"]["derived"]["MP"] - mp_cost)
                with open(path_config.game_state_path, "w", encoding="utf-8") as f:
                    json.dump(gs, f, indent=4)
            except Exception as e:
                return {"success": False, "message": f"Failed to spend MP: {e}"}

        crea = self.state["participants"][caster_key].get("stats", {}).get("Crea", 10)
        skill_bonus = self.state["participants"][caster_key].get("stats", {}).get("spellcasting", 0.0)
        if original_id == "player":
            skill_bonus = max(skill_bonus, gs.get("player", {}).get("skills", {}).get("spellcasting", 0.0))
        time_cost = calculate_spell_cast_time(base_mp_cost, crea, skill_bonus, charge_factor)

        self.state["participants"][caster_key]["next_action_second"] = self.state["current_second"] + time_cost

        # Targets
        targets_hit = []
        if is_aoe:
            if target_pos is None:
                return {"success": False, "message": "AoE spell requires a target location [x, y]"}
            for eid, participant in self.state["participants"].items():
                if participant.get("hp", 0) <= 0 or eid == caster_key:
                    continue
                dist = get_distance_meters(entity1_id=eid, target_pos=target_pos)
                if dist <= radius + 0.2:
                    targets_hit.append(eid)
        elif target_id:
            target_key = self.resolve_combat_key(target_id)
            if target_key:
                targets_hit = [target_key]
        else:
            return {"success": False, "message": "Spell requires a target"}

        # Damage resolution
        results = []
        for tid in targets_hit:
            roll_entity_id = "player" if original_id == "player" else caster_key
            attack_config = spell.get("attack", {})
            stats_used = spell.get("attack_stats") or attack_config.get("stats", ["Crea"])
            skill_used = spell.get("attack_skill") or attack_config.get("skill", "spellcasting")

            check_result = roll_generic_check(
                entity_id=roll_entity_id,
                stats_used=stats_used,
                skill_used=skill_used,
                difficulty_class=50,
                situational_bonus=0.0
            )
            margin = check_result.get("margin", 0)

            if has_explosion:
                effective_margin = max(-50, min(10, margin))
                damage_mult = (effective_margin + 50) / 60.0
                final_damage = round(base_damage_after_charge * damage_mult, 1)
            else:
                if margin < 0:
                    final_damage = 0
                else:
                    hit_quality = max(0, min(3.0, 0.13 * (margin ** 0.8)))
                    final_damage = round(base_damage_after_charge * hit_quality, 1)

            if tid in self.state["participants"]:
                self.state["participants"][tid]["hp"] = max(0, self.state["participants"][tid]["hp"] - final_damage)

            results.append({"target": tid, "damage": final_damage, "margin": margin})

        # MP was spent before resolution so stat-growth refreshes cannot refill the casting cost.
        if False and original_id == "player":
            try:
                with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                    gs = json.load(f)
                gs["player"]["derived"]["MP"] = max(0, gs["player"]["derived"]["MP"] - mp_cost)
                with open(path_config.game_state_path, "w", encoding="utf-8") as f:
                    json.dump(gs, f, indent=4)
            except:
                pass

        msg = f"At {self.state['current_second']:.1f}s: {caster_key} casts {spell_key} at {charge_percent:.0f}% charge"
        if is_aoe:
            msg += f" (AoE at {target_pos}, radius {radius})"
        for r in results:
            msg += f" | {r['target']}: {r['damage']:.0f} dmg"
        msg += f" [time cost {time_cost}s, MP {mp_cost:.0f}]"

        self.state["log"].append(msg)
        self._save_combat_state(self.state)

        return {
            "success": True,
            "caster": caster_key,
            "spell": spell_key,
            "charge_percent": charge_percent,
            "mp_cost": round(mp_cost, 1),
            "time_cost": time_cost,
            "roll_result": check_result,
            "is_aoe": is_aoe,
            "targets_hit": results,
            "message": msg
        }

    # ==================== TIME ADVANCEMENT ====================
    def advance_time(self, seconds: float = None) -> Dict:
        """Advance combat time and handle ongoing effects."""
        if seconds is None:
            next_info = self.get_next_actor()
            if next_info and next_info.get("end_combat"):
                return next_info
            if next_info:
                next_time = self.state["participants"][next_info["actor_key"]]["next_action_second"]
                seconds = max(0.0, next_time - self.state["current_second"])
            else:
                seconds = 1.0

        self.state["current_second"] += seconds
        log_messages = []

        # Handle ongoing conditions
        for entity_id, conditions in list(self.state.get("active_conditions", {}).items()):
            if entity_id not in self.state["participants"]:
                continue
            participant = self.state["participants"][entity_id]
            for cond_name, cond in list(conditions.items()):
                if cond.get("type") == "sustained":
                    cost = cond.get("mp_cost_per_second", 0) * seconds
                    if entity_id.startswith("player_") or self.get_original_id(entity_id) == "player":
                        try:
                            with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                                gs = json.load(f)
                            current_mp = gs["player"]["derived"]["MP"]
                            new_mp = max(0, current_mp - cost)
                            gs["player"]["derived"]["MP"] = new_mp
                            with open(path_config.game_state_path, "w", encoding="utf-8") as f:
                                json.dump(gs, f, indent=4)
                            if new_mp <= 0 and current_mp > 0:
                                del conditions[cond_name]
                                log_messages.append(f"At {self.state['current_second']:.1f}s: {entity_id} {cond_name} expired (out of MP)")
                        except:
                            pass
                elif cond.get("type") == "damage_over_time":
                    dps = cond.get("damage_per_second", 0)
                    damage = dps * seconds
                    participant["hp"] = max(0, participant["hp"] - damage)
                    if participant["hp"] <= 0:
                        log_messages.append(f"At {self.state['current_second']:.1f}s: {entity_id} died from {cond_name}")

        # Handle dead participants
        for entity_id, data in list(self.state["participants"].items()):
            if data["hp"] <= 0:
                if entity_id in self.state.get("active_conditions", {}):
                    del self.state["active_conditions"][entity_id]
                log_messages.append(f"At {self.state['current_second']:.1f}s: {entity_id} has died")

        # Reset blocking state if block duration has ended
        for entity_id, data in list(self.state["participants"].items()):
            if data.get("is_blocking", False) and data["next_action_second"] <= self.state["current_second"]:
                data["is_blocking"] = False
                data["block_item_id"] = None
                data["block_item_hp"] = 0
                log_messages.append(f"At {self.state['current_second']:.1f}s: {entity_id} is no longer blocking")

        for msg in log_messages:
            self.state["log"].append(msg)

        turn_summary = self.build_turn_summary()
        self._save_combat_state(self.state)
        return {
            "success": True,
            "current_second": round(self.state["current_second"], 1),
            "log_messages": log_messages,
            "turn_summary": turn_summary
        }

    # ==================== TURN SUMMARY ====================
    def build_turn_summary(self) -> Dict:
        """Build a summary of the current combat state."""
        if not self.state["active"]:
            return {"combat_ended": True}

        next_info = self.get_next_actor()
        if next_info and next_info.get("end_combat"):
            return {"combat_ended": True, "reason": next_info.get("reason", "Combat over")}

        participants_summary = {}
        for key, data in self.state["participants"].items():
            if data["hp"] <= 0:
                continue
            participants_summary[key] = {
                "display_name": data["display_name"],
                "team": data["team"],
                "hp": data["hp"],
                "max_hp": data["max_hp"],
                "next_action_second": round(data.get("next_action_second", 0), 1),
                "is_blocking": data.get("is_blocking", False),
                "block_item_hp": data.get("block_item_hp", 0)
            }

        conditions_summary = {}
        for entity_id, conds in self.state.get("active_conditions", {}).items():
            if entity_id not in self.state["participants"] or self.state["participants"][entity_id]["hp"] <= 0:
                continue
            conditions_summary[entity_id] = {}
            for name, cond in conds.items():
                if cond.get("type") == "sustained":
                    conditions_summary[entity_id][name] = f"{cond.get('damage_modifier', 0)} bonus damage, {cond.get('mp_cost_per_second', 0):.2f} MP/s"
                elif cond.get("type") == "damage_over_time":
                    conditions_summary[entity_id][name] = f"{cond.get('damage_per_second', 0)} dmg/s"

        return {
            "current_second": round(self.state["current_second"], 1),
            "next_actor": next_info,
            "participants": participants_summary,
            "active_conditions": conditions_summary,
            "message_for_llm": f"It is now {next_info['display_name']}'s turn." if next_info else "Combat continuing."
        }

    # ==================== ACTION DELAY ====================
    def delay_action(self, entity_id: str, seconds: float) -> Dict:
        """Delay an entity's next action."""
        entity_key = self.resolve_combat_key(entity_id)
        if not entity_key or entity_key not in self.state["participants"]:
            return {"success": False, "message": "Invalid entity or combat state"}

        if self.state["participants"][entity_key]["hp"] <= 0:
            return {"success": False, "message": f"{entity_key} is dead and cannot act"}

        max_existing = max((data["next_action_second"] for data in self.state["participants"].values()), default=0)
        max_delay = min(300.0, max_existing + 1.0)
        actual_seconds = max(0.0, min(seconds, max_delay))

        self.state["participants"][entity_key]["next_action_second"] += actual_seconds

        msg = f"At {self.state['current_second']:.1f}s: {entity_key} delays action by {actual_seconds:.1f}s (new next action at {self.state['participants'][entity_key]['next_action_second']:.1f}s)"
        self.state["log"].append(msg)
        self._save_combat_state(self.state)

        advance_result = self.advance_time()
        return {
            "success": True,
            "entity": entity_key,
            "delayed_by": actual_seconds,
            "new_next_action_second": self.state["participants"][entity_key]["next_action_second"],
            "message": msg,
            "advance_result": advance_result
        }

    # ==================== END COMBAT ====================
    def end_combat(self) -> Dict:
        """End the current combat."""
        self.state["active"] = False
        self.state["current_second"] = 0.0
        self.state["participants"] = {}
        self.state["active_conditions"] = {}
        self.state["map_linked"] = False
        self.state["log"] = []
        self._save_combat_state(self.state)
        map_end_combat()
        return {
            "success": True,
            "message": "Combat ended",
            "map_grid": None,
            "legend": None
        }
