# Stellaris x Archipelago

An [Archipelago](https://archipelago.gg/) multiworld randomizer integration for Stellaris.

Trade discoveries with players in other games. Your milestones and tech research send items to Hollow Knight players, Terraria players, and others - while their progress unlocks technologies and resources for your empire.

## How It Works

**Milestones** fire automatically as you play Stellaris - surveying systems, researching vanilla techs, colonizing planets, building fleet power. Each milestone sends an item to another player in the multiworld.

**AP Techs** replace vanilla techs that were "sent to other worlds." They appear in your research pool with the Archipelago logo, named after the item they contain: *"Mothwing Cloak for Alice"*. They sit at the same position in the tech tree as the vanilla tech they replaced.

**Receiving items** from other players grants you progressive unlocks (ship classes, weapons, defenses), resource caches, or traps - delivered via in-game event popups.

## Goals

Pick how you want to "win" the seed. The bridge reads your choice from `slot_data` and pushes it to the mod as a country flag at connection time, and the mod fires `AP_GOAL_COMPLETE` when the matching condition is met:

| Option | Completion Condition | Notes |
|---|---|---|
| `victory` (default) | Survive past in-game year 2400 | Always available |
| `crisis_averted` | Defeat the endgame crisis | Requires Progressive Ship Class ×4, Progressive Weapons ×4, Progressive Defenses ×3 |
| `ascension` | Complete any ascension path (Bio / Synth / Psi) | Requires Utopia DLC |
| `galactic_emperor` | Form the Galactic Imperium | Requires Federations DLC |
| `all_checks` | Send every location in the pool | Detected client-side by the bridge |

## Options

The apworld exposes the following player options (all configurable per-slot in your YAML):

**Gameplay**
- `goal` — Win condition (see Goals above)
- `galaxy_size` — Small / Medium / Large / Huge (affects pacing only — milestone thresholds aren't auto-scaled)

**Location categories** (toggle which checks appear)
- `include_exploration` — Surveys, anomalies, contacts, the L-Cluster
- `include_diplomacy` — Pacts, federations, the Galactic Community
- `include_warfare` — Wars, fleet power, leviathans
- `include_crisis` — Endgame crisis events, Become the Crisis

**Items**
- `traps_enabled` — Whether trap items appear in the pool
- `trap_percentage` — Share of filler slots filled with traps (0–100)
- `energy_link_enabled` — Shared energy pool with other connected games
- `energy_link_rate` — Stellaris-EC ↔ EnergyLink-unit conversion rate

**DLC** (each toggles whether DLC-specific content appears)
- `dlc_utopia` (on by default — base game content as of 4.0)
- `dlc_federations`, `dlc_nemesis`, `dlc_leviathans`
- `dlc_apocalypse`, `dlc_megacorp`, `dlc_overlord`

## Quick Start

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

## Dashboard

If you'd rather not run `setup.py` commands by hand, the project ships with a self-contained web dashboard:

```powershell
python dashboard.py
```

This opens a browser tab on `localhost:19472` with controls for:

- **Setup** — install/uninstall the mod, build and install the DLL, scan vanilla tech files
- **Status** — check what's installed, inspect Stellaris error logs, test the pipe end-to-end
- **Run** — start and stop the bridge or the mock AP server, tail their logs live in the browser

It uses Python's stdlib `http.server` so there's no extra dependency. Useful when you're iterating on a session and don't want to keep two or three terminals open.

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

**Inbound (server → game):** AP server sends items via WebSocket. The bridge forwards each item as a console command over a named pipe to the DLL. The DLL has two delivery modes:

- **Phase 2 (primary) — direct engine call.** At injection time, the DLL AOB-scans `stellaris.exe` to locate three internal engine functions: `StringConstruct` (builds the engine's internal string object), `ExecuteCommand` (parses and runs a console command), and `StringDestruct`. It then invokes them in sequence — the same path the game's own TweakerGUI debug panel uses. No console window flicker, no input contention with the player, no file I/O on the hot path.
- **Phase 1 (fallback) — SendInput.** If pattern scanning fails (e.g. after a Stellaris update shifts the byte signatures), the DLL automatically falls back to writing commands into `ap_bridge_commands.txt` and triggering Stellaris's built-in `run` console command via `SendInput`. Slower and more visible, but resilient to engine updates.

**Outbound (game → server):** Mod writes `AP_CHECK|id|name` lines to game.log via Paradox-script `log` effects. The bridge tails the log and forwards each as a `LocationChecks` packet to the AP server. Goal completion fires an `AP_GOAL_COMPLETE` line that becomes a `StatusUpdate(30)` packet.

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
