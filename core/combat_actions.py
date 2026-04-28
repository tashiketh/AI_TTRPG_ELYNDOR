#!/usr/bin/env python3
"""
Combat Actions - Additional combat actions that can be added to the registry
Extends the basic actions in combat_manager.py
"""

import random
from combat_manager import CombatAction

class CastSpellAction(CombatAction):
    """Magic spell casting action"""
    def __init__(self):
        super().__init__(
            "cast_spell",
            "Cast a magical spell",
            action_cost=2  # Spells cost more
        )

    def execute(self, actor, target_id, options):
        # Get spell from options
        spell_name = options.get('spell')
        if not spell_name:
            return {"success": False, "error": "No spell specified"}

        # Find spell in actor's spell list
        spells = actor.get('spells', [])
        spell = next((s for s in spells if s['name'].lower() == spell_name.lower()), None)
        
        if not spell:
            return {"success": False, "error": f"Unknown spell: {spell_name}"}

        # Determine target
        target = None
        if target_id:
            target = self._find_unit(target_id, actor['combat_manager'])
            if not target:
                return {"success": False, "error": "Target not found"}

        # Calculate spell effects
        result = self._cast_spell(actor, spell, target)
        
        # Consume mana if applicable
        if actor.get('mana') is not None:
            mana_cost = spell.get('mana_cost', 0)
            actor['mana'] = max(0, actor.get('mana', 0) - mana_cost)
            result['mana_used'] = mana_cost

        return result

    def _cast_spell(self, actor, spell, target):
        """Handle different spell types"""
        spell_type = spell.get('type', 'damage')
        actor_name = actor.get('name', 'The caster')
        spell_name = spell['name']

        if spell_type == 'damage':
            return self._cast_damage_spell(actor, spell, target, actor_name, spell_name)
        elif spell_type == 'heal':
            return self._cast_heal_spell(actor, spell, target, actor_name, spell_name)
        elif spell_type == 'buff':
            return self._cast_buff_spell(actor, spell, target, actor_name, spell_name)
        elif spell_type == 'debuff':
            return self._cast_debuff_spell(actor, spell, target, actor_name, spell_name)
        else:
            return {
                "success": True,
                "narrative": f"{actor_name} casts {spell_name}, but nothing seems to happen.",
                "action_cost": self.action_cost
            }

    def _cast_damage_spell(self, actor, spell, target, actor_name, spell_name):
        """Handle damage spells"""
        if not target:
            return {"success": False, "error": "Damage spell requires a target"}

        # Calculate damage
        base_damage = spell.get('damage', 5)
        magic_power = actor.get('magic_power', 1)
        defense = target.get('magic_defense', 0)
        damage = max(1, base_damage + magic_power - defense)

        # Apply damage
        target['current_hp'] = max(0, target['current_hp'] - damage)
        is_dead = target['current_hp'] <= 0

        # Generate narrative
        elements = spell.get('element', 'arcane')
        effects = spell.get('effects', [])

        narrative = f"{actor_name} casts {spell_name}, unleashing {elements} energy"
        if target:
            narrative += f" at {target.get('name', 'the target')}"
        narrative += "!"

        if 'burn' in effects:
            narrative += f" {target.get('name', 'The target')} is engulfed in flames!"
        if 'freeze' in effects:
            narrative += f" A frozen aura surrounds {target.get('name', 'the target')}!"

        narrative += f" The spell deals {damage} damage."
        if is_dead:
            narrative += f" {target.get('name', 'The target')} is defeated!"

        return {
            "success": True,
            "narrative": narrative,
            "damage": damage,
            "target_defeated": is_dead,
            "effects": effects,
            "action_cost": self.action_cost
        }

    def _cast_heal_spell(self, actor, spell, target, actor_name, spell_name):
        """Handle healing spells"""
        # Determine target (self if none specified)
        target = target if target else actor

        # Calculate healing
        base_heal = spell.get('healing', 5)
        magic_power = actor.get('magic_power', 1)
        heal_amount = base_heal + magic_power

        # Apply healing
        target['current_hp'] = min(target.get('max_hp', 10), target['current_hp'] + heal_amount)

        # Generate narrative
        narrative = f"{actor_name} casts {spell_name}, "
        if target == actor:
            narrative += "bathing themselves in healing light!"
        else:
            narrative += f"directing healing energy toward {target.get('name', 'the target')}!"

        narrative += f" {target.get('name', 'They')} regain {heal_amount} HP."

        return {
            "success": True,
            "narrative": narrative,
            "healing": heal_amount,
            "action_cost": self.action_cost
        }

    def _cast_buff_spell(self, actor, spell, target, actor_name, spell_name):
        """Handle buff spells"""
        # Determine target (self if none specified)
        target = target if target else actor

        # Apply buff
        buff_effect = spell.get('effect', 'strength_buff')
        if buff_effect not in target.get('status_effects', []):
            target['status_effects'].append(buff_effect)

        # Generate narrative
        narrative = f"{actor_name} casts {spell_name} on "
        if target == actor:
            narrative += "themselves, "
        else:
            narrative += f"{target.get('name', 'the target')}, "

        if buff_effect == 'strength_buff':
            narrative += "enhancing their physical power!"
        elif buff_effect == 'magic_buff':
            narrative += "amplifying their magical abilities!"
        elif buff_effect == 'speed_buff':
            narrative += "increasing their speed!"
        else:
            narrative += "providing a mysterious enhancement!"

        return {
            "success": True,
            "narrative": narrative,
            "effects": [buff_effect],
            "action_cost": self.action_cost
        }

    def _cast_debuff_spell(self, actor, spell, target, actor_name, spell_name):
        """Handle debuff spells"""
        if not target:
            return {"success": False, "error": "Debuff spell requires a target"}

        # Apply debuff
        debuff_effect = spell.get('effect', 'weakness')
        if debuff_effect not in target.get('status_effects', []):
            target['status_effects'].append(debuff_effect)

        # Generate narrative
        narrative = f"{actor_name} casts {spell_name} at {target.get('name', 'the target')}, "

        if debuff_effect == 'weakness':
            narrative += "sapping their strength!"
        elif debuff_effect == 'slow':
            narrative += "encasing them in a field of sluggish energy!"
        elif debuff_effect == 'confusion':
            narrative += "clouding their mind with confusion!"
        else:
            narrative += "afflicting them with a hex!"

        return {
            "success": True,
            "narrative": narrative,
            "effects": [debuff_effect],
            "action_cost": self.action_cost
        }

