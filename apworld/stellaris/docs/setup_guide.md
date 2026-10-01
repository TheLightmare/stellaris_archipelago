# Stellaris Archipelago Setup Guide

## Required Software

- **Stellaris** (Steam, 4.x) on **Windows** — the bridge DLL and named pipe are Windows-only
- **Archipelago** 0.5.0 or later — [download here](https://github.com/ArchipelagoMW/Archipelago/releases)
- **Python 3.10+** for the bridge client
- The **Stellaris Archipelago player package** (`stellaris-archipelago-<version>.zip`) from the project's releases page

## Step 1: Install the mod and bridge

Unzip the player package anywhere, open a terminal in that folder and run:

```powershell
python setup.py install
```

This installs the Python dependencies, copies the mod into
`Documents\Paradox Interactive\Stellaris\mod\`, and places the bridge
`version.dll` next to `stellaris.exe`. No compiler is needed.

`python setup.py status` shows what is installed. Prefer clicking? `python dashboard.py` opens a local web UI with the same actions.

Then:

1. In Steam: right-click Stellaris → Properties → Launch Options: `-logall` (required — without it the game suppresses repeated log lines and the bridge misses checks).
2. In the Paradox launcher: enable the **Archipelago Multiworld** mod.

## Step 2: Build your YAML

Run `python dashboard.py`, open the **Tech Config** tab to choose which vanilla technologies to randomize (optional), then the **YAML Wizard** tab to set your goal, DLC and other options and download the `.yaml`. Send it, together with `stellaris.apworld`, to whoever hosts the multiworld.

## Step 3: Install the apworld (host)

Place `stellaris.apworld` in the Archipelago installation's `worlds/` directory (or `custom_worlds/` on newer versions), generate with the players' YAMLs and host the room as usual.

## Step 4: Start the bridge

```powershell
python setup.py play --server archipelago.gg:12345 --slot YourSlotName
```

(add `--password` if the room has one). On connect the bridge scouts the multiworld and generates the AP research techs for your seed into the mod. Wait for the line **DYNAMIC TECHS GENERATED**.

## Step 5: Play

1. Start (or restart) Stellaris with the mod enabled and begin a **new non-ironman game**, or load an existing save.
2. Accept the **Archipelago Connection** popup (it appears at game start, or at the next monthly tick for an existing save).
3. Play normally. Milestones are detected automatically; AP techs appear in your research pool with the Archipelago icon, named after the item they send.

Items arrive once the mod has reported in to the bridge for the current game process (the connection popup, or the next monthly tick), so load your save and unpause for a moment if the bridge log says it is waiting. Keep the bridge running while you play; if it was down while you completed something, the mod re-logs sent checks every month and nothing is lost.

## In-Game Features

- **Milestone notifications** — an event popup confirms every check sent.
- **Item receipts** — an event popup shows what you got; progressive items immediately unlock their next tier.
- **EnergyLink** — if enabled in your YAML, the EnergyLink edicts deposit or withdraw energy credits from the shared multiworld pool.

## Troubleshooting

- **No connection popup:** the mod is not enabled in the launcher, or the game is ironman.
- **Bridge says "waiting for Stellaris to report in":** load a save, accept the popup, unpause until the next month.
- **Bridge says "PIPE unavailable":** `version.dll` is missing from the game folder (`python setup.py status`), or the game runs with different privileges than the bridge. The DLL writes `archipelago_dll.log` next to `stellaris.exe`.
- **Wrong Stellaris folder detected:** set `STELLARIS_USER_DIR` / `STELLARIS_GAME_DIR` (see the project README).
- **Mod errors:** `python setup.py check-errors` lists AP-related lines from Stellaris' `error.log`.
