#!/usr/bin/env python3
"""
Simple test to verify components work independently
"""

import sys
import os
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_components():
    """Test individual components"""
    print("🧪 Testing Components...")
    
    try:
        # Test 1: API Integration
        print("\n1. Testing API Integration...")
        from api_integration import APIManager
        api_manager = APIManager()
        print("✅ API Manager created successfully")
        
        # Test 2: Enhanced Social Calculator
        print("\n2. Testing Enhanced Social Calculator...")
        from enhanced_social_calc import EnhancedSocialCalculator
        social_calc = EnhancedSocialCalculator(api_manager)
        print("✅ Enhanced Social Calculator created successfully")
        
        # Test 3: Test social interaction
        print("\n3. Testing Social Interaction...")
        result = social_calc.resolve_social_interaction(
            npc_id="test_npc",
            interaction_type="appeal",
            player_action="Hello, how are you?",
            difficulty_class=50
        )
        
        print(f"✅ Social interaction result: {result}")
        
        # Test 4: Character Creation
        print("\n4. Testing Character Creation...")
        from character_creation_sequence import create_character_from_backstory
        character = create_character_from_backstory(
            name="Test Character",
            gender="male", 
            race="human",
            backstory="I was a strong warrior who enjoyed fighting and training."
        )
        print(f"✅ Character created: {character['identity']['name']}")
        print(f"Stats: {character['stats']}")
        
        print("\n🎉 All component tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_components()
    sys.exit(0 if success else 1)