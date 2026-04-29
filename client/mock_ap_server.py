"""Mock Archipelago server for local testing.

Speaks just enough of the AP WebSocket protocol to:
  - Accept a client connection
  - Send RoomInfo + Connected
  - Send items to the client on demand
  - Receive LocationChecks from the client
  - Interactive console for sending items manually

No real Archipelago installation needed.

Usage:
    python mock_ap_server.py
    python mock_ap_server.py --port 38281

Then connect the Stellaris client:
    python stellaris_client.py --server localhost:38281 --slot Stellaris
"""

import asyncio
import json
import sys
import logging
from typing import Dict, List, Set

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MockAP")

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)

# =========================================================================
# Fake game data
# =========================================================================

GAME_NAME = "Stellaris"
SLOT_NAME = "Stellaris"
PLAYER_ID = 1
ALICE_ID = 2  # Fake Hollow Knight player
BOB_ID = 3    # Fake Terraria player

# Fake item tables (all games)
ITEMS = {
    # Stellaris items (for us)
    7_471_000: "Progressive Ship Class",
    7_471_001: "Progressive Weapons",
    7_471_002: "Progressive Defenses",
    7_471_003: "Progressive FTL",
    7_471_004: "Progressive Starbase",
    7_471_200: "Resource Cache (Small)",
    7_471_201: "Resource Cache (Medium)",
    7_471_220: "Research Boost",
    7_471_300: "Pirate Surge",
    7_471_301: "Diplomatic Incident",
    # Hollow Knight items (for Alice)
    9_000_001: "Mothwing Cloak",
    9_000_002: "Mantis Claw",
    9_000_003: "Crystal Heart",
    9_000_004: "Monarch Wings",
    9_000_005: "200 Geo",
    # Terraria items (for Bob)
    9_100_001: "Hermes Boots",
    9_100_002: "Cloud in a Bottle",
    9_100_003: "Magic Mirror",
}

# Stellaris locations (location_id → name)
LOCATIONS = {
    # Milestones
    7_472_000: "Survey 5 Systems",
    7_472_001: "Survey 10 Systems",
    7_472_010: "First Contact",
    7_472_100: "Research 5 Technologies",
    7_472_200: "Colonize 1 Planet",
    7_472_430: "Achieve 50k Fleet Power",
    # Tech-type (become researchable AP techs)
    7_472_030: "Enter a Wormhole",
    7_472_120: "Research Mega-Engineering",
    7_472_240: "Build a Megastructure",
    7_472_321: "Form the Galactic Imperium",
    7_472_440: "Defeat a Leviathan",
}

# What item is at each location (the randomized mapping)
# In a real AP session, this comes from the multiworld generation
LOCATION_ITEM_MAP = {
    # Milestones — items for various players
    7_472_000: {"item": 9_000_001, "player": ALICE_ID, "game": "Hollow Knight",
                "classification": "progression"},
    7_472_001: {"item": 7_471_000, "player": PLAYER_ID, "game": "Stellaris",
                "classification": "progression"},
    7_472_010: {"item": 9_100_001, "player": BOB_ID, "game": "Terraria",
                "classification": "useful"},
    7_472_100: {"item": 9_000_005, "player": ALICE_ID, "game": "Hollow Knight",
                "classification": "filler"},
    7_472_200: {"item": 7_471_200, "player": PLAYER_ID, "game": "Stellaris",
                "classification": "filler"},
    7_472_430: {"item": 7_471_001, "player": PLAYER_ID, "game": "Stellaris",
                "classification": "progression"},
    # Tech-type
    7_472_030: {"item": 9_000_002, "player": ALICE_ID, "game": "Hollow Knight",
                "classification": "progression"},
    7_472_120: {"item": 7_471_002, "player": PLAYER_ID, "game": "Stellaris",
                "classification": "progression"},
    7_472_240: {"item": 9_100_002, "player": BOB_ID, "game": "Terraria",
                "classification": "useful"},
    7_472_321: {"item": 7_471_300, "player": PLAYER_ID, "game": "Stellaris",
                "classification": "trap"},
    7_472_440: {"item": 9_000_003, "player": ALICE_ID, "game": "Hollow Knight",
                "classification": "useful"},
}

PLAYER_NAMES = {PLAYER_ID: SLOT_NAME, ALICE_ID: "Alice", BOB_ID: "Bob"}

