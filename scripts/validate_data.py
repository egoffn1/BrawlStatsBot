#!/usr/bin/env python3
"""
Brawl Stats Data Validator
Validates JSON data files against their schemas.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple


class DataValidator:
    """Validates Brawl Stars data files against JSON schemas."""
    
    def __init__(self, schemas_dir: str = "schemas", data_dir: str = "brawl_data"):
        self.schemas_dir = Path(schemas_dir)
        self.data_dir = Path(data_dir)
        self.schemas: Dict[str, Dict] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def load_schemas(self) -> bool:
        """Load all JSON schemas from the schemas directory."""
        if not self.schemas_dir.exists():
            self.errors.append(f"Schemas directory not found: {self.schemas_dir}")
            return False
            
        for schema_file in self.schemas_dir.glob("*.schema.json"):
            try:
                with open(schema_file, 'r') as f:
                    schema_name = schema_file.stem.replace('.schema', '')
                    self.schemas[schema_name] = json.load(f)
            except json.JSONDecodeError as e:
                self.errors.append(f"Invalid JSON in schema {schema_file}: {e}")
            except Exception as e:
                self.errors.append(f"Error loading schema {schema_file}: {e}")
                
        return len(self.errors) == 0
    
    def validate_player_tag(self, tag: str) -> bool:
        """Validate player/club tag format."""
        if not tag or not isinstance(tag, str):
            return False
        return tag.startswith('#') and len(tag) >= 4
    
    def validate_date_format(self, date_str: str) -> bool:
        """Validate YYYY-MM-DD date format."""
        if not date_str or not isinstance(date_str, str):
            return False
        parts = date_str.split('-')
        if len(parts) != 3:
            return False
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            return 2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31
        except ValueError:
            return False
    
    def validate_datetime_format(self, dt_str: str) -> bool:
        """Validate ISO 8601 datetime format."""
        if not dt_str or not isinstance(dt_str, str):
            return False
        return 'T' in dt_str and ('Z' in dt_str or '+' in dt_str or '-' in dt_str)
    
    def validate_brawler_power(self, power: Any) -> bool:
        """Validate brawler power level (1-11)."""
        try:
            return 1 <= int(power) <= 11
        except (ValueError, TypeError):
            return False
    
    def validate_game_mode(self, mode: str) -> bool:
        """Validate game mode name."""
        valid_modes = [
            "Showdown", "Gem Grab", "Heist", "Bounty", "Hot Zone", 
            "Knockout", "Brawl Ball", "Volleyball", "Basketball", 
            "Wipeout", "Payload"
        ]
        return mode in valid_modes
    
    def validate_player(self, data: Dict) -> bool:
        """Validate player data structure."""
        required = ['tag', 'name', 'trophies']
        for field in required:
            if field not in data:
                self.errors.append(f"Missing required field: {field}")
                return False
        
        if not self.validate_player_tag(data['tag']):
            self.errors.append(f"Invalid player tag: {data['tag']}")
            return False
            
        if not isinstance(data['trophies'], int) or data['trophies'] < 0:
            self.errors.append(f"Invalid trophies value: {data['trophies']}")
            return False
            
        if 'brawlers' in data:
            for brawler in data['brawlers']:
                if 'power' in brawler and not self.validate_brawler_power(brawler['power']):
                    self.errors.append(f"Invalid brawler power: {brawler['power']}")
                    
        return True
    
    def validate_club(self, data: Dict) -> bool:
        """Validate club data structure."""
        required = ['tag', 'name', 'trophies']
        for field in required:
            if field not in data:
                self.errors.append(f"Missing required field: {field}")
                return False
        
        if not self.validate_player_tag(data['tag']):
            self.errors.append(f"Invalid club tag: {data['tag']}")
            return False
            
        if 'memberCount' in data:
            if not isinstance(data['memberCount'], int) or not 1 <= data['memberCount'] <= 30:
                self.errors.append(f"Invalid member count: {data['memberCount']}")
                return False
                
        return True
    
    def validate_battle(self, data: Dict) -> bool:
        """Validate battle data structure."""
        required = ['battle_time', 'battle_type', 'result']
        for field in required:
            if field not in data:
                self.errors.append(f"Missing required field: {field}")
                return False
        
        if not self.validate_datetime_format(data['battle_time']):
            self.errors.append(f"Invalid battle_time format: {data['battle_time']}")
            return False
            
        if data['battle_type'] not in ['solo', 'duo', 'team', 'challenge']:
            self.errors.append(f"Invalid battle_type: {data['battle_type']}")
            return False
            
        if data['result'] not in ['victory', 'defeat', 'draw']:
            self.errors.append(f"Invalid result: {data['result']}")
            return False
            
        if 'game_mode' in data and not self.validate_game_mode(data['game_mode']):
            self.errors.append(f"Invalid game_mode: {data['game_mode']}")
            
        return True
    
    def validate_rankings(self, data: Dict, type_name: str = "players") -> bool:
        """Validate rankings data structure."""
        if 'date' not in data or not self.validate_date_format(data['date']):
            self.errors.append(f"Invalid or missing date in rankings")
            return False
            
        if type_name not in data:
            self.errors.append(f"Missing '{type_name}' array in rankings")
            return False
            
        for entry in data[type_name]:
            if 'tag' not in entry or not self.validate_player_tag(entry['tag']):
                self.errors.append(f"Invalid tag in rankings entry: {entry.get('tag')}")
                return False
                
        return True
    
    def validate_file(self, file_path: Path, schema_name: str) -> bool:
        """Validate a single data file."""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in {file_path}: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error reading {file_path}: {e}")
            return False
        
        # Clear errors specific to this validation
        prev_errors = len(self.errors)
        
        # Route to appropriate validator
        if schema_name == 'player':
            valid = self.validate_player(data)
        elif schema_name == 'club':
            valid = self.validate_club(data)
        elif schema_name == 'battle':
            if isinstance(data, list):
                valid = all(self.validate_battle(item) for item in data) if data else True
            else:
                valid = self.validate_battle(data)
        elif schema_name == 'trophy_history':
            valid = True
            if isinstance(data, list):
                for entry in data:
                    if 'date' in entry and not self.validate_date_format(entry['date']):
                        self.errors.append(f"Invalid date in trophy history: {entry['date']}")
                        valid = False
        elif schema_name == 'club_history':
            valid = True
            if isinstance(data, list):
                for entry in data:
                    if 'date' in entry and not self.validate_date_format(entry['date']):
                        self.errors.append(f"Invalid date in club history: {entry['date']}")
                        valid = False
        elif schema_name == 'player_rankings':
            valid = self.validate_rankings(data, 'players')
        elif schema_name == 'club_rankings':
            valid = self.validate_rankings(data, 'clubs')
        elif schema_name == 'team_stats':
            valid = True
            if 'player_tags' in data:
                for tag in data['player_tags']:
                    if not self.validate_player_tag(tag):
                        self.errors.append(f"Invalid player tag in team stats: {tag}")
                        valid = False
        elif schema_name == 'team_code':
            valid = True
            if 'code' in data:
                code = data['code']
                if not (isinstance(code, str) and len(code) == 7 and code.isalnum()):
                    self.errors.append(f"Invalid team code format: {code}")
                    valid = False
        elif schema_name == 'map_stats':
            valid = True
            if isinstance(data, list):
                for entry in data:
                    if 'game_mode' in entry and not self.validate_game_mode(entry['game_mode']):
                        self.errors.append(f"Invalid game_mode in map stats: {entry['game_mode']}")
                        valid = False
        else:
            self.warnings.append(f"No specific validator for schema: {schema_name}")
            valid = True
            
        return valid and len(self.errors) == prev_errors
    
    def validate_all(self) -> Tuple[int, int]:
        """Validate all data files. Returns (valid_count, invalid_count)."""
        valid_count = 0
        invalid_count = 0
        
        mapping = {
            'players': 'player',
            'clubs': 'club',
            'battles': 'battle',
            'trophy_history': 'trophy_history',
            'club_history': 'club_history',
            'team_stats': 'team_stats',
            'team_codes': 'team_code',
        }
        
        # Validate player files
        players_dir = self.data_dir / 'players'
        if players_dir.exists():
            for file in players_dir.glob('*.json'):
                if self.validate_file(file, 'player'):
                    valid_count += 1
                else:
                    invalid_count += 1
                    
        # Validate club files
        clubs_dir = self.data_dir / 'clubs'
        if clubs_dir.exists():
            for file in clubs_dir.glob('*.json'):
                if self.validate_file(file, 'club'):
                    valid_count += 1
                else:
                    invalid_count += 1
        
        # Validate battle files
        battles_dir = self.data_dir / 'battles'
        if battles_dir.exists():
            for file in battles_dir.glob('*.json'):
                if self.validate_file(file, 'battle'):
                    valid_count += 1
                else:
                    invalid_count += 1
        
        # Validate trophy history
        trophy_dir = self.data_dir / 'trophy_history'
        if trophy_dir.exists():
            for file in trophy_dir.glob('*.json'):
                if self.validate_file(file, 'trophy_history'):
                    valid_count += 1
                else:
                    invalid_count += 1
        
        # Validate club history
        club_hist_dir = self.data_dir / 'club_history'
        if club_hist_dir.exists():
            for file in club_hist_dir.glob('*.json'):
                if self.validate_file(file, 'club_history'):
                    valid_count += 1
                else:
                    invalid_count += 1
        
        # Validate team stats
        team_stats_dir = self.data_dir / 'team_stats'
        if team_stats_dir.exists():
            for file in team_stats_dir.glob('*.json'):
                if self.validate_file(file, 'team_stats'):
                    valid_count += 1
                else:
                    invalid_count += 1
        
        # Validate team codes
        team_codes_dir = self.data_dir / 'team_codes'
        if team_codes_dir.exists():
            for file in team_codes_dir.glob('*.json'):
                if self.validate_file(file, 'team_code'):
                    valid_count += 1
                else:
                    invalid_count += 1
        
        # Validate rankings
        rankings_dir = self.data_dir / 'rankings'
        if rankings_dir.exists():
            # Player rankings
            players_rankings = rankings_dir / 'players'
            if players_rankings.exists():
                for file in players_rankings.glob('*.json'):
                    if self.validate_file(file, 'player_rankings'):
                        valid_count += 1
                    else:
                        invalid_count += 1
            
            # Club rankings
            clubs_rankings = rankings_dir / 'clubs'
            if clubs_rankings.exists():
                for file in clubs_rankings.glob('*.json'):
                    if self.validate_file(file, 'club_rankings'):
                        valid_count += 1
                    else:
                        invalid_count += 1
        
        # Validate map_stats.json
        map_stats_file = self.data_dir / 'map_stats.json'
        if map_stats_file.exists():
            if self.validate_file(map_stats_file, 'map_stats'):
                valid_count += 1
            else:
                invalid_count += 1
                
        return valid_count, invalid_count
    
    def run(self) -> int:
        """Run validation and return exit code."""
        print("=" * 60)
        print("Brawl Stats Data Validator")
        print("=" * 60)
        
        if not self.load_schemas():
            print("\n❌ Failed to load schemas")
            for error in self.errors:
                print(f"   {error}")
            return 1
            
        print(f"\n✓ Loaded {len(self.schemas)} schemas")
        
        valid, invalid = self.validate_all()
        
        print(f"\n{'=' * 60}")
        print(f"Results: {valid} valid, {invalid} invalid")
        
        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"   • {error}")
                
        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        if invalid > 0 or self.errors:
            print("\n❌ Validation FAILED")
            return 1
        else:
            print("\n✅ Validation PASSED")
            return 0


if __name__ == '__main__':
    validator = DataValidator()
    sys.exit(validator.run())
