"""Stellaris Archipelago Bridge — threaded, no asyncio.

Three threads:
  1. WebSocket receiver: reads AP server messages → puts items in a queue
  2. Pipe sender: takes from queue → sends to DLL pipe (blocking, ~500ms each)
  3. Log tailer: polls game.log → sends checks to AP server

Usage:
    pip install websocket-client
    python ap_bridge.py --server localhost:38281 --slot Stellaris

Or with the async websockets lib:
    pip install websockets
    python ap_bridge.py --server localhost:38281 --slot Stellaris
"""

import json
import logging
import re
import sys
import time
import threading
import queue
from pathlib import Path
from typing import Dict, List, Optional, Set

# Make sibling modules (tech_catalog, slot_generator) importable when the
# bridge is launched from any cwd.
sys.path.insert(0, str(Path(__file__).parent))
from tech_catalog import (  # noqa: E402
    TECH_CATALOG,
    by_key as _tech_by_key,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("APBridge")


# Item-ID base for catalog Tech: items (BASE_ID + 20000 + offset).
# Effect names follow ap_grant_tech_<key>; the matching scripted_effect
# lives in mod-install/.../ap_item_effects.txt.
_TECH_ITEM_BASE = 7_491_000  # = 7_471_000 + 20000
_TECH_LOCATION_BASE = 7_481_000  # = 7_471_000 + 10000


def _catalog_item_effects() -> Dict[int, str]:
    """item_id → ap_grant_tech_<key> for every catalog tech (always populated;
    selection-filtering happens via slot_data, not here — the map is a
    superset and only selected items will ever actually be received)."""
    return {
        _TECH_ITEM_BASE + t.offset: f"ap_grant_tech_{t.key}"
        for t in TECH_CATALOG
    }


def _catalog_location_ids_for(selected_keys: Set[str]) -> Set[int]:
    """The Research-X location IDs the player chose to randomize."""
    by_key = _tech_by_key()
    return {
        _TECH_LOCATION_BASE + by_key[k].offset
        for k in selected_keys if k in by_key
    }


def _catalog_block_flags_for(selected_keys: Set[str]) -> List[str]:
    """Country flags the bridge sets at connect to hide vanilla techs.
    These are read by 00_aaa_ap_tech_blocks.txt's potential clauses."""
    return [f"ap_tech_blocked_{k}" for k in sorted(selected_keys)]


ITEM_EFFECT_MAP: Dict[int, str] = {
    7_471_000: "ap_grant_progressive_ship_class",
    7_471_001: "ap_grant_progressive_weapons",
    7_471_002: "ap_grant_progressive_defenses",
    7_471_003: "ap_grant_progressive_ftl",
    7_471_004: "ap_grant_progressive_starbase",
    7_471_005: "ap_grant_progressive_colony_ship",
    7_471_006: "ap_grant_progressive_administration",
    7_471_007: "ap_grant_progressive_diplomacy",
    7_471_100: "ap_grant_mega_engineering_license",
    7_471_101: "ap_grant_progressive_megastructure",
    7_471_110: "ap_grant_ascension_bio",
    7_471_111: "ap_grant_ascension_synth",
    7_471_112: "ap_grant_ascension_psi",
    7_471_120: "ap_grant_lgate_insight",
    7_471_121: "ap_grant_precursor_unlock",
    7_471_130: "ap_grant_galactic_market",
    7_471_140: "ap_grant_crisis_beacon",
    7_471_200: "ap_grant_resource_cache_small",
    7_471_201: "ap_grant_resource_cache_medium",
    7_471_202: "ap_grant_resource_cache_large",
    7_471_210: "ap_grant_alloy_shipment_small",
    7_471_211: "ap_grant_alloy_shipment_medium",
    7_471_212: "ap_grant_alloy_shipment_large",
    7_471_220: "ap_grant_research_boost",
    7_471_221: "ap_grant_influence_burst",
    7_471_222: "ap_grant_unity_windfall",
    7_471_240: "ap_grant_fleet_cap_10",
    7_471_241: "ap_grant_fleet_cap_20",
    7_471_242: "ap_grant_starbase_cap_1",
    7_471_230: "ap_grant_pop_growth_stimulus",
    7_471_231: "ap_grant_edict_fund",
    7_471_223: "ap_grant_minor_relic",
    7_471_300: "ap_trigger_pirate_surge",
    7_471_301: "ap_trigger_diplomatic_incident",
    7_471_302: "ap_trigger_research_setback",
    7_471_303: "ap_trigger_market_crash",
    7_471_304: "ap_trigger_space_amoeba",
    7_471_305: "ap_trigger_border_friction",
}
# Append catalog Tech: items (one per catalog entry, always populated).
# Items the player didn't randomize will simply never be received.
ITEM_EFFECT_MAP.update(_catalog_item_effects())

# Static event-style tech locations (Find Anomalies, Form Federation, etc.)
# These always appear, regardless of randomized_techs. Catalog-driven
# Research-X locations are added per-slot via _catalog_location_ids_for()
# at connect time and stored in self.tech_location_ids.
_STATIC_TECH_LOCATION_IDS: Set[int] = {
    7_472_020,  # Find 3 Anomalies
    7_472_021,  # Find 6 Anomalies
    7_472_030,  # Enter a Wormhole
    7_472_040,  # Complete a Precursor Chain
    7_472_050,  # Explore the L-Cluster
    7_472_110,  # Research a Rare Tech
    7_472_120,  # Research Mega-Engineering
    7_472_130,  # Research a Repeatable Tech
    7_472_240,  # Build a Megastructure
    7_472_241,  # Complete a Megastructure
    7_472_300,  # Form or Join a Federation
    7_472_301,  # Federation Level 3
    7_472_302,  # Federation Level 5
    7_472_310,  # Join Galactic Community
    7_472_311,  # Pass a Galactic Resolution
    7_472_320,  # Become Custodian
    7_472_321,  # Form the Galactic Imperium
    7_472_330,  # Integrate a Subject
    7_472_350,  # Have 3 Envoys Active
    7_472_410,  # Destroy a Starbase
    7_472_420,  # Conquer a Capital
    7_472_440,  # Defeat a Leviathan
    7_472_450,  # Destroy a Fallen Empire
    7_472_520,  # Complete Biological Ascension
    7_472_521,  # Complete Synthetic Ascension
    7_472_522,  # Complete Psionic Ascension
    7_472_600,  # Survive the Crisis 10 Years
    7_472_601,  # Defeat the Endgame Crisis
    7_472_610,  # Become the Crisis Tier 1
    7_472_611,  # Become the Crisis Tier 5
    7_472_620,  # Control 40% of Galaxy
    7_472_621,  # Control 60% of Galaxy
}


def find_stellaris_dir() -> Path:
    home = Path.home()
    for p in [
        home / "Documents" / "Paradox Interactive" / "Stellaris",
        home / "OneDrive" / "Documents" / "Paradox Interactive" / "Stellaris",
    ]:
        if p.exists():
            return p
    return home / "Documents" / "Paradox Interactive" / "Stellaris"


def find_game_log(d: Path) -> Path:
    for n in ["logs/game.log", "log/game.log"]:
        p = d / n
        if p.exists():
            return p
    return d / "logs" / "game.log"


# =========================================================================
# WebSocket wrapper — supports both websocket-client (sync) and websockets (async)
# =========================================================================

class WSConnection:
    """Thin wrapper over websocket-client or websockets."""

    def __init__(self, url: str):
        self.url = url
        self._ws = None
        self._lib = None
        self._lock = threading.Lock()

    def connect(self):
        # Try websocket-client first (synchronous, simpler)
        try:
            import websocket
            self._lib = "websocket-client"
            self._ws = websocket.create_connection(self.url)
            logger.info(f"Connected via websocket-client to {self.url}")
            return True
        except ImportError:
            pass

        # Fallback to websockets (async) used synchronously
        try:
            import websockets.sync.client
            self._lib = "websockets-sync"
            self._ws = websockets.sync.client.connect(self.url)
            logger.info(f"Connected via websockets.sync to {self.url}")
            return True
        except (ImportError, AttributeError):
            pass

        logger.error("No WebSocket library found!")
        logger.error("Install one: pip install websocket-client")
        return False

    def send(self, data: str):
        with self._lock:
            self._ws.send(data)

    def recv(self) -> str:
        return self._ws.recv()

    def close(self):
        if self._ws:
            self._ws.close()


# =========================================================================
# Bridge
# =========================================================================

class StellarisAPBridge:
    def __init__(self, server: str, slot: str, password: str = ""):
        self.server = server
        self.slot = slot
        self.password = password
        self.ws: Optional[WSConnection] = None

        self.item_queue: queue.Queue = queue.Queue()
        self.processed_indices: Set[int] = set()
        self.sent_checks: Set[int] = set()
        self.item_names: Dict[int, str] = {}
        self.location_names: Dict[int, str] = {}
        self.player_names: Dict[int, str] = {}
        self.player_games: Dict[int, str] = {}
        self.player_id: int = 0
        self.all_locations: list = []
        self.scouted = False

        # EnergyLink
        self.energy_link_value: Optional[int] = None
        self.energy_link_enabled: bool = False
        self.energy_link_rate: int = 100
        self.team: int = 0

        # Goal selected by the player (from slot_data) — 0=Victory, 1=Crisis Averted,
        # 2=Ascension, 3=Galactic Emperor, 4=All Checks. Defaults to 0 until Connected.
        self.goal: int = 0

        # Set of location IDs that should be treated as researchable AP techs.
        # Starts with the static event-style locations (Find Anomalies, etc.)
        # and is extended at connect time with the player's catalog selection.
        self.tech_location_ids: Set[int] = set(_STATIC_TECH_LOCATION_IDS)

        # Catalog tech keys this slot randomized (filled from slot_data).
        self.randomized_techs: List[str] = []

        self.stellaris_dir = find_stellaris_dir()
        self._state_file = self.stellaris_dir / "ap_bridge_state.json"
        self.mod_dir = self.stellaris_dir / "mod" / "archipelago_multiworld"
        self.log_path = find_game_log(self.stellaris_dir)
        self.running = True

        # Load persisted state (must be after _state_file is set)
        self._load_state()

    def run(self):
        # Support ws:// and wss://
        if self.server.startswith("ws://") or self.server.startswith("wss://"):
            url = self.server
        else:
            url = f"ws://{self.server}"

        while self.running:
            logger.info(f"Connecting to {url} as '{self.slot}'...")
            self.ws = WSConnection(url)
            if not self.ws.connect():
                logger.warning("Connection failed, retrying in 5s...")
                time.sleep(5)
                continue

            try:
                # Handshake: receive RoomInfo
                msg = self.ws.recv()
                for p in json.loads(msg):
                    if p.get("cmd") == "RoomInfo":
                        logger.info(f"Room: seed={p.get('seed_name', '?')}")

                # Send Connect
                self.ws.send(json.dumps([{
                    "cmd": "Connect",
                    "password": self.password,
                    "name": self.slot,
                    "version": {"major": 0, "minor": 5, "build": 0, "class": "Version"},
                    "items_handling": 0b111,
                    "tags": [],
                    "uuid": "",
                    "game": "Stellaris",
                    "slot_data": True,
                }]))

                # Start threads
                threads = [
                    threading.Thread(target=self._receiver_thread, name="ws-recv", daemon=True),
                    threading.Thread(target=self._sender_thread, name="pipe-send", daemon=True),
                    threading.Thread(target=self._log_thread, name="log-tail", daemon=True),
                ]
                for t in threads:
                    t.start()

                logger.info("Bridge running. Press Ctrl+C to stop.")
                while self.running:
                    time.sleep(0.5)

            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                logger.error(f"Session error: {e}")
            finally:
                self.ws.close()

            if self.running:
                logger.warning("Connection lost. Reconnecting in 5s...")
                time.sleep(5)

        logger.info("Bridge stopped.")

    # ---- Thread 1: WebSocket receiver ----
    def _receiver_thread(self):
        """Reads WebSocket messages, puts items in queue."""
        logger.info("[recv] Receiver thread started")
        while self.running:
            try:
                raw = self.ws.recv()
                packets = json.loads(raw)
                if not isinstance(packets, list):
                    packets = [packets]

                for packet in packets:
                    self._handle_packet(packet)
            except Exception as e:
                if self.running:
                    logger.error(f"[recv] Error: {e}")
                    time.sleep(1)
                break

        logger.info("[recv] Receiver thread ended")

    def _load_state(self):
        """Load persisted checks/items from disk."""
        try:
            if self._state_file.exists():
                import json as j
                data = j.loads(self._state_file.read_text())
                self.sent_checks = set(data.get("sent_checks", []))
                self.processed_indices = set(data.get("processed_indices", []))
                logger.info(f"Loaded state: {len(self.sent_checks)} checks, {len(self.processed_indices)} items")
        except Exception as e:
            logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        """Persist checks/items to disk."""
        try:
            import json as j
            data = {
                "sent_checks": list(self.sent_checks),
                "processed_indices": list(self.processed_indices),
            }
            self._state_file.write_text(j.dumps(data))
        except Exception as e:
            logger.warning(f"Could not save state: {e}")

    @property
    def energylink_key(self) -> str:
        return f"EnergyLink{self.team}"

    def _handle_packet(self, packet: dict):
        cmd = packet.get("cmd", "")

        if cmd == "Connected":
            self.player_id = packet.get("slot", 0)
            self.team = packet.get("team", 0)
            checked = set(packet.get("checked_locations", []))
            self.sent_checks.update(checked)
            self.all_locations = packet.get("missing_locations", []) + list(checked)

            # Read slot_data for goal + EnergyLink config
            slot_data = packet.get("slot_data", {}) or {}
            self.goal = int(slot_data.get("goal", 0))
            self.energy_link_enabled = bool(slot_data.get("energy_link_enabled", False))
            self.energy_link_rate = int(slot_data.get("energy_link_rate", 100))

            # Catalog tech selection — drives Research-X locations and
            # the vanilla-tech blocking flags this slot needs.
            self.randomized_techs = list(slot_data.get("randomized_techs", []))
            selected = set(self.randomized_techs)
            catalog_loc_ids = _catalog_location_ids_for(selected)
            self.tech_location_ids = set(_STATIC_TECH_LOCATION_IDS) | catalog_loc_ids

            for p in packet.get("players", []):
                self.player_names[p["slot"]] = p["alias"]

            slot_info = packet.get("slot_info", {})
            for sid, info in slot_info.items():
                self.player_games[int(sid)] = info.get("game", "Unknown")

            logger.info(f"Connected as player {self.player_id}")
            logger.info(f"Players: {self.player_names}")
            logger.info(f"Locations: {len(self.all_locations)} ({len(checked)} already checked)")
            logger.info(f"Goal: {self.goal} | EnergyLink: {self.energy_link_enabled}")
            logger.info(f"Randomized techs: {len(self.randomized_techs)} "
                        f"({len(catalog_loc_ids)} catalog Research-X locations)")

            # Push the chosen goal into the mod as a country flag so the mod
            # can detect the right victory condition for this seed.
            self.item_queue.put(("raw_effect", f"set_country_flag = ap_goal_{self.goal}"))

            # Push tech-blocking flags so 00_aaa_ap_tech_blocks.txt hides
            # randomized vanilla techs from the player's research pool.
            for flag in _catalog_block_flags_for(selected):
                self.item_queue.put(("raw_effect", f"set_country_flag = {flag}"))

            # Re-send any checks we have locally that the server doesn't know about
            unsent = self.sent_checks - checked
            if unsent:
                logger.info(f"Re-sending {len(unsent)} locally-stored checks...")
                self.ws.send(json.dumps([{
                    "cmd": "LocationChecks",
                    "locations": list(unsent),
                }]))

            # Subscribe to EnergyLink updates
            self.ws.send(json.dumps([{
                "cmd": "SetNotify", "keys": [self.energylink_key]
            }]))
            # Get current EnergyLink value
            self.ws.send(json.dumps([{
                "cmd": "Get", "keys": [self.energylink_key]
            }]))
            logger.info(f"EnergyLink: subscribed to {self.energylink_key}")

            # Request DataPackage
            self.ws.send(json.dumps([{"cmd": "GetDataPackage"}]))

        elif cmd == "DataPackage":
            for game, gdata in packet.get("data", {}).get("games", {}).items():
                for iname, iid in gdata.get("item_name_to_id", {}).items():
                    self.item_names[iid] = iname
                for lname, lid in gdata.get("location_name_to_id", {}).items():
                    self.location_names[lid] = lname
            logger.info(f"DataPackage: {len(self.item_names)} items, {len(self.location_names)} locations")

            # Now scout all our locations to find what's at each one
            if self.all_locations and not self.scouted:
                logger.info(f"Scouting {len(self.all_locations)} locations...")
                self.ws.send(json.dumps([{
                    "cmd": "LocationScouts",
                    "locations": self.all_locations,
                }]))
                self.scouted = True

        elif cmd == "LocationInfo":
            # Server tells us what's at each scouted location
            scouted = packet.get("locations", [])
            logger.info(f"Received scout info for {len(scouted)} locations")
            self._generate_dynamic_techs(scouted)

        elif cmd == "ReceivedItems":
            base_index = packet.get("index", 0)
            for i, item in enumerate(packet.get("items", [])):
                idx = base_index + i
                if idx in self.processed_indices:
                    continue
                self.processed_indices.add(idx)
                item_id = item.get("item", 0)
                sender = item.get("player", 0)
                name = self.item_names.get(item_id, f"Item #{item_id}")
                sender_name = self.player_names.get(sender, f"Player {sender}")
                logger.info(f"  ← RECEIVED: {name} (from {sender_name})")
                self.item_queue.put(item_id)
                self._save_state()

        elif cmd == "PrintJSON":
            parts = packet.get("data", [])
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
            if text:
                logger.info(f"  💬 {text}")

        elif cmd == "SetReply":
            key = packet.get("key", "")
            if key.startswith("EnergyLink"):
                current = int(packet.get("value", 0))
                original = int(packet.get("original_value", current))
                self.energy_link_value = current
                # If original > current, we successfully withdrew
                gained = original - current
                if gained > 0:
                    logger.info(f"  💰 EnergyLink: withdrew {gained} EC (pool: {current})")
                    self._grant_energy(gained)
                elif original < current:
                    # A deposit was confirmed
                    logger.info(f"  💰 EnergyLink: deposit confirmed (pool: {current})")

        elif cmd == "Retrieved":
            keys = packet.get("keys", {})
            for key, value in keys.items():
                if key.startswith("EnergyLink"):
                    self.energy_link_value = int(value) if value else 0
                    logger.info(f"  💰 EnergyLink pool: {self.energy_link_value} EC")

    def _generate_dynamic_techs(self, scouted_locations: list):
        """Build slot data from scouted locations and generate mod files."""
        # AP flags → classification
        flag_to_class = {1: "progression", 2: "useful", 4: "trap"}

        slot_data = []
        for loc in scouted_locations:
            loc_id = loc.get("location", 0)
            item_id = loc.get("item", 0)
            player_id = loc.get("player", 0)
            flags = loc.get("flags", 0)

            loc_name = self.location_names.get(loc_id, f"Location {loc_id}")
            item_name = self.item_names.get(item_id, f"Item {item_id}")
            player_name = self.player_names.get(player_id, f"Player {player_id}")
            game = self.player_games.get(player_id, "Unknown")
            is_own = (player_id == self.player_id)

            # Determine classification from flags
            classification = flag_to_class.get(flags, "filler")

            # Determine location type from embedded set
            loc_type = "tech" if loc_id in self.tech_location_ids else "milestone"

            slot_data.append({
                "location_id": loc_id,
                "location_name": loc_name,
                "item_name": item_name,
                "player_name": player_name,
                "game": game,
                "classification": classification,
                "is_own_item": is_own,
                "location_type": loc_type,
            })

        # Generate mod files
        from slot_generator import generate_mod_files, clear_dynamic_files
        clear_dynamic_files(self.mod_dir)

        tech_count = sum(1 for s in slot_data if s["location_type"] == "tech")
        milestone_count = sum(1 for s in slot_data if s["location_type"] == "milestone")

        blocked_techs = generate_mod_files(slot_data, self.mod_dir)
        if blocked_techs is not None:
            logger.info(f"Generated {tech_count} AP techs ({milestone_count} milestones auto-detected)")
            logger.info(f"Blocking {len(blocked_techs)} vanilla techs (sent to other worlds)")

            # Queue blocking flags — these will be sent via pipe when the game runs
            # Each flag hides the corresponding vanilla tech from the research pool
            for tech_key in blocked_techs:
                self.item_queue.put(("raw_effect", f"set_country_flag = ap_tech_blocked_{tech_key}"))

            logger.info("")
            logger.info("=" * 60)
            logger.info("DYNAMIC TECHS GENERATED!")
            logger.info("Restart Stellaris for the AP techs to appear in-game.")
            logger.info("After loading, the bridge will send blocking flags to hide")
            logger.info("vanilla techs that were sent to other worlds.")
            logger.info("=" * 60)
            logger.info("")
        else:
            logger.error("Failed to generate dynamic tech files!")

    # ---- Thread 2: Pipe sender ----
    def _sender_thread(self):
        """Takes items from queue, batches them, sends to DLL pipe."""
        logger.info("[send] Sender thread started")
        while self.running:
            # Collect first item (blocking)
            try:
                msg = self.item_queue.get(timeout=1)
            except queue.Empty:
                continue

            # Collect any additional queued items (non-blocking batch)
            batch = [msg]
            while not self.item_queue.empty():
                try:
                    batch.append(self.item_queue.get_nowait())
                except queue.Empty:
                    break

            # Convert to effect commands
            effects = []
            for msg in batch:
                if isinstance(msg, tuple) and msg[0] == "raw_effect":
                    effects.append(msg[1])
                elif isinstance(msg, int):
                    item_id = msg
                    effect = ITEM_EFFECT_MAP.get(item_id)
                    if effect:
                        effects.append(f"{effect} = yes")
                    else:
                        effects.append(f"set_country_flag = ap_item_{item_id}")

            # Send entire batch in one pipe session
            if effects:
                self._send_batch_to_pipe(effects)

        logger.info("[send] Sender thread ended")

    def _send_batch_to_pipe(self, effects: list):
        """Send a batch of effects in a single pipe connection."""
        if sys.platform != "win32":
            for e in effects:
                logger.warning(f"  → NO PIPE (non-Windows): {e}")
            return

        from pipe_client import create_pipe_client
        pipe = create_pipe_client()
        if pipe.connect():
            for effect_cmd in effects:
                pipe.send_effect(effect_cmd)
            flushed = pipe.flush_commands()
            pipe.disconnect()
            logger.info(f"  → PIPE: {len(effects)} effect(s) sent, {flushed} flushed")
            for e in effects:
                logger.info(f"    {e}")
        else:
            logger.warning(f"  → NO PIPE: {len(effects)} effect(s) lost (DLL not running?)")

    def _grant_energy(self, amount: int):
        """Grant energy credits in-game from EnergyLink withdrawal."""
        self.item_queue.put(("raw_effect", f"add_resource = {{ energy = {amount} }}"))

    # ---- Thread 3: Log tailer ----
    def _log_thread(self):
        """Polls game.log for AP_CHECK lines."""
        logger.info(f"[log] Tailer started: {self.log_path}")
        RE_CHECK = re.compile(r"AP_CHECK\|(\d+)\|(.+)")
        RE_GOAL = re.compile(r"AP_GOAL_COMPLETE")
        RE_DEPOSIT = re.compile(r"AP_ENERGY_DEPOSIT\|(\d+)")
        RE_WITHDRAW = re.compile(r"AP_ENERGY_WITHDRAW\|(\d+)")

        pos = self.log_path.stat().st_size if self.log_path.exists() else 0

        while self.running:
            try:
                if not self.log_path.exists():
                    time.sleep(1)
                    continue

                size = self.log_path.stat().st_size
                if size < pos:
                    logger.info("[log] File reset")
                    pos = 0
                if size <= pos:
                    time.sleep(0.5)
                    continue

                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(pos)
                    for line in f:
                        if "AP_" not in line:
                            continue
                        m = RE_CHECK.search(line)
                        if m:
                            loc_id = int(m.group(1))
                            loc_name = m.group(2).strip()
                            if loc_id not in self.sent_checks:
                                self.sent_checks.add(loc_id)
                                logger.info(f"  → CHECK: {loc_name} (ID={loc_id})")
                                self.ws.send(json.dumps([{
                                    "cmd": "LocationChecks",
                                    "locations": [loc_id],
                                }]))
                                self._save_state()

                                # Goal 4 (All Checks): if every location is now sent,
                                # the player has completed their goal.
                                if (
                                    self.goal == 4
                                    and self.all_locations
                                    and set(self.all_locations).issubset(self.sent_checks)
                                ):
                                    logger.info("  🏆 ALL CHECKS COMPLETE — goal satisfied!")
                                    self.ws.send(json.dumps([{
                                        "cmd": "StatusUpdate",
                                        "status": 30,
                                    }]))
                        if RE_GOAL.search(line):
                            logger.info("  🏆 GOAL COMPLETE!")
                            self.ws.send(json.dumps([{
                                "cmd": "StatusUpdate",
                                "status": 30,
                            }]))
                        md = RE_DEPOSIT.search(line)
                        if md:
                            amount = int(md.group(1))
                            logger.info(f"  💰 EnergyLink deposit: {amount} EC")
                            # 1 Stellaris EC = 1 AP EnergyLink unit (1:1 with Factorio)
                            self.ws.send(json.dumps([{
                                "cmd": "Set",
                                "key": self.energylink_key,
                                "default": 0,
                                "want_reply": False,
                                "operations": [
                                    {"operation": "add", "value": amount}
                                ]
                            }]))
                        mw = RE_WITHDRAW.search(line)
                        if mw:
                            amount = int(mw.group(1))
                            pool = self.energy_link_value or 0
                            if pool <= 0:
                                logger.info(f"  💰 EnergyLink: pool empty, cannot withdraw")
                                continue
                            # Withdraw up to what's available
                            withdraw = min(amount, pool)
                            logger.info(f"  💰 EnergyLink withdraw: requesting {withdraw} EC (pool: {pool})")
                            self.ws.send(json.dumps([{
                                "cmd": "Set",
                                "key": self.energylink_key,
                                "default": 0,
                                "want_reply": True,
                                "operations": [
                                    {"operation": "add", "value": -withdraw},
                                    {"operation": "max", "value": 0},
                                ],
                            }]))
                    pos = f.tell()

            except Exception as e:
                logger.error(f"[log] Error: {e}")
                time.sleep(1)

        logger.info("[log] Tailer ended")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Stellaris AP Bridge")
    parser.add_argument("--server", required=True, help="AP server (host:port)")
    parser.add_argument("--slot", required=True, help="Slot/player name")
    parser.add_argument("--password", default="", help="Room password")
    args = parser.parse_args()

    bridge = StellarisAPBridge(args.server, args.slot, args.password)
    bridge.run()


if __name__ == "__main__":
    main()
