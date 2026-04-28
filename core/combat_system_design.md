# TTRPG Combat System Design

## 🏗️ Core Architecture

```
Normal Gameplay → Combat Initiation → Combat Loop → Combat Resolution → Normal Gameplay
```

## 🎯 Key Design Principles

1. **Separate Data Flow** - Combat uses different context than normal gameplay
2. **Turn-Based** - Clear turn order with unit-specific actions
3. **Context-Aware** - AI understands combat situation and available actions
4. **Narrative-Driven** - Rich descriptions of combat events
5. **Modular** - Easy to add new unit types and actions

## 📁 Files to Create/Modify

### **New Files:**
- `combat_manager.py` - Core combat logic
- `combat_actions.py` - Available combat actions
- `combat_ai.py` - AI decision making for NPCs/enemies
- `combat_ui.js` - Combat-specific UI elements

### **Modified Files:**
- `core/game_engine.py` - Add combat state handling
- `core/api_integration.py` - Add combat-specific prompts
- `static/js/main.js` - Add combat UI toggles

## 🎭 Combat State Structure

```python
# In game_engine.py
class GameEngine:
    def __init__(self):
        # ... existing init ...
        self.combat_manager = CombatManager(self)
        self.in_combat = False
    
    def enter_combat(self, enemies, allies=None, environment=None):
        """Initialize combat state"""
        self.in_combat = True
        self.combat_manager.initialize_combat(enemies, allies, environment)
        
        # Switch to combat UI
        if hasattr(self, 'web_interface'):
            self.web_interface.show_combat_ui()
        
        return self.combat_manager.get_combat_state()
    
    def exit_combat(self):
        """Return to normal gameplay"""
        self.in_combat = False
        if hasattr(self, 'web_interface'):
            self.web_interface.show_normal_ui()
        
        # Apply combat results to game state
        self._apply_combat_results()
```

## ⚔️ Combat Manager

