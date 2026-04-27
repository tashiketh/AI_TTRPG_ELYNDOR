#!/usr/bin/env python3
"""
Combat Manager - Core combat system that integrates with existing combat_tools.py
Handles turn-based combat, AI decisions, and combat state management
"""

import random
from datetime import datetime
from typing import Dict, List, Any, Optional
import json

class CombatManager:
    def __init__(self, game_engine):
        """
        Initialize combat manager with game engine reference
        Integrates with existing CombatTools for state management
        """
        self.game_engine = game_engine
        self.combat_tools = game_engine.combat  # Existing CombatTools
        self.combat_state = {
            'active': False,
            'turn': 0,
            'round': 1,
            'turn_order': [],
            'current_unit': None,
            'environment': {},
            'initiative_bonuses': {}
        }
        self.action_registry = self._load_combat_actions()

    def initialize_combat(self, enemies, allies=None, environment=None):
        """
        Set up combat with participants and environment
        Uses existing combat_tools for participant management
        """
        # Reset combat state
        self.combat_state = {
            'active': True,
            'turn': 0,
            'round': 1,
            'turn_order': [],
            'current_unit': None,
            'environment': environment or {},
            'initiative_bonuses': {}
        }

        # Add participants using existing combat_tools methods
        for enemy in enemies:
            self.combat_tools.add_combat_participant(enemy, 'enemy')

        if allies:
            for ally in allies:
                self.combat_tools.add_combat_participant(ally, 'ally')

        # Calculate initiative using existing method
        self.combat_state['turn_order'] = self.combat_tools.calculate_initiative()
        self.combat_state['current_unit'] = self.combat_state['turn_order'][0]

        # Initialize map if needed
        if environment and environment.get('use_map', True):
            self._initialize_combat_map(environment)

        return self.get_combat_state()

    def _initialize_combat_map(self, environment):
        """Set up combat map using existing map_tools"""
        from map_tools import initialize_combat_map, add_entity

        map_result = initialize_combat_map(
            width=environment.get('map_width', 20),
            height=environment.get('map_height', 15),
            terrain=environment.get('terrain', 'forest')
        )
        map_data = map_result.get('map_state', map_result)

        # Add all participants to map
        for unit_id, unit in self.combat_tools.get_combat_participants().items():
            position = self._determine_start_position(unit, map_data)
            add_entity(
                entity_id=unit_id,
                pos=list(position),
                display_name=unit.get('display_name') or unit.get('name') or unit_id,
                team=unit.get('team', 'enemy')
            )

        self.combat_state['map_data'] = map_data
        self.combat_state['map_linked'] = True

    def _determine_start_position(self, unit, map_data):
        """Determine where unit starts on map"""
        team = unit.get('team', 'enemy')

        if team == 'ally':
            # Allies start on left side
            return (2, map_data['height'] // 2)
        else:
            # Enemies start on right side
            return (map_data['width'] - 3, map_data['height'] // 2)

    def get_combat_state(self):
        """Get current combat state combining manager and tools data"""
        tools_state = self.combat_tools.get_current_combat_state()
        
        return {
            **self.combat_state,
            **tools_state,
            'participants': tools_state['participants']
        }

    def get_current_unit(self):
        """Get the unit whose turn it is"""
        if not self.combat_state['active']:
            return None

        unit_id = self.combat_state['current_unit']
        participants = self.combat_tools.get_combat_participants()
        return participants.get(unit_id)

    def advance_turn(self):
        """Move to next unit's turn"""
        current_index = self.combat_state['turn_order'].index(self.combat_state['current_unit'])

        # Check if round should advance
        if current_index == len(self.combat_state['turn_order']) - 1:
            self.combat_state['round'] += 1
            self.combat_state['turn'] = 0
        else:
            self.combat_state['turn'] += 1

        # Set next unit
        next_index = (current_index + 1) % len(self.combat_state['turn_order'])
        self.combat_state['current_unit'] = self.combat_state['turn_order'][next_index]

        # Reset action counters
        for unit in self.combat_tools.get_combat_participants().values():
            unit['actions_taken'] = 0

        return self.combat_state

    def resolve_combat_action(self, unit_id, action_data):
        """Process a unit's combat action"""
        unit = self.combat_tools.get_combat_participants().get(unit_id)
        if not unit:
            return {"success": False, "error": "Unit not found"}

        # Get action details
        action_type = action_data['action']
        target_id = action_data.get('target')

        if action_type not in self.action_registry:
            return {"success": False, "error": "Invalid action"}

        # Execute the action
        action_handler = self.action_registry[action_type]
        unit['combat_manager'] = self
        result = action_handler.execute(unit, target_id, action_data.get('options', {}))

        # Log the action using existing combat_tools
        self.combat_tools.log_combat_action({
            'unit_id': unit_id,
            'action': action_type,
            'target': target_id,
            'result': result
        })

        # Check for combat end conditions
        if self._check_combat_end():
            result['combat_ended'] = True
            result['winner'] = self._determine_winner()

        return result

    def _check_combat_end(self):
        """Check if combat should end"""
        participants = self.combat_tools.get_combat_participants()
        
        # Check if one team is completely defeated
        enemy_alive = any(u['team'] == 'enemy' and u['current_hp'] > 0 for u in participants.values())
        ally_alive = any(u['team'] == 'ally' and u['current_hp'] > 0 for u in participants.values())

        # Combat ends if only one team has living units
        return not (enemy_alive and ally_alive)

    def _determine_winner(self):
        """Determine which team won"""
        participants = self.combat_tools.get_combat_participants()
        enemy_alive = any(u['team'] == 'enemy' and u['current_hp'] > 0 for u in participants.values())
        return 'enemies' if enemy_alive else 'allies'

    def _load_combat_actions(self):
        """Load available combat actions"""
        registry = CombatActionRegistry()
        try:
            from combat_actions import extend_combat_actions
            registry = extend_combat_actions(registry)
        except Exception:
            pass
        return registry.actions

    def end_combat(self):
        """Clean up combat state using existing tools"""
        self.combat_tools.end_combat()
        self.combat_state['active'] = False
        
        # Clean up map if used
        if self.combat_state.get('map_linked'):
            from map_tools import end_combat as map_end_combat
            map_end_combat()

    def get_unit_position(self, unit_id):
        """Get unit's current map position"""
        if not self.combat_state.get('map_linked'):
            return None

        map_data = self.combat_state['map_data']
        return map_data['entities'].get(unit_id, {}).get('position')

    def move_unit(self, unit_id, new_position):
        """Move unit on combat map"""
        if not self.combat_state.get('map_linked'):
            return False

        from map_tools import move_entity
        result = move_entity(unit_id, list(new_position))
        success = result.get("success", False)

        if success:
            self.combat_state['map_data'] = result.get("map_state", self.combat_state.get('map_data', {}))

        return success

    def _save_map(self, map_data):
        """Save map state using existing tools"""
        from map_tools import _save_map
        _save_map(map_data)

# Combat Action Classes
class CombatAction:
    """Base class for combat actions"""
    def __init__(self, name, description, action_cost=1):
        self.name = name
        self.description = description
        self.action_cost = action_cost

    def execute(self, actor, target_id, options):
        """Execute this action and return results"""
        raise NotImplementedError("Subclasses must implement execute()")

    def _find_unit(self, unit_id, combat_manager):
        """Find unit by ID"""
        participants = combat_manager.combat_tools.get_combat_participants()
        return participants.get(unit_id)

class AttackAction(CombatAction):
    def __init__(self):
        super().__init__(
            "attack",
            "Basic melee or ranged attack against a target",
            action_cost=1
        )

    def execute(self, actor, target_id, options):
        target = self._find_unit(target_id, actor['combat_manager'])
        if not target:
            return {"success": False, "error": "Target not found"}

        # Calculate damage
        attack_power = actor.get('attack_power', 3)
        defense = target.get('defense', 1)
        damage = max(1, attack_power - defense)

        # Apply damage
        target['current_hp'] = max(0, target['current_hp'] - damage)

        # Check for death
        is_dead = target['current_hp'] <= 0

        return {
            "success": True,
            "narrative": self._generate_attack_narrative(actor, target, damage, is_dead),
            "damage": damage,
            "target_defeated": is_dead,
            "action_cost": self.action_cost
        }

    def _generate_attack_narrative(self, actor, target, damage, is_dead):
        """Create vivid attack description"""
        actor_name = actor.get('name', 'The attacker')
        target_name = target.get('name', 'the target')
        weapon = actor.get('weapon', 'fists')

        verbs = ["strikes", "hits", "slashes", "pummels", "smashes"]
        adverbs = ["swiftly", "powerfully", "precise", "viciously", "deftly"]

        narrative = f"{actor_name} {random.choice(verbs)} {target_name} {random.choice(adverbs)} with {weapon}, "
        narrative += f"dealing {damage} damage!"

        if is_dead:
            death_verbs = ["collapses", "falls", "crumples", "succumbs"]
            narrative += f" {target_name} {random.choice(death_verbs)} to the ground, defeated!"

        return narrative

class CombatActionRegistry:
    """Registry of all available combat actions"""
    def __init__(self):
        self.actions = {
            'attack': AttackAction(),
            'defend': DefendAction(),
            'heal': HealAction(),
            'wait': WaitAction(),
            'flee': FleeAction()
        }

    def get_action(self, action_name):
        return self.actions.get(action_name)

    def get_available_actions(self, unit):
        """Get actions available to this unit"""
        available = {}
        for name, action in self.actions.items():
            if self._can_use_action(unit, action):
                available[name] = {
                    'description': action.description,
                    'action_cost': action.action_cost
                }
        return available

    def _can_use_action(self, unit, action):
        """Check if unit can use this action"""
        # Check action-specific requirements
        if action.name == 'heal' and unit.get('healing_power', 0) <= 0:
            return False
        return True

class DefendAction(CombatAction):
    def __init__(self):
        super().__init__(
            "defend",
            "Focus on defense, reducing incoming damage next turn",
            action_cost=1
        )

    def execute(self, actor, target_id, options):
        # Apply defense buff
        if 'defense_buff' not in actor.get('status_effects', []):
            actor['status_effects'].append('defense_buff')

        return {
            "success": True,
            "narrative": f"{actor.get('name', 'The defender')} assumes a defensive stance, ready to withstand incoming attacks!",
            "effects": {"defense_buff": True},
            "action_cost": self.action_cost
        }

class HealAction(CombatAction):
    def __init__(self):
        super().__init__(
            "heal",
            "Restore HP to self or ally",
            action_cost=1
        )

    def execute(self, actor, target_id, options):
        # Determine target (self if none specified)
        target = self._find_unit(target_id, actor['combat_manager']) if target_id else actor
        if not target:
            return {"success": False, "error": "Target not found"}

        # Calculate healing
        healing_power = actor.get('healing_power', 2)
        heal_amount = random.randint(healing_power, healing_power * 2)

        # Apply healing
        target['current_hp'] = min(target.get('max_hp', 10), target['current_hp'] + heal_amount)

        return {
            "success": True,
            "narrative": f"{actor.get('name', 'The healer')} channels healing energy, restoring {heal_amount} HP to {target.get('name', 'themselves')}!",
            "healing": heal_amount,
            "action_cost": self.action_cost
        }

class WaitAction(CombatAction):
    def __init__(self):
        super().__init__(
            "wait",
            "Skip turn to gain advantage later",
            action_cost=1
        )

    def execute(self, actor, target_id, options):
        return {
            "success": True,
            "narrative": f"{actor.get('name', 'The unit')} waits patiently, observing the battlefield.",
            "action_cost": self.action_cost
        }

class FleeAction(CombatAction):
    def __init__(self):
        super().__init__(
            "flee",
            "Attempt to escape from combat",
            action_cost=1
        )

    def execute(self, actor, target_id, options):
        # Fleeing ends combat for this unit
        return {
            "success": True,
            "narrative": f"{actor.get('name', 'The unit')} turns and flees from the battle!",
            "fled": True,
            "action_cost": self.action_cost
        }
