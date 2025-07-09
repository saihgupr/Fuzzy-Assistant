import requests
import yaml
from fuzzywuzzy import fuzz
import sys
import re
import os
import time

try:
    from config import HA_URL, HA_TOKEN, DEFAULT_ENTITIES
except ImportError:
    print("Error: config.py not found. Please copy config.example.py to config.py and update with your settings.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "content-type": "application/json",
}

# Hardcoded for performance
MEDIA_COMMANDS = {
    "play": "media_play",
    "pause": "media_pause",
    "stop": "media_pause",
    "next": "media_next_track",
    "previous": "media_previous_track",
    "prev": "media_previous_track",
    "volume up": "volume_up",
    "volume down": "volume_down",
    "on": "turn_on",
    "off": "turn_off",
    "status": "status"
}

BRIGHTNESS_PHRASES = {
    "increase": "brightness_up",
    "raise": "brightness_up",
    "up": "brightness_up",
    "brighter": "brightness_up",
    "decrease": "brightness_down",
    "lower": "brightness_down",
    "down": "brightness_down",
    "dim": "brightness_down",
    "dimmer": "brightness_down",
}

# Add to the constants at the top
FAN_SPEEDS = {
    "high": 100,
    "medium": 66,
    "low": 33,
    "off": 0
}

# Add to constants at top
HVAC_MODE = "heat"  # or "cool" for AC

# Global cache for entities
_ENTITIES_CACHE = None

# Domain categories for default intent determination
QUERY_DOMAINS = [
    "sensor", "binary_sensor", "input_select", "weather", "sun", "zone",
    "person", "calendar", "persistent_notification", "alarm_control_panel",
    "device_tracker", "image_processing", "camera",
    "lock"
]
TOGGLE_DOMAINS = [
    "light", "switch", "fan", "input_boolean", "script", 
    "media_player", 
    "climate",      
    "cover",        
    "siren",        
    "humidifier"    
]
# Note: "input_button" and "scene" are handled specially for default actions.
#       "automation" has no default action and is handled in get_intent.

# Domains to prioritize for querying when a short, ambiguous command matches multiple entities.
# This list is used in the __main__ block for ambiguity resolution.
PREFERRED_QUERY_DOMAINS_FOR_SHORT_AMBIGUOUS_COMMANDS = ["input_select", "sensor"]

# Scoring and matching thresholds for find_entities
SHORT_CMD_WORD_THRESHOLD = 1 # Max words in a device_name to be considered "short" for ambiguity handling (used by find_entities and __main__).
AMBIGUOUS_DOMAIN_BONUS = 30  # Score bonus for preferred domains in ambiguous short commands (used by find_entities).
AMBIGUOUS_MATCH_THRESHOLD = 70 # Minimum score for an entity to be considered a candidate in ambiguous short commands (used by find_entities).
BASE_MATCH_THRESHOLD = 50    # Default minimum score for an entity to be considered a match (used by find_entities).
COMPETITIVE_SCORE_RATIO = 0.85 # Used in __main__ ambiguity resolution: a preferred domain entity is chosen if its score
                               # is at least this ratio of the top overall score.

# Define the debug state file path using absolute path to script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG = False  # Default state
DEBUG_FILE = os.path.join(SCRIPT_DIR, '.debug_state')

def debug_print(*args, **kwargs):
    """Print debug messages only if DEBUG is True"""
    if DEBUG:
        print("Debug -", *args, **kwargs)

def toggle_debug(command=None):
    """Toggle or set debug state"""
    global DEBUG
    
    if command == "on":
        DEBUG = True
    elif command == "off":
        DEBUG = False
    else:  # Toggle if no specific command
        DEBUG = not DEBUG
    
    with open(DEBUG_FILE, 'w') as f:
        f.write(str(DEBUG))
    
    if DEBUG: 
        print(f"Debug ON")
    return True
    
def load_debug_state():
    """Load debug state from file"""
    global DEBUG
    try:
        with open(DEBUG_FILE, 'r') as f:
            DEBUG = f.read().strip().lower() == 'true'
    except FileNotFoundError:
        pass 