```python
# combat_manager.py
class CombatManager:
    def __init__(self, game_engine):
        self.game_engine = game_engine
        self.combat_state = {
            'active': False,
            'turn': 0,
            'round': 1,
            'units': [],      # All combat participants
            'turn_order': [], # Current turn order
            'current_unit': None, # Unit whose turn it is
            'log': [],        # Combat actions/results
            'environment': {}, # Terrain, weather, etc.
            'initiative_bonuses': {} # Unit-specific initiative mods
        }
        self.action_registry = self._load_combat_actions()
    
    def initialize_combat(self, enemies, allies=None, environment=None):
        """Set up combat with participants and environment"""
        self.combat_state = {
            'active': True,
            'turn': 0,
            'round': 1,
            'units': [],
            'turn_order': [],
            'current_unit': None,
            'log': [],
            'environment': environment or {},
            'initiative_bonuses': {}
        }
        
        # Add all participants
        self._add_combat_units(enemies, 'enemy')
        if allies:
            self._add_combat_units(allies, 'ally')
        
        # Determine turn order
        self._calculate_initiative()
        
        # Start first turn
        self.combat_state['current_unit'] = self.combat_state['turn_order'][0]
        
        return self.combat_state
    
    def _add_combat_units(self, units, team):
        """Add units to combat with team affiliation"""
        for unit in units:
            unit['team'] = team
            unit['combat_id'] = f"{team}_{len(self.combat_state['units']) + 1}"
            unit['current_hp'] = unit.get('max_hp', unit.get('hp', 10))
            unit['status_effects'] = unit.get('status_effects', [])
            unit['actions_taken'] = 0
            self.combat_state['units'].append(unit)
    
    def _calculate_initiative(self):
        """Determine turn order based on initiative"""
        initiative_order = []
        
        for unit in self.combat_state['units']:
            base_initiative = unit.get('initiative', 10)
            bonus = self.combat_state['initiative_bonuses'].get(unit['combat_id'], 0)
            initiative_order.append((unit['combat_id'], base_initiative + bonus))
        
        # Sort by initiative (highest first)
        initiative_order.sort(key=lambda x: x[1], reverse=True)
        self.combat_state['turn_order'] = [unit_id for unit_id, initiative in initiative_order]
    
    def get_current_unit(self):
        """Get the unit whose turn it is"""
        if not self.combat_state['active']:
            return None
        
        unit_id = self.combat_state['current_unit']
        return self._get_unit_by_id(unit_id)
    
    def _get_unit_by_id(self, unit_id):
        """Find unit by combat ID"""
        for unit in self.combat_state['units']:
            if unit['combat_id'] == unit_id:
                return unit
        return None
    
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
        for unit in self.combat_state['units']:
            unit['actions_taken'] = 0
        
        return self.combat_state
    
    def resolve_combat_action(self, unit_id, action_data):
        """Process a unit's combat action"""
        unit = self._get_unit_by_id(unit_id)
        if not unit:
            return {"success": False, "error": "Unit not found"}
        
        # Get action details
        action_type = action_data['action']
        target_id = action_data.get('target')
        
        if action_type not in self.action_registry:
            return {"success": False, "error": "Invalid action"}
        
        # Execute the action
        action_handler = self.action_registry[action_type]
        result = action_handler.execute(unit, target_id, action_data.get('options', {}))
        
        # Log the action
        self._log_combat_action(unit_id, action_type, target_id, result)
        
        # Check for combat end conditions
        if self._check_combat_end():
            result['combat_ended'] = True
            result['winner'] = self._determine_winner()
        
        return result
    
    def _log_combat_action(self, unit_id, action_type, target_id, result):
        """Record action in combat log"""
        unit = self._get_unit_by_id(unit_id)
        target = self._get_unit_by_id(target_id) if target_id else None
        
        log_entry = {
            'turn': self.combat_state['turn'],
            'round': self.combat_state['round'],
            'unit': unit['combat_id'],
            'unit_name': unit.get('name', 'Unknown'),
            'action': action_type,
            'target': target_id,
            'target_name': target.get('name', 'None') if target else None,
            'result': result,
            'timestamp': datetime.now().isoformat()
        }
        
        self.combat_state['log'].append(log_entry)
        
        # Keep log manageable
        if len(self.combat_state['log']) > 50:
            self.combat_state['log'] = self.combat_state['log'][-50:]
    
    def _check_combat_end(self):
        """Check if combat should end"""
        # Check if one team is completely defeated
        enemy_alive = any(u for u in self.combat_state['units'] if u['team'] == 'enemy' and u['current_hp'] > 0)
        ally_alive = any(u for u in self.combat_state['units'] if u['team'] == 'ally' and u['current_hp'] > 0)
        
        # Combat ends if only one team has living units
        return not (enemy_alive and ally_alive)
    
    def _determine_winner(self):
        """Determine which team won"""
        enemy_alive = any(u for u in self.combat_state['units'] if u['team'] == 'enemy' and u['current_hp'] > 0)
        return 'enemies' if enemy_alive else 'allies'
    
    def get_combat_summary(self):
        """Get summary of current combat state"""
        return {
            'round': self.combat_state['round'],
            'turn': self.combat_state['turn'],
            'current_unit': self.combat_state['current_unit'],
            'units': [self._get_unit_summary(u) for u in self.combat_state['units']],
            'log': self.combat_state['log'][-10:],  # Last 10 actions
            'environment': self.combat_state['environment']
        }
    
    def _get_unit_summary(self, unit):
        """Get public-facing unit info"""
        return {
            'combat_id': unit['combat_id'],
            'name': unit.get('name', 'Unknown'),
            'team': unit['team'],
            'current_hp': unit['current_hp'],
            'max_hp': unit.get('max_hp', unit.get('hp', 10)),
            'status_effects': unit['status_effects'],
            'position': unit.get('position', 'unknown')
        }
    
    def _load_combat_actions(self):
        """Load available combat actions"""
        from combat_actions import CombatActionRegistry
        return CombatActionRegistry()
```

## 🎯 Combat-Specific API Prompts

