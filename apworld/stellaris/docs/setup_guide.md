# Stellaris Archipelago Setup Guide

## Required Software

- **Stellaris** (Steam, version 3.12 or later)
- **Archipelago** (version 0.5.0 or later) — [download here](https://github.com/ArchipelagoMW/Archipelago/releases)
- **Python 3.10+** (for the bridge client)

## Step 1: Install the Stellaris Mod

1. Download the Stellaris Archipelago mod.
2. Copy the `mod/` folder contents to your Stellaris mod directory:
   - **Windows:** `Documents\Paradox Interactive\Stellaris\mod\archipelago\`
   - **Linux:** `~/.local/share/Paradox Interactive/Stellaris/mod/archipelago/`
   - **macOS:** `~/Documents/Paradox Interactive/Stellaris/mod/archipelago/`
3. Create a `archipelago.mod` file in the `mod/` parent directory pointing to the folder.
4. Enable the mod in the Stellaris launcher.

## Step 2: Install the Apworld

1. Download `stellaris.apworld` from the releases page.
2. Place it in your Archipelago installation's `worlds/` directory.

## Step 3: Generate a Multiworld

1. Create your YAML configuration file (see `sample.yaml` for options).
2. Use the Archipelago generator to create a multiworld with your YAML.
3. Host or connect to an Archipelago server.

## Step 4: Launch the Client

```bash
python client/stellaris_client.py --server localhost:38281 --slot YourName
```

The client will create the bridge directory automatically.

## Step 5: Start Stellaris

1. **Add `-logall` to Stellaris launch options in Steam.** (Right-click Stellaris → Properties → Launch Options → type `-logall`). This is required — without it, the game suppresses duplicate log messages and the bridge may miss checks.
2. Launch Stellaris with the Archipelago mod enabled.
3. Start a **new game** (non-ironman, any difficulty).
4. On game start, you'll see the "Archipelago Connection" event — click to connect.
5. Play normally! Milestones will be tracked automatically.

## In-Game Features

### Milestone Notifications
When you complete a milestone (e.g., "Survey 10 Systems"), you'll see an event popup confirming the check was sent.

### Item Receipts
When you receive an item from the multiworld, an event popup shows what you got. Progressive items (like ship class unlocks) immediately expand your capabilities.

### EnergyLink
If enabled, use the EnergyLink decisions in your empire decisions menu to deposit or withdraw energy credits from the shared multiworld pool.

## Troubleshooting

- **No events firing:** Make sure the mod is enabled and you clicked "Connect" on the first event.
- **Items not arriving:** Check that the Python client is running and connected to the server.
- **Bridge files not found:** Verify the bridge directory exists at `Documents/Paradox Interactive/Stellaris/archipelago/`.

## YAML Options Reference

See the design document for a full list of configurable options including goal selection, DLC toggles, trap settings, and EnergyLink configuration.