# =========================================================================
# Server state
# =========================================================================

class MockServer:
    def __init__(self):
        self.client_ws = None
        self.checked_locations: Set[int] = set()
        self.items_sent: List[dict] = []
        self.item_index = 0
        self.energy_link_pool: int = 0

    async def handle_client(self, ws):
        self.client_ws = ws
        logger.info(f"Client connected from {ws.remote_address}")

        # Send RoomInfo
        await ws.send(json.dumps([{
            "cmd": "RoomInfo",
            "version": {"major": 0, "minor": 5, "build": 0, "class": "Version"},
            "generator_version": {"major": 0, "minor": 5, "build": 0, "class": "Version"},
            "tags": [],
            "password": False,
            "permissions": {},
            "hint_cost": 0,
            "location_check_points": 1,
            "games": [GAME_NAME],
            "datapackage_checksums": {},
            "seed_name": "TEST_SEED_001",
            "time": 0,
        }]))

        try:
            async for message in ws:
                data = json.loads(message)
                if isinstance(data, list):
                    for packet in data:
                        await self.handle_packet(packet)
                else:
                    await self.handle_packet(data)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected")
        finally:
            self.client_ws = None

    async def handle_packet(self, packet: dict):
        cmd = packet.get("cmd", "")

        if cmd == "Connect":
            slot = packet.get("slot", "?")
            logger.info(f"Client connecting as slot '{slot}'")

            # Send Connected
            await self.client_ws.send(json.dumps([{
                "cmd": "Connected",
                "team": 0,
                "slot": PLAYER_ID,
                "players": [
                    {"team": 0, "slot": PLAYER_ID, "alias": SLOT_NAME, "name": SLOT_NAME},
                    {"team": 0, "slot": ALICE_ID, "alias": "Alice", "name": "Alice"},
                    {"team": 0, "slot": BOB_ID, "alias": "Bob", "name": "Bob"},
                ],
                "missing_locations": list(LOCATIONS.keys()),
                "checked_locations": [],
                "slot_data": {},
                "slot_info": {
                    str(PLAYER_ID): {"game": GAME_NAME, "name": SLOT_NAME},
                    str(ALICE_ID): {"game": "Hollow Knight", "name": "Alice"},
                    str(BOB_ID): {"game": "Terraria", "name": "Bob"},
                },
            }]))
            logger.info("Sent Connected response")

        elif cmd == "LocationChecks":
            locations = packet.get("locations", [])
            for loc_id in locations:
                name = LOCATIONS.get(loc_id, f"Unknown ({loc_id})")
                if loc_id not in self.checked_locations:
                    self.checked_locations.add(loc_id)
                    logger.info(f"  ✓ CHECK RECEIVED: {name} (ID={loc_id})")

        elif cmd == "Sync":
            pass  # Client requesting sync, ignore

        elif cmd == "GetDataPackage":
            # Send minimal data package
            await self.client_ws.send(json.dumps([{
                "cmd": "DataPackage",
                "data": {
                    "games": {
                        GAME_NAME: {
                            "item_name_to_id": {v: k for k, v in ITEMS.items()},
                            "location_name_to_id": {v: k for k, v in LOCATIONS.items()},
                        }
                    }
                }
            }]))

        elif cmd == "LocationScouts":
            # Respond with what's at each scouted location
            locations = packet.get("locations", [])
            scout_items = []
            for loc_id in locations:
                mapping = LOCATION_ITEM_MAP.get(loc_id)
                if mapping:
                    # AP flags: 0b001=progression, 0b010=useful, 0b100=trap
                    classification = mapping.get("classification", "filler")
                    flags = {"progression": 1, "useful": 2, "trap": 4}.get(classification, 0)
                    scout_items.append({
                        "item": mapping["item"],
                        "location": loc_id,
                        "player": mapping["player"],
                        "flags": flags,
                    })
            await self.client_ws.send(json.dumps([{
                "cmd": "LocationInfo",
                "locations": scout_items,
            }]))
            logger.info(f"Scouted {len(scout_items)} locations")

        elif cmd == "Set":
            key = packet.get("key", "")
            if key.startswith("EnergyLink"):
                original = self.energy_link_pool
                for op in packet.get("operations", []):
                    if op["operation"] == "add":
                        self.energy_link_pool += int(op["value"])
                    elif op["operation"] == "max":
                        self.energy_link_pool = max(self.energy_link_pool, int(op["value"]))
                logger.info(f"  EnergyLink: {original} -> {self.energy_link_pool}")
                if packet.get("want_reply"):
                    reply = {
                        "cmd": "SetReply",
                        "key": key,
                        "value": self.energy_link_pool,
                        "original_value": original,
                    }
                    # Forward extra fields (like withdraw_id)
                    for k, v in packet.items():
                        if k not in ("cmd", "key", "default", "want_reply", "operations"):
                            reply[k] = v
                    await self.client_ws.send(json.dumps([reply]))

        elif cmd == "Get":
            keys = packet.get("keys", [])
            result = {}
            for key in keys:
                if key.startswith("EnergyLink"):
                    result[key] = self.energy_link_pool
            await self.client_ws.send(json.dumps([{
                "cmd": "Retrieved",
                "keys": result,
            }]))

        elif cmd == "SetNotify":
            pass  # We handle this implicitly

        else:
            logger.debug(f"Unhandled command: {cmd}")

    async def send_item(self, item_id: int):
        """Send an item to the connected client."""
        if not self.client_ws:
            logger.warning("No client connected!")
            return

        name = ITEMS.get(item_id, f"Unknown ({item_id})")
        self.item_index += 1

        await self.client_ws.send(json.dumps([{
            "cmd": "ReceivedItems",
            "index": self.item_index,
            "items": [{
                "item": item_id,
                "location": 0,
                "player": PLAYER_ID,
                "flags": 0,
            }],
        }]))
        logger.info(f"  → SENT ITEM: {name} (ID={item_id}, index={self.item_index})")