def find_entities(user_input: str) -> list[tuple[float, str]] | None:
    start_time = time.time()
    global _ENTITIES_CACHE
    
    try:
        colors = ["red", "green", "blue", "yellow", "orange", "purple", "pink", "white"]
        if user_input.lower() in colors:
            debug_print(f"Using default color lights")
            # Assuming DEFAULT_ENTITIES['color_lights'] is a list of entity_ids
            # We need to return them with a nominal high score if this path is taken.
            return [(100.0, eid) for eid in DEFAULT_ENTITIES['color_lights']] if DEFAULT_ENTITIES.get('color_lights') else None
            
        user_input_lower = user_input.lower()
        
        debug_print(f"Automations will be included in search if names match.")
        
        is_temp_command = bool(re.search(r'(\d+)', user_input_lower) and 
                             any(word in user_input_lower for word in [
                                 'heat', 'heater', 'thermostat', 
                                 'ac', 'air conditioner', 'air con'
                             ]))
        
        if _ENTITIES_CACHE is None:
            cache_start = time.time()
            with open('entities.yaml', 'r') as file:
                _ENTITIES_CACHE = yaml.safe_load(file)
            debug_print(f"Cache load time: {(time.time() - cache_start)*1000:.1f}ms")
        
        device_names = re.split(r' and |, ', user_input.lower())
        found_entities_with_scores = []

        is_short_ambiguous_input_context = (
            len(device_names) == 1 and 
            len(device_names[0].split()) <= SHORT_CMD_WORD_THRESHOLD
        )
        if is_short_ambiguous_input_context:
            debug_print(f"Short ambiguous input context detected for: '{user_input}'")

        for device_name_part in device_names: 
            device_name_part = device_name_part.strip()
            if not device_name_part: 
                continue

            potential_matches_for_part = []
            
            is_light_command = any(word in device_name_part for word in ['%', 'bright', 'dim', 'color', 'red', 'blue', 'green', 'yellow', 'white'])
            is_volume_command = any(word in device_name_part for word in ['volume', 'vol'])
            is_media_command = any(word in device_name_part for word in ['play', 'pause', 'next', 'previous', 'prev', 'stop']) or is_volume_command
            is_fan_command = "fan" in device_name_part and any(speed in device_name_part for speed in FAN_SPEEDS.keys())

            for name, data in _ENTITIES_CACHE.items():
                entity_id = data['entity_id']
                entity_domain = entity_id.split('.')[0]
                name_lower = name.lower()
                
                if is_temp_command and not entity_id.startswith('climate.'):
                    continue
                
                score_set    = fuzz.token_set_ratio(device_name_part, name_lower)
                score_sort   = fuzz.token_sort_ratio(device_name_part, name_lower)
                score_partial = fuzz.partial_ratio(device_name_part, name_lower)
                combined_score = (score_set + score_sort + score_partial) / 3

                if device_name_part in name_lower: 
                    combined_score += 10

                if is_short_ambiguous_input_context and entity_domain in PREFERRED_QUERY_DOMAINS_FOR_SHORT_AMBIGUOUS_COMMANDS:
                    combined_score += AMBIGUOUS_DOMAIN_BONUS
                    debug_print(f"Applied domain bonus for {entity_id} (domain: {entity_domain}). New score: {combined_score:.0f} (was {(combined_score - AMBIGUOUS_DOMAIN_BONUS):.0f})")

                if is_temp_command: 
                    if entity_domain == 'climate': combined_score += 200
                    else: combined_score = 0 
                elif is_media_command:
                    if entity_domain == 'media_player': combined_score += 100
                    else: combined_score -= 50
                elif is_fan_command:
                    if entity_domain == 'fan': combined_score += 100
                    else: combined_score -= 50
                elif is_light_command:
                    if entity_domain == 'light': combined_score += 60
                    elif entity_domain == 'group': combined_score -= 40 
                elif not any([is_light_command, is_media_command, is_fan_command, is_temp_command]):
                    if entity_domain in ['light', 'switch']: 
                        combined_score += 40

                if combined_score > 0: 
                    potential_matches_for_part.append((combined_score, entity_id))
            
            if not potential_matches_for_part:
                continue

            potential_matches_for_part.sort(key=lambda x: x[0], reverse=True)
            debug_print(f"Potential matches for '{device_name_part}': {potential_matches_for_part[:5]}") 

            if is_short_ambiguous_input_context:
                for score, entity_id in potential_matches_for_part:
                    if score >= AMBIGUOUS_MATCH_THRESHOLD:
                        if not any(e_id == entity_id for _, e_id in found_entities_with_scores):
                             found_entities_with_scores.append((score, entity_id))
                             debug_print(f"Adding candidate for short ambiguous input: {entity_id} (Score: {score:.0f})")
                    else:
                        break 
            else:
                if potential_matches_for_part: 
                    best_score_for_part, best_match_for_part = potential_matches_for_part[0]
                    if best_score_for_part > BASE_MATCH_THRESHOLD:
                        if not any(e_id == best_match_for_part for _, e_id in found_entities_with_scores):
                            found_entities_with_scores.append((best_score_for_part, best_match_for_part))
                            debug_print(f"Best match for part '{device_name_part}': {best_match_for_part} (Score: {best_score_for_part:.0f})")
        
        found_entities_with_scores.sort(key=lambda x: x[0], reverse=True)
        
        debug_print(f"Entity finding time: {(time.time() - start_time)*1000:.1f}ms. Found: {found_entities_with_scores}")
        return found_entities_with_scores if found_entities_with_scores else None
    except FileNotFoundError:
        print("Debug - entities.yaml file not found!")
        return None

