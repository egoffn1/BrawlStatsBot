#!/usr/bin/env python3
"""
Test suite for Brawl Stats Data Validator
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
from validate_data import DataValidator


class TestDataValidator:
    """Test cases for the DataValidator class."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.test_dir = None
        
    def setup(self):
        """Create temporary test directories."""
        self.test_dir = tempfile.mkdtemp()
        schemas_dir = Path(self.test_dir) / 'schemas'
        data_dir = Path(self.test_dir) / 'brawl_data'
        schemas_dir.mkdir()
        data_dir.mkdir()
        return schemas_dir, data_dir
    
    def teardown(self):
        """Clean up temporary test directories."""
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def assert_true(self, condition, message=""):
        """Assert that condition is true."""
        if condition:
            self.passed += 1
            print(f"  ✓ {message}")
        else:
            self.failed += 1
            print(f"  ✗ {message}")
    
    def test_player_tag_validation(self):
        """Test player tag validation."""
        print("\nTest: Player Tag Validation")
        validator = DataValidator()
        
        # Valid tags
        self.assert_true(validator.validate_player_tag("#8UG9C0L"), "Valid tag #8UG9C0L")
        self.assert_true(validator.validate_player_tag("#ABC123"), "Valid tag #ABC123")
        self.assert_true(validator.validate_player_tag("#XYZ"), "Valid tag #XYZ")
        
        # Invalid tags
        self.assert_true(not validator.validate_player_tag("8UG9C0L"), "Missing # prefix")
        self.assert_true(not validator.validate_player_tag("#"), "Only # character")
        self.assert_true(not validator.validate_player_tag(""), "Empty string")
        self.assert_true(not validator.validate_player_tag(None), "None value")
    
    def test_date_format_validation(self):
        """Test date format validation."""
        print("\nTest: Date Format Validation")
        validator = DataValidator()
        
        # Valid dates
        self.assert_true(validator.validate_date_format("2025-03-28"), "Valid date 2025-03-28")
        self.assert_true(validator.validate_date_format("2024-01-01"), "Valid date 2024-01-01")
        
        # Invalid dates
        self.assert_true(not validator.validate_date_format("2025/03/28"), "Wrong separator")
        self.assert_true(not validator.validate_date_format("2025-13-01"), "Invalid month")
        self.assert_true(not validator.validate_date_format("2025-00-01"), "Zero month")
        self.assert_true(not validator.validate_date_format(""), "Empty string")
    
    def test_datetime_format_validation(self):
        """Test datetime format validation."""
        print("\nTest: Datetime Format Validation")
        validator = DataValidator()
        
        # Valid datetimes
        self.assert_true(validator.validate_datetime_format("2025-03-28T14:23:00Z"), "UTC datetime")
        self.assert_true(validator.validate_datetime_format("2025-03-28T14:23:00+00:00"), "Timezone datetime")
        
        # Invalid datetimes
        self.assert_true(not validator.validate_datetime_format("2025-03-28 14:23:00"), "Missing T separator")
        self.assert_true(not validator.validate_datetime_format(""), "Empty string")
    
    def test_brawler_power_validation(self):
        """Test brawler power validation."""
        print("\nTest: Brawler Power Validation")
        validator = DataValidator()
        
        # Valid powers
        self.assert_true(validator.validate_brawler_power(1), "Power level 1")
        self.assert_true(validator.validate_brawler_power(11), "Power level 11")
        self.assert_true(validator.validate_brawler_power(5), "Power level 5")
        
        # Invalid powers
        self.assert_true(not validator.validate_brawler_power(0), "Power level 0")
        self.assert_true(not validator.validate_brawler_power(12), "Power level 12")
        self.assert_true(not validator.validate_brawler_power(-1), "Negative power")
    
    def test_game_mode_validation(self):
        """Test game mode validation."""
        print("\nTest: Game Mode Validation")
        validator = DataValidator()
        
        # Valid modes
        self.assert_true(validator.validate_game_mode("Showdown"), "Showdown")
        self.assert_true(validator.validate_game_mode("Gem Grab"), "Gem Grab")
        self.assert_true(validator.validate_game_mode("Brawl Ball"), "Brawl Ball")
        
        # Invalid modes
        self.assert_true(not validator.validate_game_mode("showdown"), "Lowercase showdown")
        self.assert_true(not validator.validate_game_mode("Unknown"), "Unknown mode")
        self.assert_true(not validator.validate_game_mode(""), "Empty string")
    
    def test_player_validation(self):
        """Test player data validation."""
        print("\nTest: Player Data Validation")
        validator = DataValidator()
        
        # Valid player
        valid_player = {
            "tag": "#8UG9C0L",
            "name": "Player1",
            "trophies": 32000,
            "highestTrophies": 33000,
            "brawlers": [
                {"id": 1, "name": "Shelly", "trophies": 750, "power": 11}
            ]
        }
        self.assert_true(validator.validate_player(valid_player), "Valid player object")
        
        # Missing required fields
        invalid_player = {"tag": "#8UG9C0L"}
        self.assert_true(not validator.validate_player(invalid_player), "Missing name and trophies")
        
        # Invalid tag
        invalid_player = {"tag": "INVALID", "name": "Player", "trophies": 1000}
        self.assert_true(not validator.validate_player(invalid_player), "Invalid tag format")
        
        # Negative trophies
        invalid_player = {"tag": "#8UG9C0L", "name": "Player", "trophies": -100}
        self.assert_true(not validator.validate_player(invalid_player), "Negative trophies")
    
    def test_club_validation(self):
        """Test club data validation."""
        print("\nTest: Club Data Validation")
        validator = DataValidator()
        
        # Valid club
        valid_club = {
            "tag": "#CLUB123",
            "name": "Pro Club",
            "trophies": 950000,
            "memberCount": 30,
            "type": "open"
        }
        self.assert_true(validator.validate_club(valid_club), "Valid club object")
        
        # Invalid member count
        invalid_club = {"tag": "#CLUB123", "name": "Club", "trophies": 1000, "memberCount": 50}
        self.assert_true(not validator.validate_club(invalid_club), "Member count > 30")
    
    def test_battle_validation(self):
        """Test battle data validation."""
        print("\nTest: Battle Data Validation")
        validator = DataValidator()
        
        # Valid battle
        valid_battle = {
            "battle_time": "2025-03-28T14:23:00Z",
            "battle_type": "solo",
            "result": "victory",
            "trophies_change": 8,
            "game_mode": "Showdown"
        }
        self.assert_true(validator.validate_battle(valid_battle), "Valid battle object")
        
        # Invalid battle type
        invalid_battle = {
            "battle_time": "2025-03-28T14:23:00Z",
            "battle_type": "unknown",
            "result": "victory"
        }
        self.assert_true(not validator.validate_battle(invalid_battle), "Invalid battle_type")
        
        # Invalid result
        invalid_battle = {
            "battle_time": "2025-03-28T14:23:00Z",
            "battle_type": "solo",
            "result": "win"
        }
        self.assert_true(not validator.validate_battle(invalid_battle), "Invalid result")
    
    def test_rankings_validation(self):
        """Test rankings data validation."""
        print("\nTest: Rankings Data Validation")
        validator = DataValidator()
        
        # Valid rankings
        valid_rankings = {
            "date": "2025-03-28",
            "players": [
                {"tag": "#8UG9C0L", "trophies": 32000, "rank": 1},
                {"tag": "#ABC123", "trophies": 31000, "rank": 2}
            ]
        }
        self.assert_true(validator.validate_rankings(valid_rankings, 'players'), "Valid player rankings")
        
        # Invalid date
        invalid_rankings = {
            "date": "invalid-date",
            "players": []
        }
        self.assert_true(not validator.validate_rankings(invalid_rankings, 'players'), "Invalid date format")
    
    def test_full_validation_workflow(self):
        """Test complete validation workflow with files."""
        print("\nTest: Full Validation Workflow")
        
        schemas_dir, data_dir = self.setup()
        
        try:
            # Create a minimal schema file
            schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Test",
                "type": "object"
            }
            with open(schemas_dir / 'test.schema.json', 'w') as f:
                json.dump(schema, f)
            
            # Create valid data file
            players_dir = data_dir / 'players'
            players_dir.mkdir()
            valid_player = {"tag": "#8UG9C0L", "name": "Test", "trophies": 1000}
            with open(players_dir / 'test.json', 'w') as f:
                json.dump(valid_player, f)
            
            # Run validator
            validator = DataValidator(str(schemas_dir), str(data_dir))
            valid, invalid = validator.validate_all()
            
            self.assert_true(valid == 1 and invalid == 0, f"Validation counts: {valid} valid, {invalid} invalid")
            
        finally:
            self.teardown()
    
    def run_all_tests(self):
        """Run all tests."""
        print("=" * 60)
        print("Brawl Stats Data Validator - Test Suite")
        print("=" * 60)
        
        self.test_player_tag_validation()
        self.test_date_format_validation()
        self.test_datetime_format_validation()
        self.test_brawler_power_validation()
        self.test_game_mode_validation()
        self.test_player_validation()
        self.test_club_validation()
        self.test_battle_validation()
        self.test_rankings_validation()
        self.test_full_validation_workflow()
        
        print("\n" + "=" * 60)
        print(f"Test Results: {self.passed} passed, {self.failed} failed")
        print("=" * 60)
        
        return self.failed == 0


if __name__ == '__main__':
    tester = TestDataValidator()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