# =========================================================================
# Interactive console
# =========================================================================

async def console_loop(server: MockServer):
    """Interactive console for sending items."""
    await asyncio.sleep(1)  # Let server start first

    print("\n" + "=" * 60)
    print("MOCK ARCHIPELAGO SERVER — Interactive Console")
    print("=" * 60)
    print("\nCommands:")
    print("  ship    — Send Progressive Ship Class")
    print("  weapons — Send Progressive Weapons")
    print("  defense — Send Progressive Defenses")
    print("  ftl     — Send Progressive FTL")
    print("  starbase— Send Progressive Starbase")
    print("  cache   — Send Resource Cache (Small)")
    print("  research— Send Research Boost")
    print("  trap    — Send Pirate Surge (trap)")
    print("  diplo   — Send Diplomatic Incident (trap)")
    print("  <id>    — Send item by numeric ID")
    print("  status  — Show server status")
    print("  quit    — Stop server")
    print()

    shortcuts = {
        "ship": 7_471_000,
        "weapons": 7_471_001,
        "defense": 7_471_002,
        "ftl": 7_471_003,
        "starbase": 7_471_004,
        "cache": 7_471_200,
        "research": 7_471_220,
        "trap": 7_471_300,
        "diplo": 7_471_301,
    }

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("AP> ")
            )
        except (EOFError, KeyboardInterrupt):
            break

        line = line.strip().lower()
        if not line:
            continue
        if line == "quit":
            break
        if line == "status":
            connected = "Yes" if server.client_ws else "No"
            print(f"  Client connected: {connected}")
            print(f"  Items sent: {server.item_index}")
            print(f"  Checks received: {len(server.checked_locations)}")
            print(f"  EnergyLink pool: {server.energy_link_pool} EC")
            for loc_id in sorted(server.checked_locations):
                name = LOCATIONS.get(loc_id, f"Unknown ({loc_id})")
                print(f"    ✓ {name}")
            continue

        if line in shortcuts:
            await server.send_item(shortcuts[line])
        elif line.isdigit():
            await server.send_item(int(line))
        else:
            print(f"  Unknown command: {line}")


# =========================================================================
# Main
# =========================================================================

async def main(port: int = 38281):
    server = MockServer()

    async with websockets.serve(server.handle_client, "localhost", port):
        logger.info(f"Mock AP server running on ws://localhost:{port}")
        logger.info(f"Connect with: python stellaris_client.py --server localhost:{port} --slot {SLOT_NAME}")
        await console_loop(server)

    logger.info("Server stopped")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mock Archipelago server")
    parser.add_argument("--port", type=int, default=38281)
    args = parser.parse_args()

    try:
        asyncio.run(main(args.port))
    except KeyboardInterrupt:
        pass