```python
# In api_integration.py
class APIManager:
    # ... existing methods ...
    
    def generate_combat_action(self, combat_state, unit, available_actions):
        """Generate AI response for combat turn"""
        unit_name = unit.get('name', unit.get('combat_id', 'Unknown'))
        
        # Create combat-specific context
        context = {
            'situation': self._create_combat_situation_summary(combat_state),
            'unit': self._create_unit_description(unit, available_actions),
            'combat_log': self._format_combat_log(combat_state['log'][-5:]),  # Last 5 actions
            'environment': combat_state.get('environment', {})
        }
        
        prompt = self._build_combat_prompt(context)
        
        # Use API or fallback
        if self.api_key:
            return self._call_api_with_fallback(prompt, "combat_action")
        else:
            return self._generate_fallback_combat_action(context)
    
    def _create_combat_situation_summary(self, combat_state):
        """Summarize current combat situation"""
        summary = f"Combat Round {combat_state['round']}, Turn {combat_state['turn']}\n"
        summary += f"Location: {combat_state.get('environment', {}).get('name', 'unknown')}\n"
        summary += f"Current Unit: {combat_state['current_unit']}\n\n"
        
        # Team status
        enemies = [u for u in combat_state['units'] if u['team'] == 'enemy' and u['current_hp'] > 0]
        allies = [u for u in combat_state['units'] if u['team'] == 'ally' and u['current_hp'] > 0]
        
        summary += f"Enemies Alive: {len(enemies)}\n"
        summary += f"Allies Alive: {len(allies)}\n\n"
        
        # Recent events
        if combat_state['log']:
            last_action = combat_state['log'][-1]
            summary += f"Last Action: {last_action['unit_name']} {last_action['action']} "
            if last_action['target']:
                summary += f"against {last_action['target_name']}"
            summary += "\n"
        
        return summary
    
    def _create_unit_description(self, unit, available_actions):
        """Describe unit and available actions"""
        description = f"Unit: {unit.get('name', unit.get('combat_id', 'Unknown'))}\n"
        description += f"Type: {unit.get('type', 'unknown')}\n"
        description += f"HP: {unit['current_hp']}/{unit.get('max_hp', unit.get('hp', 10))}\n"
        description += f"Status: {', '.join(unit['status_effects']) if unit['status_effects'] else 'normal'}\n"
        description += f"Position: {unit.get('position', 'unknown')}\n\n"
        
        description += "Available Actions:\n"
        for action_name, action_data in available_actions.items():
            cost = action_data.get('action_cost', 1)
            description += f"- {action_name}: {action_data.get('description', 'No description')}"
            if cost > 1:
                description += f" (Costs {cost} action points)"
            description += "\n"
        
        return description
    
    def _format_combat_log(self, log_entries):
        """Format recent combat actions for context"""
        if not log_entries:
            return "No recent actions."
        
        log_text = "Recent Combat Actions:\n"
        for entry in log_entries:
            log_text += f"{entry['unit_name']} {entry['action']}"
            if entry['target']:
                log_text += f" against {entry['target_name']}"
            log_text += f" - {entry['result'].get('narrative', 'unknown result')}\n"
        
        return log_text
    
    def _build_combat_prompt(self, context):
        """Create prompt for combat AI decision"""
        prompt = f"""
        ISEKAI RPG COMBAT AI - Turn Resolution
        
        {context['situation']}
        
        {context['unit']}
        
        {context['combat_log']}
        
        ENVIRONMENT:
        {context['environment'].get('description', 'No special environment effects')}
        
        INSTRUCTIONS:
        1. Analyze the current combat situation
        2. Choose the most appropriate action for this unit
        3. Provide a vivid narrative description of the action and results
        4. Calculate any damage/healing/effects based on unit stats
        5. Return structured JSON with narrative and game effects
        
        RESPONSE FORMAT:
        {{
          "thought_process": "Your reasoning about why this action was chosen",
          "action": "action_name",
          "target": "target_unit_id_or_none",
          "narrative": "Vivid description of what happens (2-3 sentences)",
          "effects": {{
            "damage": amount_or_null,
            "healing": amount_or_null,
            "status_effects": ["effect1", "effect2"]_or_null,
            "position_change": "description_or_null",
            "special": "any_other_effects_or_null"
          }},
          "action_cost": number_of_action_points_used
        }}
        
        IMPORTANT: Stay true to the unit's personality and tactics. Be creative but fair. Use the environment if relevant.
        """
        
        return prompt
    
    def _generate_fallback_combat_action(self, context):
        """Rule-based fallback when API unavailable"""
        unit = context['unit_data']
        available_actions = context['available_actions']
        
        # Simple AI logic for fallback
        if unit['current_hp'] < unit.get('max_hp', 10) * 0.3:
            # Low HP - try to heal or defend
            if 'heal' in available_actions:
                return self._create_fallback_response('heal', None, unit)
            elif 'defend' in available_actions:
                return self._create_fallback_response('defend', None, unit)
        
        # Default to basic attack
        if 'attack' in available_actions:
            # Find weakest enemy
            enemies = [u for u in context['combat_state']['units'] 
                      if u['team'] == 'enemy' and u['current_hp'] > 0]
            if enemies:
                target = min(enemies, key=lambda x: x['current_hp'])
                return self._create_fallback_response('attack', target['combat_id'], unit, target)
        
        # Last resort - wait
        return self._create_fallback_response('wait', None, unit)
    
    def _create_fallback_response(self, action, target_id, unit, target=None):
        """Create structured fallback response"""
        response = {
            "thought_process": f"Fallback AI chose {action} based on simple rules",
            "action": action,
            "target": target_id,
            "narrative": f"{unit.get('name', 'The unit')} {action}s",
            "effects": {},
            "action_cost": 1
        }
        
        if target:
            response["narrative"] += f" {target.get('name', 'the target')}"
            if action == "attack":
                damage = max(1, unit.get('attack_power', 3) - target.get('defense', 1))
                response["effects"]["damage"] = damage
                response["narrative"] += f" for {damage} damage"
        
        return response
```

