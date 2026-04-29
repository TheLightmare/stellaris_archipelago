# Stellaris x Archipelago

An [Archipelago](https://archipelago.gg/) multiworld randomizer integration for Stellaris.

Trade discoveries with players in other games. Your milestones and tech research send items to Hollow Knight players, Terraria players, and others - while their progress unlocks technologies and resources for your empire.

## How It Works

**Milestones** fire automatically as you play Stellaris - surveying systems, researching vanilla techs, colonizing planets, building fleet power. Each milestone sends an item to another player in the multiworld.

**AP Techs** replace vanilla techs that were "sent to other worlds." They appear in your research pool with the Archipelago logo, named after the item they contain: *"Mothwing Cloak for Alice"*. They sit at the same position in the tech tree as the vanilla tech they replaced.

**Receiving items** from other players grants you progressive unlocks (ship classes, weapons, defenses), resource caches, or traps - delivered via in-game event popups.

## Quick Start

The mod has a graphical UI to set up everything, but you can do it manually as well :

```powershell
# 1. Install Python dependencies
pip install websocket-client

# 2. Run the Dashboard
python dashboard.py
```

Manual set up:

```powershell
# 1. Install Python dependencies
pip install websocket-client

# 2. Install the mod
python setup.py install

# 3. Build and install the DLL (requires CMake + Visual Studio)
python setup.py build-dll
python setup.py install-dll

# 4. Check everything is in place
python setup.py status
```

Then launch Stellaris with `-logall` in Steam launch options, enable the mod, and start a new non-ironman game.

## Testing Locally

```powershell
# Set up mock session (installs mod + generates test AP techs)
python setup.py mock

# In one terminal: mock AP server
cd client && python mock_ap_server.py

# In another terminal: bridge
cd client && python ap_bridge.py --server localhost:38281 --slot Stellaris

# In the mock server, send items:
#   ship / weapons / cache / trap / status
```

## Playing for Real

```powershell
python setup.py play --server archipelago.gg:12345 --slot YourName
```

The bridge auto-generates AP techs from the multiworld seed, then tells you to restart Stellaris. After restarting, the AP techs appear in your research pool and vanilla techs that were sent to other worlds are hidden.

## Project Structure

```
README.md / LICENSE / CONTRIBUTING.md
setup.py                            One script to install, build, test, run
dashboard.py                        Optional local web UI for managing the bridge

mod-install/                        Stellaris mod (copy to Paradox/Stellaris/mod/)
  archipelago_multiworld.mod        Launcher descriptor
  archipelago_multiworld/           Mod content
    common/technology/              Vanilla tech overrides (FIOS blocking)
    common/scripted_effects/        Item grants, check detection, log senders
    common/scripted_triggers/       Item-tier checks
    common/edicts/                  EnergyLink deposit/withdraw
    common/static_modifiers/        Filler-item modifier definitions
    common/opinion_modifiers/       Trap diplomatic modifiers
    common/on_actions/              Game-event hooks
    events/                         Connection, notification, hook events
    gfx/                            Archipelago tech icon
    localisation/                   All UI text

client/                             Python AP client
  ap_bridge.py                      Main bridge (WebSocket + pipe + log tailing)
  pipe_client.py                    Named pipe client for DLL communication
  slot_generator.py                 Generates AP tech cards from multiworld seed
  tech_scanner.py                   Vanilla tech file scanner
  mock_ap_server.py                 Fake AP server for local testing

dll/                                C++ DLL (version.dll proxy)
  src/                              Proxy, bridge, console injection, logging
  CMakeLists.txt                    Build with: cmake -G "Visual Studio 17 2022" -A x64
  ARCHITECTURE.md                   How the DLL fits together
  HOOKING_RESEARCH.md               Design rationale (ref to similar engine mods)

apworld/stellaris/                  Archipelago world definition
  __init__.py                       World class (generation, rules, items, regions)
  archipelago.json                  AP world metadata
  items.py                          38 items (progressive, unique, filler, traps)
  locations.py                      120 locations (milestones + tech-type)
  regions.py                        Menu - Early - Mid - Late - Endgame
  rules.py                          Progression logic
  options.py                        Player options (goal, DLC, galaxy size)
  docs/                             Player-facing setup guide and game info
  test/                             Unit tests (data integrity, fill, options)
```

## Architecture

```
Stellaris Game <-> DLL (version.dll proxy) <-> Named Pipe <-> ap_bridge.py <-> AP Server
     |                                                              |
     +-- game.log (AP_CHECK lines) -------------------------------->+
```

**Inbound (server -> game):** AP server sends items via WebSocket. Bridge writes console commands to a file. DLL types `run ap_bridge_commands.txt` into the Stellaris console via SendInput.

**Outbound (game -> server):** Mod writes `AP_CHECK|id|name` to game.log. Bridge tails the log and sends LocationChecks to the AP server.

## 120 Locations

| Category | Total | Milestones (auto-detected) | AP Techs (researchable) |
|---|---:|---:|---:|
| Exploration | 11 | 6 | 5 |
| Advanced Tech | 7 | 4 | 3 |
| Expansion | 13 | 11 | 2 |
| Diplomacy | 11 | 2 | 9 |
| Warfare | 9 | 5 | 4 |
| Traditions | 9 | 6 | 3 |
| Crisis | 6 | 0 | 6 |
| Victory | 1 | 1 | 0 |
| Vanilla Tech Research | 40 | 40 | 0 |
| Bonus Gameplay | 13 | 13 | 0 |
| **Total** | **120** | **88** | **32** |

**Milestones** trigger automatically as you play (e.g. surveying systems, hitting fleet-power thresholds, completing tradition trees).

**AP Techs** appear in the research pool with the Archipelago icon and named after the item they send to another player. Researching one sends the check.

## EnergyLink

Shared energy pool across all connected games. Exchange rate: **1 Stellaris EC = 1 Factorio Joule** (1:1).

Use the EnergyLink edicts in-game to deposit or withdraw energy credits. The bridge handles the AP protocol (`Set`/`Get` data storage).

## Tests

The apworld ships with a unit test suite that runs under Archipelago's standard test harness. After dropping `apworld/stellaris/` into your `Archipelago/worlds/` checkout:

```sh
# from your Archipelago repo root
python -m unittest discover -s worlds/stellaris/test
```

The suite checks ID stability, item/location counts, region connectivity, fill solvability across all goal types, and option interactions.

## Requirements

- Stellaris (non-ironman, `-logall` launch option)
- Python 3.10+ with `websocket-client` (`pip install websocket-client`)
- Windows (for DLL + named pipe)
- Visual Studio 2022 / MSVC Build Tools (for DLL compilation)
- Archipelago server (for real multiworld sessions)