def get_intent(command: str, primary_entity_domain: str | None = None) -> str | tuple | None:
    command = command.lower().strip()

    if any(keyword in command for keyword in ["status", "state", "query"]):
        return "query_state"

    if "trigger" in command.split(): 
        return "trigger_entity"

    if "fan" in command:
        for speed, percentage in FAN_SPEEDS.items():
            if speed in command:
                return ("fan_speed", percentage)

    colors = ["red", "green", "blue", "yellow", "orange", "purple", "pink", "white"]
    for color_name in colors: 
        if color_name in command:
            return ("color", color_name)

    number_match = re.search(r'(\d+)', command)
    if number_match:
        number = float(number_match.group(1))
        return ("number", number)

    volume_words = ["volume", "vol"]
    if any(word in command for word in volume_words):
        if "up" in command or "increase" in command or "raise" in command or "higher" in command:
            return "volume_up"
        elif "down" in command or "decrease" in command or "lower" in command:
            return "volume_down"
        elif volume_match := re.search(r'volume (\d+)', command): 
            return ("volume_set", float(volume_match.group(1)) / 100)

    if "play" in command: 
        return "media_play"
    for cmd_word, service_name in MEDIA_COMMANDS.items():
        if cmd_word in command:
            if cmd_word not in ["on", "off", "volume up", "volume down", "status"]: 
                return service_name 

    for phrase, intent_val in BRIGHTNESS_PHRASES.items():
        if phrase in command:
            return intent_val 

    if "on" in command:
        return "turn_on"

    if "off" in command:
        return "turn_off"
            
    if command: 
        if primary_entity_domain:
            debug_print(f"Determining default intent for domain: {primary_entity_domain}")
            if primary_entity_domain == "automation":
                debug_print(f"Automation domain '{primary_entity_domain}' has no default action.")
                return None 
            elif primary_entity_domain == "input_button":
                return "press_button"
            elif primary_entity_domain == "scene":
                return "activate_scene"
            
            if primary_entity_domain in QUERY_DOMAINS: 
                return "query_state"
            elif primary_entity_domain in TOGGLE_DOMAINS:
                return "toggle"
            else:
                debug_print(f"Domain '{primary_entity_domain}' not in special, QUERY_DOMAINS or TOGGLE_DOMAINS, defaulting to query_state.")
                return "query_state"
        else:
            debug_print("No primary entity domain provided, defaulting to query_state for general command.")
            return "query_state" 

    debug_print("Command exhausted all specific checks, falling back to 'toggle'.")
    return "toggle"

def get_device_state(entity_id):
    """Get the current state of a device.
    Returns the state string in lowercase on success, None on failure."""
    try:
        response = requests.get(
            f"{HA_URL}/api/states/{entity_id}",
            headers=HEADERS,
            timeout=5 
        )
        response.raise_for_status() 

        try:
            state_data = response.json()
            if 'state' in state_data:
                debug_print(f"State for {entity_id}: {state_data['state']}")
                return state_data['state'].lower() 
            else:
                debug_print(f"Error: 'state' key not found in response for {entity_id}. Response: {state_data}")
                return None 
        except requests.exceptions.JSONDecodeError:
            debug_print(f"Error: Could not decode JSON response for {entity_id}. Response text: {response.text}")
            return None 

    except requests.exceptions.HTTPError as e:
        debug_print(f"HTTP error occurred for {entity_id}: {e}")
        return None 
    except requests.exceptions.RequestException as e:
        debug_print(f"Request exception occurred for {entity_id}: {e}")
        return None 
    except Exception as e:
        debug_print(f"An unexpected error occurred in get_device_state for {entity_id}: {e}")
        return None 