## 🎮 Combat Action System

```python
# combat_actions.py
class CombatAction:
    """Base class for combat actions"""
    def __init__(self, name, description, action_cost=1):
        self.name = name
        self.description = description
        self.action_cost = action_cost
    
    def execute(self, actor, target_id, options):
        """Execute this action and return results"""
        raise NotImplementedError("Subclasses must implement execute()")
    
    def is_valid_target(self, actor, target):
        """Check if target is valid for this action"""
        return True

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
    
    def _find_unit(self, unit_id, combat_manager):
        """Find unit by ID"""
        return combat_manager._get_unit_by_id(unit_id)

class CombatActionRegistry:
    """Registry of all available combat actions"""
    def __init__(self):
        self.actions = {
            'attack': AttackAction(),
            'defend': self._create_defend_action(),
            'heal': self._create_heal_action(),
            'wait': self._create_wait_action(),
            'flee': self._create_flee_action(),
            'use_item': self._create_use_item_action(),
            'cast_spell': self._create_cast_spell_action()
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
        if action.name == 'cast_spell' and not unit.get('spells', []):
            return False
        return True
    
    # Action creators...
    def _create_defend_action(self):
        return DefendAction()
    
    def _create_heal_action(self):
        return HealAction()
    
    def _create_wait_action(self):
        return WaitAction()
    
    def _create_flee_action(self):
        return FleeAction()
    
    def _create_use_item_action(self):
        return UseItemAction()
    
    def _create_cast_spell_action(self):
        return CastSpellAction()

# Additional action classes would be defined here...
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
```

## 🎨 Combat UI Integration

