![Dashboard Preview](https://i.imgur.com/mQ6sywi.png)
A powerful command-line interface to control your Home Assistant entities using natural language.

## Description

This script allows you to quickly control your Home Assistant devices without needing to open the UI. It uses fuzzy string matching to find the entities you mean and understands a variety of commands for different device types.

## Features

-   **Natural Language Processing:** Understands commands like "turn on the lights" or "set thermostat to 72".
-   **Fuzzy Entity Matching:** Finds the correct device even if you don't type the exact name. "ktl" or "trn on ktt", both turn on the kettle.
-   **Wide Device Support:** Controls lights, switches, fans, climate (thermostats), media players, locks, and more.
-   **Multi-Entity Commands:** Control multiple devices at once, e.g., `python script.py turn on living room light and fan`.
-   **Entity Cache:** Fetches all your entities and caches them locally for fast performance.
-   **Debug Mode:** A debug mode for troubleshooting and seeing command details.
-   **Alfred Workflow:** A quick access text input using Alfred for Mac OS.

## Alfred Workflow
![Dashboard Preview](https://i.imgur.com/2Sap7Qh.png)

## Requirements

-   Python 3
-   `requests`
-   `PyYAML`
-   `fuzzywuzzy`
-   `python-Levenshtein` (optional, for better performance)

You can install the required libraries using pip:
```bash
pip install -r requirements.txt
```

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <repo-directory>
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure the script:**
    -   Copy `config.example.py` to `config.py`.
        ```bash
        cp config.example.py config.py
        ```
    -   Edit `config.py` and add your Home Assistant URL and a Long-Lived Access Token.
        ```python
        # Home Assistant Configuration
        HA_URL = "http://your.home.assistant:8123"
        HA_TOKEN = "your_long_lived_access_token"

        # Default Entities
        DEFAULT_ENTITIES = {
            'lights': 'light.your_default_lights',
            'light': 'light.your_default_lights',
            'fan': 'fan.your_default_fan',
            'tv': 'media_player.your_default_tv'
        }
        ```

4.  **Fetch your entities:**
    Before the first use, you need to populate the entity list from your Home Assistant instance.
    ```bash
    python script.py reload
    ```
    This will create an `entities.yaml` file containing all your devices. You should run this command whenever you add or remove devices from Home Assistant.

## Usage

The script is run from the command line.

**Syntax:**
```bash
python script.py [command]
```

### Examples

**Toggling Devices:**
```bash
# Turn a light on/off
python script.py toggle living room lamp

# Turn on a switch
python script.py turn on coffee maker

# Turn off multiple devices
python script.py turn off office light and desk fan
```

**Lights:**
```bash
# Set brightness
python script.py living room light 50%

# Set color
python script.py set office light to blue
```

**Climate (Thermostats):**
```bash
# Set temperature
python script.py set thermostat to 72
python script.py set heater to 20 degrees
```

**Fans:**
```bash
# Set fan speed
python script.py set desk fan to high
python script.py fan low
```

**Media Players:**
```bash
# Control playback
python script.py play on living room tv
python script.py pause on kitchen speaker

# Control volume
python script.py volume up on tv
python script.py set tv volume to 25
```

**Querying State:**
```bash
# Get the status of a device
python script.py status of front door
python script.py query garage door
```

### Special Commands

**Reload Entities:**
```bash
python script.py reload
```

**Debug Mode:**
```bash
# Turn debug mode on/off/toggle
python script.py debug on
python script.py debug off
python script.py debug
```

## How it Works

The script takes your command and performs the following steps:
1.  **Finds Entities:** It searches the `entities.yaml` file to find the best matching entity for the device name in your command using fuzzy string matching.
2.  **Determines Intent:** It analyzes the command to understand the desired action (e.g., `turn_on`, `set_temperature`, `play_media`).
3.  **Executes Command:** It sends the appropriate API request to your Home Assistant instance to execute the command.