def get_group_entities(group_entity_id: str) -> list[str]:
    """Get all entities that belong to a group"""
    response = requests.get(
        f"{HA_URL}/api/states/{group_entity_id}",
        headers=HEADERS
    )
    if response.status_code == 200:
        state_data = response.json()
        return state_data.get('attributes', {}).get('entity_id', [])
    return []

def execute_command(entity_id: str, intent: str | tuple) -> bool:
    start_time = time.time()
    transition = 0 

    global _ENTITIES_CACHE 
    if _ENTITIES_CACHE is None: 
        try:
            with open('entities.yaml', 'r') as file:
                _ENTITIES_CACHE = yaml.safe_load(file)
            debug_print("Cache loaded in execute_command")
        except FileNotFoundError:
            debug_print("entities.yaml not found in execute_command, friendly names might not be available.")
            _ENTITIES_CACHE = {} 

    if intent == "status": 
        get_device_state(entity_id) 
        return True
    elif intent == "query_state":
        friendly_name = entity_id 
        if _ENTITIES_CACHE: 
            for name, data_val in _ENTITIES_CACHE.items(): 
                if data_val.get('entity_id') == entity_id:
                    friendly_name = name
                    break
        
        state_value_or_status = get_device_state(entity_id)
        
        if isinstance(state_value_or_status, str):
            if state_value_or_status == "Failed to get status": 
                print(f"Error: Could not retrieve state for '{friendly_name}'. API returned: {state_value_or_status}")
            else:
                print(f"{friendly_name.title()}: {state_value_or_status.capitalize()}")
        elif state_value_or_status is True: 
            pass 
        else: 
            print(f"Error: Could not retrieve state for '{friendly_name}'.")
            
        return True 

    domain = entity_id.split('.')[0]
    data = { "entity_id": entity_id }
    service = None 

    if isinstance(intent, tuple) and intent[0] == "number":
        number = intent[1]
        if domain == "climate":
            data.update({"temperature": number, "hvac_mode": "heat" if "heat" in entity_id else "cool"})
            service = "set_temperature"
        elif domain == "media_player":
            data["volume_level"] = number / 100 if number > 1 else number
            service = "volume_set"
        elif domain == "light":
            data.update({"brightness": int((number / 100) * 255), "transition": transition})
            service = "turn_on"
        else: return False
    elif isinstance(intent, tuple) and intent[0] == "temperature": 
        if domain != "climate": return False
        data.update({"temperature": intent[1], "hvac_mode": intent[2] if len(intent) > 2 else HVAC_MODE})
        service = "set_temperature"
    elif isinstance(intent, tuple) and intent[0] == "fan_speed": 
         if domain != "fan": return False
         data["percentage"] = intent[1] 
         service = "set_percentage"
    elif isinstance(intent, str) and intent in MEDIA_COMMANDS and MEDIA_COMMANDS[intent] not in ["turn_on", "turn_off", "status"]: 
        if domain != "media_player": return False
        service = MEDIA_COMMANDS[intent]
    elif isinstance(intent, str) and intent in BRIGHTNESS_PHRASES: 
        if domain != "light": return True 
        data["brightness_step_pct"] = 15 if BRIGHTNESS_PHRASES[intent] == "brightness_up" else -15
        service = "turn_on"
    elif isinstance(intent, tuple) and intent[0] == "color":
        if domain != "light": return True 
        data.update({"color_name": intent[1], "transition": transition})
        service = "turn_on"
    elif intent == "press_button":
        if domain != "input_button": return False
        service = "press"
    elif intent == "activate_scene":
        if domain != "scene": return False
        service = "turn_on" 
    elif intent == "trigger_entity":
        if domain == "automation": service = "trigger"
        else:
            debug_print(f"Error: 'trigger_entity' intent used for non-triggerable domain '{domain}' with entity '{entity_id}'.")
            return False
    else: 
        if domain == "lock":
            if intent == "turn_on": service = "lock"
            elif intent == "turn_off": service = "unlock"
            else: service = intent 
        elif domain == "light": 
            data["transition"] = transition
            service = "toggle" if intent == "toggle" else intent
        else: 
            service = "toggle" if intent == "toggle" else intent

    if service is None: 
        debug_print(f"Error: Service could not be determined for intent '{intent}' and domain '{domain}'.")
        return False

    if domain != "light" or data.get('transition') is None:
        data.pop('transition', None)

    url = f"{HA_URL}/api/services/{domain}/{service}"
    debug_print(f"Making request to: {url}")
    debug_print(f"With data: {data}")

    try:
        response = requests.post(url, headers=HEADERS, json=data, timeout=1, verify=False)
        debug_print(f"Command execution time: {(time.time() - start_time)*1000:.1f}ms")
        return response.status_code == 200
    except Exception as e:
        # print(f"Error: {e}")
        return False