```javascript
// combat_ui.js - Add to static/js/

class CombatUI {
    constructor() {
        this.combatActive = false;
        this.currentUnit = null;
    }
    
    showCombatUI() {
        this.combatActive = true;
        this._createCombatOverlay();
        this._createActionPanel();
        this._createCombatLog();
        this._switchToCombatMode();
    }
    
    showNormalUI() {
        this.combatActive = false;
        this._removeCombatElements();
        this._switchToNormalMode();
    }
    
    updateCombatState(combatState) {
        if (!this.combatActive) return;
        
        this._updateUnitDisplay(combatState);
        this._updateActionPanel(combatState);
        this._updateCombatLog(combatState.log);
        this._highlightCurrentUnit(combatState.current_unit);
    }
    
    _createCombatOverlay() {
        // Create combat-specific UI overlay
        const overlay = document.createElement('div');
        overlay.id = 'combatOverlay';
        overlay.className = 'combat-overlay';
        
        // Add combat-specific styles
        const style = document.createElement('style');
        style.textContent = `
            .combat-overlay {
                position: fixed;
                top: 30px; /* Below token counter */
                left: 0;
                right: 0;
                bottom: 0;
                pointer-events: none;
                z-index: 50;
            }
            
            .combat-unit-display {
                position: absolute;
                bottom: 20px;
                left: 20px;
                background: rgba(0, 0, 0, 0.7);
                padding: 15px;
                border-radius: 10px;
                border: 2px solid #00ffaa;
                max-width: 300px;
                pointer-events: auto;
            }
            
            .combat-actions {
                position: absolute;
                bottom: 20px;
                right: 20px;
                background: rgba(0, 0, 0, 0.7);
                padding: 15px;
                border-radius: 10px;
                border: 2px solid #ffaa00;
                max-width: 350px;
                pointer-events: auto;
            }
            
            .combat-log {
                position: absolute;
                top: 10px;
                right: 20px;
                background: rgba(0, 0, 0, 0.6);
                padding: 10px;
                border-radius: 8px;
                max-width: 400px;
                max-height: 300px;
                overflow-y: auto;
                font-size: 0.9rem;
                pointer-events: auto;
            }
            
            .unit-turn-indicator {
                background: #ffaa00;
                padding: 8px 15px;
                border-radius: 20px;
                margin-bottom: 10px;
                text-align: center;
                font-weight: bold;
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
            
            .action-button {
                display: block;
                width: 100%;
                padding: 10px;
                margin: 5px 0;
                background: #222;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                pointer-events: auto;
            }
            
            .action-button:hover {
                background: #00ffaa;
                color: #111;
            }
            
            .action-button:disabled {
                background: #444;
                color: #888;
                cursor: not-allowed;
            }
            
            .health-bar {
                height: 20px;
                background: #333;
                border-radius: 10px;
                overflow: hidden;
                margin: 8px 0;
            }
            
            .health-fill {
                height: 100%;
                background: linear-gradient(90deg, #ff2a2a, #ffaa00);
                transition: width 0.3s ease;
            }
            
            .combat-unit {
                display: flex;
                align-items: center;
                gap: 10px;
                margin: 10px 0;
                padding: 8px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 6px;
            }
            
            .unit-current {
                border: 2px solid #00ffaa;
            }
        `;
        
        document.head.appendChild(style);
        document.body.appendChild(overlay);
    }
    
    _updateUnitDisplay(combatState) {
        const display = document.getElementById('unitDisplay') || this._createUnitDisplay();
        
        const currentUnit = combatState.units.find(u => u.combat_id === combatState.current_unit);
        
        if (currentUnit) {
            const healthPercent = (currentUnit.current_hp / currentUnit.max_hp) * 100;
            display.innerHTML = `
                <div class="unit-turn-indicator">⚔️ ${currentUnit.name}'s Turn</div>
                <div class="combat-unit unit-current">
                    <div>
                        <strong>${currentUnit.name}</strong><br>
                        <small>${currentUnit.team === 'ally' ? 'Ally' : 'Enemy'}</small>
                    </div>
                </div>
                <div class="health-bar">
                    <div class="health-fill" style="width: ${healthPercent}%"></div>
                </div>
                <div>HP: ${currentUnit.current_hp}/${currentUnit.max_hp}</div>
                ${currentUnit.status_effects.length > 0 ? `
                <div>Status: ${currentUnit.status_effects.join(', ')}</div>
                ` : ''}
            `;
        }
    }
    
    // Additional UI methods would go here...
    _createUnitDisplay() {
        const display = document.createElement('div');
        display.id = 'unitDisplay';
        display.className = 'combat-unit-display';
        document.getElementById('combatOverlay').appendChild(display);
        return display;
    }
    
    _switchToCombatMode() {
        // Modify existing UI for combat
        const playerInput = document.getElementById('playerInput');
        if (playerInput) {
            playerInput.placeholder = "Describe your combat action... (attack, defend, cast spell, etc.)";
        }
    }
    
    _switchToNormalMode() {
        // Restore normal UI
        const playerInput = document.getElementById('playerInput');
        if (playerInput) {
            playerInput.placeholder = "Describe your action...";
        }
    }
}

// Initialize combat UI when needed
const combatUI = new CombatUI();
```

## 🎮 Integration with Game Engine

```python
# In game_engine.py
class GameEngine:
    # ... existing methods ...
    
    def process_combat_turn(self, player_action=None):
        """Process a combat turn - player or AI"""
        if not self.in_combat:
            return {"error": "Not in combat"}
        
        current_unit = self.combat_manager.get_current_unit()
        
        if current_unit['team'] == 'ally' and player_action:
            # Player-controlled unit
            result = self._process_player_combat_action(player_action)
        else:
            # AI-controlled unit
            result = self._process_ai_combat_turn(current_unit)
        
        # Check if combat ended
        if result.get('combat_ended'):
            self.exit_combat()
        else:
            # Advance to next turn
            self.combat_manager.advance_turn()
        
        return result
    
    def _process_player_combat_action(self, action_description):
        """Parse and execute player's combat action"""
        current_unit = self.combat_manager.get_current_unit()
        available_actions = self.combat_manager.action_registry.get_available_actions(current_unit)
        
        # Parse natural language action
        parsed_action = self._parse_combat_action(action_description, available_actions)
        
        if not parsed_action:
            return {
                "success": False,
                "error": "Invalid action. Try: 'attack goblin', 'cast fireball at demon', 'use health potion', etc."
            }
        
        # Execute the action
        return self.combat_manager.resolve_combat_action(
            current_unit['combat_id'],
            parsed_action
        )
    
    def _process_ai_combat_turn(self, unit):
        """Generate and execute AI combat action"""
        available_actions = self.combat_manager.action_registry.get_available_actions(unit)
        combat_state = self.combat_manager.get_combat_summary()
        
        # Get AI decision
        ai_response = self.api_manager.generate_combat_action(
            combat_state,
            unit,
            available_actions
        )
        
        # Execute the AI's chosen action
        return self.combat_manager.resolve_combat_action(
            unit['combat_id'],
            {
                'action': ai_response['action'],
                'target': ai_response.get('target'),
                'options': ai_response.get('options', {})
            }
        )
    
    def _parse_combat_action(self, description, available_actions):
        """Convert natural language to structured action"""
        desc_lower = description.lower()
        
        # Try to match action type
        if any(word in desc_lower for word in ['attack', 'hit', 'strike', 'slash']):
            return self._parse_attack_action(desc_lower)
        elif any(word in desc_lower for word in ['defend', 'block', 'guard']):
            return {'action': 'defend'}
        elif any(word in desc_lower for word in ['heal', 'cure', 'restore']):
            return self._parse_heal_action(desc_lower)
        elif any(word in desc_lower for word in ['cast', 'spell', 'magic']):
            return self._parse_cast_action(desc_lower)
        elif any(word in desc_lower for word in ['use', 'drink', 'consume']):
            return self._parse_use_item_action(desc_lower)
        elif any(word in desc_lower for word in ['flee', 'run', 'escape']):
            return {'action': 'flee'}
        elif any(word in desc_lower for word in ['wait', 'hold', 'pass']):
            return {'action': 'wait'}
        
        return None
    
    def _parse_attack_action(self, description):
        """Parse attack action with target"""
        # Find target in description
        targets = []
        for unit in self.combat_manager.combat_state['units']:
            if unit['team'] == 'enemy' and unit['current_hp'] > 0:
                if unit['name'].lower() in description:
                    targets.append(unit['combat_id'])
        
        if targets:
            return {'action': 'attack', 'target': targets[0]}
        else:
            # Attack random enemy if no specific target
            enemies = [u for u in self.combat_manager.combat_state['units'] 
                      if u['team'] == 'enemy' and u['current_hp'] > 0]
            if enemies:
                return {'action': 'attack', 'target': random.choice(enemies)['combat_id']}
        
        return {'action': 'attack'}
    
    # Additional parsing methods...
```

## 📊 Combat Flow Example

```
Player Action → Parse → Validate → Execute → Narrate → Advance Turn → Repeat
```

### **Example Combat Turn:**

1. **Player Input:** `"I attack the grey-skinned demon with my sword"`
2. **Parse:** `{'action': 'attack', 'target': 'enemy_1'}`
3. **Validate:** Check if target exists and is valid
4. **Execute:** Calculate damage, apply effects
5. **Narrate:** `"You strike the grey-skinned demon with your sword, dealing 7 damage!"`
6. **Advance:** Next unit's turn
7. **AI Turn:** Demon decides action via API
8. **Repeat:** Until combat ends

## 🎯 Key Advantages

1. **Separate Data Flow** - Combat doesn't interfere with normal gameplay context
2. **AI-Driven NPCs** - Enemies make intelligent decisions via same AI
3. **Natural Language** - Players describe actions naturally
4. **Rich Narrative** - Vivid combat descriptions from AI
5. **Flexible Actions** - Easy to add new combat abilities
6. **Turn-Based Clarity** - Clear structure for complex interactions
7. **Context Preservation** - AI has full combat context for decisions

## 🚀 Implementation Steps

1. **Create combat_manager.py** - Core combat logic
2. **Create combat_actions.py** - Available actions
3. **Add combat UI** - Visual combat elements
4. **Modify game_engine.py** - Combat state handling
5. **Update API prompts** - Combat-specific contexts
6. **Test combat flow** - Ensure smooth transitions
7. **Balance actions** - Adjust damage/effects as needed

This design gives you a **flexible, AI-powered combat system** that integrates seamlessly with your open-ended gameplay while providing the structure needed for turn-based combat!
