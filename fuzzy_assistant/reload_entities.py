import requests
import yaml
import os
import sys

try:
    from config import HA_URL, HA_TOKEN
except ImportError:
    print("Error: config.py not found. Please copy config.example.py to config.py and update with your settings.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "content-type": "application/json",
}

# Debug configuration
DEBUG = False
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_FILE = os.path.join(SCRIPT_DIR, '.debug_state')

def debug_print(*args, **kwargs):
    """Print debug messages only if DEBUG is True"""
    if DEBUG:
        print("Debug -", *args, **kwargs)

def load_debug_state():
    """Load debug state from file"""
    global DEBUG
    try:
        with open(DEBUG_FILE, 'r') as f:
            DEBUG = f.read().strip().lower() == 'true'
    except FileNotFoundError:
        pass

def reload_entities():
    """Rescan and reload entities from Home Assistant"""
    try:
        # Get all entities from Home Assistant API
        debug_print("Fetching entities from Home Assistant...")
        response = requests.get(f"{HA_URL}/api/states", headers=HEADERS)
        if response.status_code != 200:
            print("Failed to fetch entities from Home Assistant")
            return False
            
        entities = response.json()
        entity_dict = {}
        
        # Debug print all heater-related entities
        if DEBUG:
            debug_print("\nFound heater-related entities in HA:")
            for entity in entities:
                entity_id = entity['entity_id']
                friendly_name = entity.get('attributes', {}).get('friendly_name', entity_id)
                if 'heater' in entity_id.lower() or (friendly_name and 'heater' in friendly_name.lower()):
                    debug_print(f"  ID: {entity_id}")
                    debug_print(f"  Name: {friendly_name}")
                    debug_print(f"  Domain: {entity_id.split('.')[0]}")
                    debug_print(f"  State: {entity['state']}")
                    debug_print(f"  Attributes: {entity['attributes']}\n")
        
        # Process each entity
        for entity in entities:
            entity_id = entity['entity_id']
            friendly_name = entity.get('attributes', {}).get('friendly_name', entity_id)
            domain = entity_id.split('.')[0]
            
            # Create unique name keys for entities with the same friendly name
            base_name_key = friendly_name.lower() if friendly_name else entity_id.lower()
            name_key = base_name_key
            counter = 1
            
            # If this is a duplicate name, append the domain
            if name_key in entity_dict:
                name_key = f"{base_name_key} ({domain})"
            
            entity_dict[name_key] = {
                'domain': domain,
                'entity_id': entity_id,
                'friendly_name': base_name_key
            }
        
        # Save to YAML file
        with open('entities.yaml', 'w') as file:
            yaml.dump(entity_dict, file, sort_keys=True)
            
        print("Entities reloaded successfully")
        return True
        
    except Exception as e:
        print(f"Error reloading entities: {e}")
        return False

def create_entity_index(entities):
    """Create search-optimized index of entity names"""
    name_index = {}
    for name, data in entities.items():
        words = name.lower().split()
        for word in words:
            if word not in name_index:
                name_index[word] = set()
            name_index[word].add(data['entity_id'])
            # Add common abbreviations
            if word == "coffee":
                name_index["cff"] = name_index[word]
                name_index["cof"] = name_index[word]
    return name_index

def main():
    """Main function to reload entities"""
    load_debug_state()
    return reload_entities()

if __name__ == "__main__":
    main() 