if __name__ == "__main__":
    # --- Main script execution flow ---
    start_time = time.time()
    load_debug_state() 
    
    if len(sys.argv) < 2:
        sys.exit(1)
    
    command = " ".join(sys.argv[1:]).lower().strip()
    
    if command == "reload":
        try:
            import reload_entities 
            reload_entities.main()
            print("Entities reloaded successfully")
            sys.exit(0) 
        except ImportError:
            print("Error: reload_entities.py not found. Cannot reload entities.")
            sys.exit(1)
        except Exception as e:
            print(f"Failed to reload entities: {e}")
            sys.exit(1)
    
    if command == "debug" or command.startswith("debug "):
        parts = command.split()
        if len(parts) > 1:
            toggle_debug(parts[1])  
        else:
            toggle_debug()  
        sys.exit(0) 
    
    found_entities_with_scores = find_entities(command)

    if not found_entities_with_scores:
        print("No matching devices found") 
        sys.exit(1) 
    
    entity_ids_for_processing = []
    chosen_entity_id_for_intent = found_entities_with_scores[0][1] # Default to top match for primary domain

    command_words = command.split() 
    is_short_command = len(command_words) <= SHORT_CMD_WORD_THRESHOLD

    if is_short_command and len(found_entities_with_scores) > 1:
        debug_print(f"Short command '{command}' with multiple candidates: {found_entities_with_scores}")
        top_score, top_entity_id = found_entities_with_scores[0]
        chosen_entity_id_for_intent = top_entity_id # Default to top entity
        
        preferred_candidate_id = None
        highest_preferred_score = 0

        for r_score, r_eid in found_entities_with_scores:
            r_domain = r_eid.split('.')[0]
            if r_domain in PREFERRED_QUERY_DOMAINS_FOR_SHORT_AMBIGUOUS_COMMANDS:
                if r_score >= top_score * COMPETITIVE_SCORE_RATIO:
                    if r_score > highest_preferred_score:
                        highest_preferred_score = r_score
                        preferred_candidate_id = r_eid
        
        if preferred_candidate_id:
            debug_print(f"Prioritizing preferred domain entity: {preferred_candidate_id} (Score: {highest_preferred_score:.0f}) over initial top score {top_entity_id} (Score: {top_score:.0f})")
            entity_ids_for_processing = [preferred_candidate_id]
            chosen_entity_id_for_intent = preferred_candidate_id # Update for primary_domain determination
        else:
            debug_print(f"No competitive preferred domain entity found. Using original top score entity: {top_entity_id}")
            entity_ids_for_processing = [top_entity_id]
    else:
        entity_ids_for_processing = [item[1] for item in found_entities_with_scores]
        if len(found_entities_with_scores) > 1: # Not short ambiguous, but multiple entities (e.g. "lights and fan")
             debug_print(f"Processing multiple entities for command '{command}': {entity_ids_for_processing}")
        # If only one entity found, chosen_entity_id_for_intent is already correct.
        # If multiple entities from a non-short command, chosen_entity_id_for_intent (for primary_domain) uses the first one.

    primary_domain = None 
    if entity_ids_for_processing: # Should always have at least one item if we reached here
        primary_domain = chosen_entity_id_for_intent.split('.')[0]
        debug_print(f"Primary entity domain for intent determination: {primary_domain} (from {chosen_entity_id_for_intent})")
    
    intent = get_intent(command, primary_entity_domain=primary_domain) 
    success = True 
    
    if intent is None:
        # This logic assumes entity_ids_for_processing has at least one element if intent is None
        # which should be true since primary_domain was derived from chosen_entity_id_for_intent
        entity_display_name = entity_ids_for_processing[0] if entity_ids_for_processing else "unknown entity"
        if primary_domain == "automation": 
             debug_print(f"No default action for automation '{entity_display_name}'. Command not executed.")
        else: 
             debug_print(f"Intent resolved to None for '{entity_display_name}'. Command not executed.")
    elif entity_ids_for_processing: 
        for entity_id in entity_ids_for_processing:
            if not execute_command(entity_id, intent):
                success = False
                # print(f"Failed for {entity_id}") 
    
    if not success:
        print("") 
    
    if DEBUG:
        debug_print(f"Total execution time: {(time.time() - start_time)*1000:.1f}ms")