class UseItemAction(CombatAction):
    """Use consumable items in combat"""
    def __init__(self):
        super().__init__(
            "use_item",
            "Use a consumable item from inventory",
            action_cost=1
        )

    def execute(self, actor, target_id, options):
        item_name = options.get('item')
        if not item_name:
            return {"success": False, "error": "No item specified"}

        # Find item in inventory
        inventory = actor.get('inventory', [])
        item = next((i for i in inventory if i['name'].lower() == item_name.lower()), None)

        if not item:
            return {"success": False, "error": f"Item not found: {item_name}"}

        # Determine target
        target = None
        if target_id:
            target = self._find_unit(target_id, actor['combat_manager'])
            if not target:
                return {"success": False, "error": "Target not found"}

        # Use the item
        result = self._use_item(actor, item, target)

        # Remove item from inventory if consumable
        if item.get('consumable', True):
            actor['inventory'].remove(item)

        return result

    def _use_item(self, actor, item, target):
        """Handle different item types"""
        item_type = item.get('type', 'consumable')
        actor_name = actor.get('name', 'The user')
        item_name = item['name']

        if item_type == 'health_potion':
            return self._use_health_potion(actor, item, target, actor_name, item_name)
        elif item_type == 'mana_potion':
            return self._use_mana_potion(actor, item, target, actor_name, item_name)
        elif item_type == 'bomb':
            return self._use_bomb(actor, item, target, actor_name, item_name)
        else:
            return {
                "success": True,
                "narrative": f"{actor_name} uses {item_name}, but nothing special happens.",
                "action_cost": self.action_cost
            }

    def _use_health_potion(self, actor, item, target, actor_name, item_name):
        """Use health potion"""
        # Determine target (self if none specified)
        target = target if target else actor

        # Calculate healing
        heal_amount = item.get('healing', 10)
        target['current_hp'] = min(target.get('max_hp', 10), target['current_hp'] + heal_amount)

        # Generate narrative
        narrative = f"{actor_name} drinks {item_name}, "
        if target == actor:
            narrative += "feeling their wounds knit together!"
        else:
            narrative += f"and pours it on {target.get('name', 'the target')}!"

        narrative += f" {target.get('name', 'They')} regain {heal_amount} HP."

        return {
            "success": True,
            "narrative": narrative,
            "healing": heal_amount,
            "action_cost": self.action_cost
        }

    def _use_mana_potion(self, actor, item, target, actor_name, item_name):
        """Use mana potion"""
        # Only affects caster
        target = actor

        # Restore mana
        mana_amount = item.get('mana', 10)
        if 'mana' in actor:
            actor['mana'] = min(actor.get('max_mana', 20), actor.get('mana', 0) + mana_amount)
        else:
            actor['mana'] = mana_amount

        # Generate narrative
        narrative = f"{actor_name} drinks {item_name}, feeling magical energy course through their veins! "
        narrative += f"{actor_name} regains {mana_amount} mana."

        return {
            "success": True,
            "narrative": narrative,
            "mana_restored": mana_amount,
            "action_cost": self.action_cost
        }

    def _use_bomb(self, actor, item, target, actor_name, item_name):
        """Use explosive item"""
        if not target:
            return {"success": False, "error": "Bomb requires a target"}

        # Calculate damage
        damage = item.get('damage', 15)
        target['current_hp'] = max(0, target['current_hp'] - damage)
        is_dead = target['current_hp'] <= 0

        # Generate narrative
        narrative = f"{actor_name} hurls {item_name} at {target.get('name', 'the target')}! "
        narrative += f"The explosion deals {damage} damage!"
        if is_dead:
            narrative += f" {target.get('name', 'The target')} is defeated by the blast!"

        # Area effect if applicable
        if item.get('area_effect', False):
            narrative += " Nearby units are also affected by the explosion!"
            # In a real implementation, you'd calculate area damage here

        return {
            "success": True,
            "narrative": narrative,
            "damage": damage,
            "target_defeated": is_dead,
            "action_cost": self.action_cost
        }

