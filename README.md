# Stellaris x Archipelago

An [Archipelago](https://archipelago.gg/) multiworld randomizer integration for Stellaris.

Trade discoveries with players in other games. Your milestones and tech research send items to Hollow Knight players, Terraria players, and others - while their progress unlocks technologies and resources for your empire.

## How It Works

**Milestones** fire automatically as you play Stellaris - surveying systems, researching vanilla techs, colonizing planets, building fleet power. Each milestone sends an item to another player in the multiworld.

**AP Techs** replace vanilla techs that were "sent to other worlds." They appear in your research pool with the Archipelago logo, named after the item they contain: *"Mothwing Cloak for Alice"*. They sit at the same position in the tech tree as the vanilla tech they replaced.

**Receiving items** from other players grants you progressive unlocks (ship classes, weapons, defenses), resource caches, or traps - delivered via in-game event popups.

## Goals

Pick how you want to "win" the seed. The bridge reads your choice from `slot_data` and pushes it to the mod as a country flag, and the mod fires `AP_GOAL_COMPLETE` when the matching condition is met. Whichever goal you pick, reaching it also sends the **Victory** location (it exists in every seed):

| Option | Completion Condition | Notes |
|---|---|---|
| `victory` (default) | Survive past in-game year 2400 | Always available |
| `crisis_averted` | Defeat the endgame crisis | Requires Progressive Ship Class ×4, Progressive Weapons ×4, Progressive Defenses ×3 |
| `ascension` | Complete any ascension path (Bio / Synth / Psi) | Requires Utopia DLC |
| `galactic_emperor` | Form the Galactic Imperium | Requires Federations DLC |
| `all_checks` | Send every other location in the pool | Detected client-side; the bridge then sends Victory itself |

## Tech Randomization

Beyond the fixed milestones, any vanilla technology from the catalog (598 techs) can be randomized via the `randomized_techs` YAML option (pick them in the dashboard's **Tech Config** tab). Each selected tech:

- is hidden from your research pool and replaced by an AP tech that sits at the same spot in the tree (same tier, area, prerequisites and cost);
- becomes a `Research <Tech>` location — researching the AP tech sends the check;
- becomes a `Tech: <Tech>` item somewhere in the multiworld — receiving it is the only way to get the vanilla tech's effects.

If a randomized tech is a prerequisite of another randomized tech, the generator's logic knows the `Tech:` item for the prerequisite must come first, so seeds are never left uncompletable.

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
- `energy_link_rate` — Energy credits per EnergyLink unit (default 100)
- `randomized_techs` — Vanilla techs to randomize (see Tech Randomization)

**DLC** (each toggles whether DLC-specific content appears)
- `dlc_utopia` (on by default — base game content as of 4.0)
- `dlc_federations`, `dlc_nemesis`, `dlc_leviathans`
- `dlc_apocalypse`, `dlc_megacorp`, `dlc_overlord`

## Quick Start (no terminal needed)

1. Install [Python 3](https://www.python.org/downloads/windows/) if you don't have it — tick **"Add python.exe to PATH"** in the installer.
2. Unzip the player package and double-click **`Stellaris Archipelago.bat`**. A dashboard opens in your browser.
3. On the **Setup** tab click **Set up everything**. It installs the Python packages, the mod, and the bridge DLL (prebuilt, no compiler needed), adds the `-logall` launch option in Steam, and enables the mod in your Paradox launcher playset. The two Steam/launcher steps need those programs closed; if one is open the checklist tells you, with the manual steps as a fallback.
4. **Tech Config** (optional) → **YAML Wizard** → download your YAML and send it to the host together with `stellaris.apworld`.
5. When the host's multiworld is up: **Bridge** tab → server, slot, password → **Start Bridge**. Wait for *DYNAMIC TECHS GENERATED*, click **Launch Stellaris**, press Play in the launcher, start a new non-ironman game (or load your save) and accept the Archipelago popup.

The dashboard remembers your connection settings, shows whether the bridge is connected and in-game, and keeps running the bridge while you play.

### Command line

Everything the dashboard does is also available from a terminal:

```powershell
python setup.py install       # deps, mod, DLL, Steam launch option, launcher playset
python setup.py status        # what's installed
python setup.py play --server archipelago.gg:12345 --slot YourName
```

To rebuild the DLL from source instead of using the prebuilt one (requires CMake +
Visual Studio 2022): `python setup.py build-dll && python setup.py install-dll`
— a fresh local build always takes priority over the prebuilt binary.

## Dashboard

`Stellaris Archipelago.bat` (or `python dashboard.py`) serves a local page on `localhost:19472` with:

- **Setup** — the checklist above with one-click fixes, plus uninstall and tech-override rebuilding
- **Bridge** — start/stop the bridge, launch Stellaris, live bridge log with plain-language status
- **Tech Config / YAML Wizard** — choose randomized techs and build the YAML for your host
- **Errors** — AP-related lines from Stellaris' error.log

It uses Python's stdlib `http.server`; the page itself loads React from a CDN, so it needs the same internet connection the bridge needs anyway.

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

The bridge auto-generates AP techs from the multiworld seed, then tells you to (re)start Stellaris. After restarting, the AP techs appear in your research pool and vanilla techs that were sent to other worlds are hidden.

**When do items arrive?** Console effects only work inside a loaded save, so the bridge waits until the mod *reports in* for the current game process — that happens when you accept the connection popup in a new game, and at every monthly tick after that. Once it does, the bridge first syncs the save's flags (goal, tech blocking, EnergyLink) and then delivers every queued item. If you see `waiting for Stellaris to report in` in the bridge log, load your save and unpause for a moment.

**What if the bridge wasn't running when I completed something?** Nothing is lost: every month the mod re-logs all checks the save has already sent, and the bridge picks up anything it hasn't forwarded yet.

## Project Structure

```
README.md / LICENSE / CONTRIBUTING.md
Stellaris Archipelago.bat           Double-click entry point (opens the dashboard)
setup.py                            One script to install, build, test, run
dashboard.py                        Local web UI: setup checklist, bridge, YAML

mod-install/                        Stellaris mod (copy to Paradox/Stellaris/mod/)
  archipelago_multiworld.mod        Launcher descriptor
  archipelago_multiworld/           Mod content
    common/technology/              Vanilla tech overrides (FIOS blocking)
    common/scripted_effects/        Item grants, check detection, log senders,
                                    monthly check resync (ap_resync.txt, generated)
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
  tech_catalog.py                   Mirror of the apworld tech catalog (IDs)
  game_setup.py                     Steam launch option + launcher playset automation
  mock_ap_server.py                 Fake AP server for local testing

scripts/
  check_coherence.py                Cross-checks IDs/names across all layers;
                                    --write regenerates the mod's ap_resync.txt
  make_release.py                   Builds release zips

dll/                                C++ DLL (version.dll proxy)
  src/                              Proxy, bridge, console injection, logging
  CMakeLists.txt                    Build with: cmake -G "Visual Studio 17 2022" -A x64
  ARCHITECTURE.md                   How the DLL fits together

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

**Outbound (game → server):** Mod writes `AP_CHECK|id|name` lines to game.log via Paradox-script `log` effects. The bridge tails the log and forwards each as a `LocationChecks` packet to the AP server. Goal completion fires an `AP_GOAL_COMPLETE` line that becomes a `StatusUpdate(30)` packet. The monthly `AP_HEARTBEAT` line is also how the bridge knows a save is loaded (and therefore that effects can be delivered); when game.log is recreated by a game restart the bridge waits for the next heartbeat and re-syncs the save's flags before delivering anything.

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

Shared energy pool across all connected games. The exchange rate is the `energy_link_rate` YAML option: energy credits per EnergyLink unit (default 100, so a 500 EC deposit adds 5 units and a 2,000 EC withdrawal asks for 20).

Use the EnergyLink edicts in-game to deposit or withdraw energy credits; they only appear when the slot has EnergyLink enabled. The bridge handles the AP protocol (`Set`/`Get` data storage). Withdrawals are clamped to what the pool actually holds.

## Tests

The apworld ships with a unit test suite that runs under Archipelago's standard test harness. After dropping `apworld/stellaris/` into your `Archipelago/worlds/` checkout:

```sh
# from your Archipelago repo root
python -m unittest discover -s worlds/stellaris/test
```

The suite checks ID stability, item/location counts, region connectivity, fill solvability across all goal types (including every catalog tech randomized at once), tech prerequisite logic, and option interactions.

The layers outside the apworld (client, mod) are cross-checked by a standalone script that needs no Archipelago checkout:

```sh
python setup.py check          # or: python scripts/check_coherence.py
```

## Requirements

- Stellaris (non-ironman, `-logall` launch option)
- Python 3.10+ (`setup.py install` fetches the pip dependencies automatically)
- Windows (for DLL + named pipe)
- Archipelago server (for real multiworld sessions)
- *Optional:* Visual Studio 2022 / MSVC Build Tools — only needed to
  rebuild the DLL from source; a prebuilt binary is included

## Troubleshooting

**Wrong Stellaris folder detected?** All tools share one detector
(`client/ap_paths.py`) that prefers the user directory with the most
recent `game.log`. If your setup is unusual (OneDrive redirection, a
custom Steam library), override it explicitly:

```powershell
$env:STELLARIS_USER_DIR = "C:\path\to\Documents\Paradox Interactive\Stellaris"
$env:STELLARIS_GAME_DIR = "D:\SteamLibrary\steamapps\common\Stellaris"
```

**Enabled the mod on an existing campaign?** That works — the
connection-setup popup appears at the next monthly tick instead of
game start.

**Bridge says "waiting for Stellaris to report in"?** Items are only
delivered while a save is loaded. Load your game, make sure you
accepted the Archipelago connection popup, and unpause — the mod
checks in at the next monthly tick. If it never does, the mod is
probably not enabled in the launcher, or `-logall` is missing.

**Bridge says "PIPE unavailable"?** The game is in session but the
DLL isn't answering: check that `version.dll` sits next to
`stellaris.exe` (`python setup.py status`) and look at
`archipelago_dll.log` in the game folder.
