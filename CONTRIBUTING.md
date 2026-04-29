# Contributing

Thanks for your interest in improving Stellaris × Archipelago! Here's how the project is laid out and what kinds of changes go where.

## Repo Layout

The project has four layers, and most changes touch one of them:

| Layer | What it is | Where it lives |
|---|---|---|
| **apworld** | Archipelago world definition (items, locations, rules, options) | `apworld/stellaris/` |
| **client** | Python bridge between the AP server and the running game | `client/` |
| **DLL** | C++ proxy that injects console commands into Stellaris on Windows | `dll/` |
| **Stellaris mod** | Paradox script (events, scripted effects, technology, localisation) | `mod-install/archipelago_multiworld/` |

A change usually has to be made in 2–3 layers at once. For example, adding a new milestone location means touching `apworld/stellaris/locations.py`, then adding a sender to `mod-install/.../scripted_effects/ap_bridge_log.txt` and a detection block in `ap_check_detection.txt`. Adding a new item type means `apworld/stellaris/items.py` + `client/ap_bridge.py`'s `ITEM_EFFECT_MAP` + a new effect in `mod-install/.../scripted_effects/ap_item_effects.txt`.

## Coherence Rules

The four layers have to agree on ID and name boundaries:

- **Item IDs** in `apworld/stellaris/items.py` must match `ITEM_EFFECT_MAP` in `client/ap_bridge.py`, and every effect name in that map must be defined in `mod-install/.../scripted_effects/ap_item_effects.txt`.
- **Location IDs and names** in `apworld/stellaris/locations.py` must match the `AP_CHECK|<id>|<name>` lines in `mod-install/.../scripted_effects/ap_bridge_log.txt`. The name on both sides has to be byte-identical.
- **Tech-type locations** (the ones the bridge turns into AP-tech research entries) are listed in `TECH_LOCATION_IDS` in `client/ap_bridge.py`. Anything not in that set is treated as a milestone and detected by the static mod files.
- **Goal flags** (`ap_goal_0` through `ap_goal_4`) are pushed by the bridge based on `slot_data["goal"]`. The mod's `ap_check_victory_condition` keys off these.

When making a change, run the apworld's test suite *and* the cross-reference checks under `apworld/stellaris/test/` to catch ID/name drift early.

## Testing

```sh
# from your Archipelago checkout, with apworld/stellaris/ symlinked or copied
# into Archipelago/worlds/
python -m unittest discover -s worlds/stellaris/test
```

For end-to-end testing, `client/mock_ap_server.py` runs a fake AP server you can connect the bridge to without setting up a real session. See the README's "Testing Locally" section.

## Pull Request Checklist

- [ ] All tests under `apworld/stellaris/test/` pass
- [ ] No new ID/name mismatches between layers (the apworld tests catch most)
- [ ] If you added or changed locations/items, the mod's senders/effects were updated to match
- [ ] If you added a goal type, the bridge sets the right `ap_goal_N` flag and the mod has a matching detection branch
- [ ] Paradox script files (`*.txt` in `mod-install/`) have balanced braces
- [ ] No hardcoded paths or personal info in committed files

## Reporting Issues

When opening an issue please include:

- Stellaris version
- DLC enabled
- Archipelago version
- Bridge log output (`bridge.log` in your Stellaris user directory)
- Last ~50 lines of `game.log` if the issue is in-game

## License

Contributions are accepted under the project's MIT License.