# Additional action classes can be added here as needed
class SpecialAttackAction(CombatAction):
    """Special attack that consumes a resource"""
    def __init__(self):
        super().__init__(
            "special_attack",
            "Use a special attack ability",
            action_cost=2
        )

    def execute(self, actor, target_id, options):
        ability_name = options.get('ability')
        if not ability_name:
            return {"success": False, "error": "No ability specified"}

        # Find ability
        abilities = actor.get('special_abilities', [])
        ability = next((a for a in abilities if a['name'].lower() == ability_name.lower()), None)

        if not ability:
            return {"success": False, "error": f"Unknown ability: {ability_name}"}

        # Check cooldown
        if ability.get('cooldown_remaining', 0) > 0:
            return {"success": False, "error": f"{ability_name} is on cooldown"}

        # Determine target
        target = None
        if target_id:
            target = self._find_unit(target_id, actor['combat_manager'])
            if not target:
                return {"success": False, "error": "Target not found"}

        # Execute ability
        result = self._execute_ability(actor, ability, target)

        # Set cooldown
        ability['cooldown_remaining'] = ability.get('cooldown', 3)

        return result

    def _execute_ability(self, actor, ability, target):
        """Execute different ability types"""
        ability_type = ability.get('type', 'damage')
        actor_name = actor.get('name', 'The user')
        ability_name = ability['name']

        if ability_type == 'damage':
            return self._execute_damage_ability(actor, ability, target, actor_name, ability_name)
        elif ability_type == 'heal':
            return self._execute_heal_ability(actor, ability, target, actor_name, ability_name)
        else:
            return {
                "success": True,
                "narrative": f"{actor_name} uses {ability_name}!",
                "action_cost": self.action_cost
            }

    def _execute_damage_ability(self, actor, ability, target, actor_name, ability_name):
        """Execute damage ability"""
        if not target:
            return {"success": False, "error": "Damage ability requires a target"}

        # Calculate damage
        base_damage = ability.get('damage', 8)
        attack_power = actor.get('attack_power', 3)
        defense = target.get('defense', 1)
        damage = max(1, base_damage + attack_power - defense)

        # Apply damage
        target['current_hp'] = max(0, target['current_hp'] - damage)
        is_dead = target['current_hp'] <= 0

        # Generate narrative
        narrative = f"{actor_name} unleashes {ability_name} on {target.get('name', 'the target')}! "
        narrative += f"The powerful attack deals {damage} damage!"
        if is_dead:
            narrative += f" {target.get('name', 'The target')} is defeated!"

        return {
            "success": True,
            "narrative": narrative,
            "damage": damage,
            "target_defeated": is_dead,
            "action_cost": self.action_cost
        }

    def _execute_heal_ability(self, actor, ability, target, actor_name, ability_name):
        """Execute healing ability"""
        # Determine target (self if none specified)
        target = target if target else actor

        # Calculate healing
        heal_amount = ability.get('healing', 12)
        target['current_hp'] = min(target.get('max_hp', 10), target['current_hp'] + heal_amount)

        # Generate narrative
        narrative = f"{actor_name} activates {ability_name}, "
        if target == actor:
            narrative += "healing their own wounds!"
        else:
            narrative += f"mending {target.get('name', 'the target')}'s injuries!"

        narrative += f" {target.get('name', 'They')} regain {heal_amount} HP."

        return {
            "success": True,
            "narrative": narrative,
            "healing": heal_amount,
            "action_cost": self.action_cost
        }

# Registry extension for additional actions
def extend_combat_actions(registry):
    """Add additional actions to the registry"""
    registry.actions['cast_spell'] = CastSpellAction()
    registry.actions['use_item'] = UseItemAction()
    registry.actions['special_attack'] = SpecialAttackAction()
    return registry