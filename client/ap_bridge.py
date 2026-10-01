"""Stellaris Archipelago Bridge — threaded, no asyncio.

Three threads per server session:
  1. WebSocket receiver: reads AP server messages -> puts items in a queue
  2. Pipe sender: takes from queue -> sends to DLL pipe (blocking, ~500ms each)
  3. Log tailer: polls game.log -> sends checks to AP server

Delivery model
--------------
Console effects only work while a save is loaded. The DLL pipe exists as
soon as stellaris.exe starts (main menu included), and an effect executed
at the main menu is silently lost. So the sender only talks to the pipe
once the mod has *reported in* for the current game process — any AP_*
line in game.log (the monthly AP_HEARTBEAT, AP_CONNECTED when the player
accepts the connection popup, or a check). When game.log is recreated
(Stellaris restarted) the bridge goes back to waiting, and the first
report from the new process triggers a resync of all persistent state
(goal flag, tech-blocking flags, EnergyLink flag) before any items.

Usage:
    pip install websocket-client
    python ap_bridge.py --server localhost:38281 --slot Stellaris
"""

import json
import logging
import math
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

# The "Victory" location. The mod sends it when the player's chosen goal
# is reached in-game (goals 0-3). For goal 4 (All Checks) the bridge
# sends it itself once every other location has been checked.
VICTORY_LOCATION_ID = 7_472_900
GOAL_ALL_CHECKS = 4

# AP client status codes
CLIENT_GOAL = 30


def _catalog_item_effects() -> Dict[int, str]:
    """item_id -> ap_grant_tech_<key> for every catalog tech (always populated;
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
    # Shared marker-based detection (client/ap_paths.py): prefers the
    # directory with recent game activity, honors STELLARIS_USER_DIR.
    from ap_paths import find_stellaris_user_dir
    return find_stellaris_user_dir(fallback=True)


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
        # Pick whichever WebSocket library is available. Library-import
        # failure and connection failure are handled separately so a
        # failed connect() returns False instead of raising — otherwise
        # the bridge crashes through main() instead of retrying.
        create = None
        lib = None
        try:
            import websocket
            lib = "websocket-client"
            create = lambda: websocket.create_connection(self.url, timeout=15)
        except ImportError:
            try:
                import websockets.sync.client
                lib = "websockets-sync"
                create = lambda: websockets.sync.client.connect(self.url, open_timeout=15)
            except (ImportError, AttributeError):
                logger.error("No WebSocket library found!")
                logger.error("Install one: pip install websocket-client")
                return False

        # Any connect-time failure (TLS mismatch, DNS, refused,
        # remote close mid-handshake, timeout, ...) is logged and
        # converted to a False return so run() can retry.
        try:
            self._ws = create()
            self._lib = lib
            logger.info(f"Connected via {lib} to {self.url}")
            return True
        except Exception as e:
            logger.warning(f"Connect to {self.url} failed: {type(e).__name__}: {e}")
            return False

    def send(self, data: str):
        with self._lock:
            self._ws.send(data)

    def recv(self, timeout: Optional[float] = None) -> str:
        """Receive one message. timeout=None blocks until data or close."""
        if self._lib == "websockets-sync":
            return self._ws.recv(timeout=timeout)
        # websocket-client: the timeout lives on the socket.
        self._ws.settimeout(timeout)
        return self._ws.recv()

    def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass


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
        self.room_games: List[str] = []
        self.scouted = False

        # EnergyLink. The pool is stored in EnergyLink units; the YAML
        # option energy_link_rate is "energy credits per unit".
        self.energy_link_value: Optional[int] = None
        self.energy_link_enabled: bool = False
        self.energy_link_rate: int = 100
        self.team: int = 0

        # Goal selected by the player (from slot_data) — 0=Victory, 1=Crisis Averted,
        # 2=Ascension, 3=Galactic Emperor, 4=All Checks. Defaults to 0 until Connected.
        self.goal: int = 0
        self._goal_sent = False

        # Set of location IDs that should be treated as researchable AP techs.
        # Starts with the static event-style locations (Find Anomalies, etc.)
        # and is extended at connect time with the player's catalog selection.
        self.tech_location_ids: Set[int] = set(_STATIC_TECH_LOCATION_IDS)

        # Catalog tech keys this slot randomized (filled from slot_data).
        self.randomized_techs: List[str] = []

        self.stellaris_dir = find_stellaris_dir()
        # State is keyed by seed+slot so joining a new multiworld never
        # replays checks/items from an old one. The real path is set once
        # RoomInfo tells us the seed; until then state stays empty.
        self._state_file: Optional[Path] = None
        self._state_lock = threading.Lock()
        self.mod_dir = self.stellaris_dir / "mod" / "archipelago_multiworld"
        self.log_path = find_game_log(self.stellaris_dir)
        self.running = True

        # Connection-liveness signalling between threads:
        # the receiver sets _disconnected on socket loss; the main loop
        # waits on it and reconnects. _session_stop tells the per-session
        # worker threads to exit so a reconnect never doubles them up.
        self._disconnected = threading.Event()
        self._session_stop = threading.Event()

        # Item indices that are queued for pipe delivery but not yet
        # delivered. Only after a successful pipe write do they move into
        # processed_indices (and get persisted) — items received while
        # Stellaris is closed are retried, never dropped.
        self._pending_indices: Set[int] = set()

        # --- Game-session tracking (see module docstring) ---
        # Set once the mod has written an AP_* line to game.log for the
        # current Stellaris process; cleared when game.log is recreated.
        self._game_active = threading.Event()
        # Persistent country flags that must exist in every save of this
        # seed: goal, tech blocking, EnergyLink. Re-sent whenever a game
        # session becomes active, and whenever they change.
        self._state_effects: List[str] = []
        self._resync_needed = threading.Event()

        # Logged once per game session: which delivery mode the DLL is in.
        self._dll_status_logged = False

        # Log tailer position. Lives on the bridge (not the thread) so a
        # server reconnect never skips lines written during the outage.
        # None = not initialised; the first pass starts at end-of-file so
        # a stale log from an earlier campaign is never replayed.
        self._log_pos: Optional[int] = None
        self._log_ident = None  # (creation time, inode) of the tailed file

    def run(self):
        # Determine candidate URL(s) for the connection.
        # If the user provided a scheme, respect it exactly. Otherwise
        # try wss:// first (matches the public archipelago.gg service,
        # which terminates TLS) and fall back to ws:// for self-hosted
        # servers that don't. Once a candidate works it's reused on
        # reconnect so we don't pay the fallback cost every blip.
        if self.server.startswith(("ws://", "wss://")):
            url_candidates = [self.server]
        else:
            url_candidates = [f"wss://{self.server}", f"ws://{self.server}"]

        working_url: Optional[str] = None

        logger.info(f"Stellaris user dir: {self.stellaris_dir}")
        logger.info(f"Tailing: {self.log_path}")
        if not (self.mod_dir / "descriptor.mod").exists():
            logger.warning(
                f"The Archipelago mod is not installed at {self.mod_dir} — "
                "run 'python setup.py install' (or use the dashboard) "
                "before starting Stellaris.")

        while self.running:
            urls = [working_url] if working_url else url_candidates
            for url in urls:
                logger.info(f"Connecting to {url} as '{self.slot}'...")
                self.ws = WSConnection(url)
                if self.ws.connect():
                    working_url = url
                    break
            else:
                # No candidate succeeded.
                logger.warning("Connection failed, retrying in 5s...")
                time.sleep(5)
                continue

            threads = []
            try:
                # Handshake: receive RoomInfo. A server that accepts the
                # socket but never speaks must not hang us forever.
                msg = self.ws.recv(timeout=30)
                for p in json.loads(msg):
                    if p.get("cmd") == "RoomInfo":
                        seed = p.get("seed_name", "")
                        self.room_games = list(p.get("games", []) or [])
                        logger.info(f"Room: seed={seed or '?'}")
                        self._set_state_file(seed)

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

                # Start per-session threads
                self._disconnected.clear()
                self._session_stop.clear()
                threads = [
                    threading.Thread(target=self._receiver_thread, name="ws-recv", daemon=True),
                    threading.Thread(target=self._sender_thread, name="pipe-send", daemon=True),
                    threading.Thread(target=self._log_thread, name="log-tail", daemon=True),
                ]
                for t in threads:
                    t.start()

                logger.info("Bridge running. Press Ctrl+C to stop.")
                # Wake on disconnect (set by the receiver thread) or Ctrl+C.
                while self.running and not self._disconnected.is_set():
                    self._disconnected.wait(timeout=0.5)

            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                logger.error(f"Session error: {e}")
            finally:
                # Tear the session down completely before reconnecting so
                # the next session never runs two tailers or two senders.
                self._session_stop.set()
                self.ws.close()
                for t in threads:
                    t.join(timeout=5)

            if self.running:
                logger.warning("Connection lost. Reconnecting in 5s...")
                time.sleep(5)

        logger.info("Bridge stopped.")

    # ---- Thread 1: WebSocket receiver ----
    def _receiver_thread(self):
        """Reads WebSocket messages, puts items in queue.

        Socket-level failures end the session (main loop reconnects).
        A bad packet is logged and skipped — one malformed message must
        not kill the connection.
        """
        logger.info("[recv] Receiver thread started")
        while self.running and not self._session_stop.is_set():
            try:
                raw = self.ws.recv()
            except Exception as e:
                if self.running and not self._session_stop.is_set():
                    logger.error(f"[recv] Connection lost: {e}")
                break

            try:
                packets = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"[recv] Malformed message skipped: {e}")
                continue
            if not isinstance(packets, list):
                packets = [packets]

            for packet in packets:
                try:
                    self._handle_packet(packet)
                except Exception as e:
                    logger.error(
                        f"[recv] Error handling {packet.get('cmd', '?')} packet: {e}",
                        exc_info=True,
                    )

        # Signal the main loop that this session is over.
        self._disconnected.set()
        logger.info("[recv] Receiver thread ended")

    def _set_state_file(self, seed: str):
        """Bind the state file to this seed+slot and load it.

        Called on RoomInfo. Keying by seed and slot means state from an
        old multiworld can never leak checks/items into a new one.
        """
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", f"{seed}_{self.slot}") or "default"
        path = self.stellaris_dir / f"ap_bridge_state_{safe}.json"
        if path == self._state_file:
            return  # reconnect to the same room — state already loaded
        self._state_file = path
        self.sent_checks = set()
        self.processed_indices = set()
        self._pending_indices = set()
        self._goal_sent = False
        self._load_state()

    def _load_state(self):
        """Load persisted checks/items from disk."""
        try:
            if self._state_file and self._state_file.exists():
                data = json.loads(self._state_file.read_text())
                self.sent_checks = set(data.get("sent_checks", []))
                self.processed_indices = set(data.get("processed_indices", []))
                logger.info(f"Loaded state: {len(self.sent_checks)} checks, {len(self.processed_indices)} items")
        except Exception as e:
            logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        """Persist checks/items to disk (thread-safe, atomic write)."""
        if not self._state_file:
            return
        try:
            with self._state_lock:
                data = {
                    "sent_checks": sorted(self.sent_checks),
                    "processed_indices": sorted(self.processed_indices),
                }
                tmp = self._state_file.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(data))
                tmp.replace(self._state_file)
        except Exception as e:
            logger.warning(f"Could not save state: {e}")

    @property
    def energylink_key(self) -> str:
        return f"EnergyLink{self.team}"

    def _handle_packet(self, packet: dict):
        cmd = packet.get("cmd", "")

        if cmd == "ConnectionRefused":
            errors = packet.get("errors", [])
            logger.error("=" * 60)
            logger.error(f"SERVER REFUSED CONNECTION: {', '.join(errors) or 'unknown error'}")
            hints = {
                "InvalidSlot": f"No slot named '{self.slot}' in this multiworld — check --slot.",
                "InvalidGame": "This slot is not a Stellaris slot.",
                "InvalidPassword": "Wrong room password — check --password.",
                "IncompatibleVersion": "Client/server version mismatch.",
            }
            for err in errors:
                if err in hints:
                    logger.error(f"  {hints[err]}")
            logger.error("=" * 60)
            # Retrying with the same credentials cannot succeed — stop.
            self.running = False
            self._disconnected.set()

        elif cmd == "Connected":
            self.player_id = packet.get("slot", 0)
            self.team = packet.get("team", 0)
            checked = set(packet.get("checked_locations", []))
            self.sent_checks.update(checked)
            self.all_locations = packet.get("missing_locations", []) + list(checked)

            # Read slot_data for goal + EnergyLink config
            slot_data = packet.get("slot_data", {}) or {}
            self.goal = int(slot_data.get("goal", 0))
            self.energy_link_enabled = bool(slot_data.get("energy_link_enabled", False))
            self.energy_link_rate = max(1, int(slot_data.get("energy_link_rate", 100)))

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
            logger.info(f"Goal: {self.goal} | EnergyLink: {self.energy_link_enabled} "
                        f"(rate {self.energy_link_rate} EC/unit)")
            logger.info(f"Randomized techs: {len(self.randomized_techs)} "
                        f"({len(catalog_loc_ids)} catalog Research-X locations)")

            # Persistent per-save state. Delivered (and re-delivered on
            # every new game session) by the sender thread.
            self._set_state_effects(selected)

            # Re-send any checks we have locally that the server doesn't know about
            unsent = self.sent_checks - checked
            if unsent:
                logger.info(f"Re-sending {len(unsent)} locally-stored checks...")
                self.ws.send(json.dumps([{
                    "cmd": "LocationChecks",
                    "locations": sorted(unsent),
                }]))
            self._check_all_checks_goal()

            if self.energy_link_enabled:
                # Subscribe to EnergyLink updates and fetch the current pool
                self.ws.send(json.dumps([{
                    "cmd": "SetNotify", "keys": [self.energylink_key]
                }]))
                self.ws.send(json.dumps([{
                    "cmd": "Get", "keys": [self.energylink_key]
                }]))
                logger.info(f"EnergyLink: subscribed to {self.energylink_key}")

            # Request the DataPackage — only for games present in this
            # room; the full package can be tens of MB on big servers.
            req = {"cmd": "GetDataPackage"}
            if self.room_games:
                req["games"] = self.room_games
            self.ws.send(json.dumps([req]))

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
                # processed = delivered to the game; pending = queued for
                # the pipe. An index is only persisted as processed after
                # the pipe write succeeds, so items received while
                # Stellaris is closed are retried instead of lost.
                if idx in self.processed_indices or idx in self._pending_indices:
                    continue
                self._pending_indices.add(idx)
                item_id = item.get("item", 0)
                sender = item.get("player", 0)
                name = self.item_names.get(item_id, f"Item #{item_id}")
                sender_name = self.player_names.get(sender, f"Player {sender}")
                logger.info(f"  <- RECEIVED: {name} (from {sender_name})")
                self.item_queue.put(("item", idx, item_id))

        elif cmd == "PrintJSON":
            parts = packet.get("data", [])
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
            if text:
                logger.info(f"  [chat] {text}")

        elif cmd == "SetReply":
            key = packet.get("key", "")
            if key.startswith("EnergyLink"):
                current = int(packet.get("value", 0) or 0)
                original = int(packet.get("original_value", current) or 0)
                self.energy_link_value = current
                # SetReply is broadcast to every SetNotify subscriber, so
                # this fires for *other* games' deposits/withdrawals too.
                # Our own Set requests echo our slot back (extra fields on
                # Set are returned verbatim); only grant energy for those.
                is_ours = packet.get("slot") == self.player_id
                gained = original - current
                if gained > 0 and is_ours:
                    ec = gained * self.energy_link_rate
                    logger.info(f"  [energy] EnergyLink: withdrew {gained} unit(s) = {ec} EC (pool: {current})")
                    self._grant_energy(ec)
                elif is_ours:
                    logger.info(f"  [energy] EnergyLink: pool was empty, nothing withdrawn (pool: {current})")
                elif gained > 0:
                    logger.info(f"  [energy] EnergyLink: another game withdrew {gained} unit(s) (pool: {current})")
                elif original < current:
                    logger.info(f"  [energy] EnergyLink: deposit confirmed (pool: {current})")

        elif cmd == "Retrieved":
            keys = packet.get("keys", {})
            for key, value in keys.items():
                if key.startswith("EnergyLink"):
                    self.energy_link_value = int(value) if value else 0
                    logger.info(f"  [energy] EnergyLink pool: {self.energy_link_value} unit(s)")

    # ---- Persistent save-state flags ----
    def _set_state_effects(self, selected: Set[str]):
        """Compute the country flags every save of this seed must carry
        and schedule their delivery."""
        effects = []
        for g in range(5):
            if g == self.goal:
                effects.append(f"set_country_flag = ap_goal_{g}")
            else:
                effects.append(f"remove_country_flag = ap_goal_{g}")
        if self.energy_link_enabled:
            effects.append("set_country_flag = ap_energy_link")
        else:
            effects.append("remove_country_flag = ap_energy_link")
        # Hide randomized vanilla techs (read by 00_aaa_ap_tech_blocks.txt).
        effects += [f"set_country_flag = {f}" for f in _catalog_block_flags_for(selected)]
        self._state_effects = effects
        self._resync_needed.set()

    def _generate_dynamic_techs(self, scouted_locations: list):
        """Build slot data from scouted locations and generate mod files."""
        # AP flags -> classification
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

        if not (self.mod_dir / "descriptor.mod").exists():
            logger.error(
                f"Mod not installed at {self.mod_dir} — generating AP techs "
                "anyway, but Stellaris won't see them until you run "
                "'python setup.py install' and enable the mod in the launcher.")

        # Generate mod files
        from slot_generator import generate_mod_files, clear_dynamic_files
        clear_dynamic_files(self.mod_dir)

        tech_count = sum(1 for s in slot_data if s["location_type"] == "tech")
        milestone_count = sum(1 for s in slot_data if s["location_type"] == "milestone")

        blocked_techs = generate_mod_files(slot_data, self.mod_dir)
        # generate_mod_files returns a list of blocked tech keys on
        # success (possibly empty) and None on failure.
        if isinstance(blocked_techs, list):
            logger.info(f"Generated {tech_count} AP techs ({milestone_count} milestones auto-detected)")
            logger.info(f"Blocking {len(blocked_techs)} vanilla techs (sent to other worlds)")

            # The blocking flags are part of the persistent save state;
            # make sure anything the generator found is included.
            extra = set(blocked_techs) - set(self.randomized_techs)
            if extra:
                logger.warning(f"Generator blocked {len(extra)} techs missing from slot_data: {sorted(extra)[:5]}")
                self.randomized_techs = sorted(set(self.randomized_techs) | extra)
                self._set_state_effects(set(self.randomized_techs))

            logger.info("")
            logger.info("=" * 60)
            logger.info("DYNAMIC TECHS GENERATED!")
            logger.info("If Stellaris is already running, restart it so the AP techs")
            logger.info("appear in-game. Keep this bridge running: once you load a")
            logger.info("save and the mod reports in, it syncs flags and delivers items.")
            logger.info("=" * 60)
            logger.info("")
        else:
            logger.error("Failed to generate dynamic tech files!")

    # ---- Thread 2: Pipe sender ----
    def _sender_thread(self):
        """Takes items from queue, batches them, sends to DLL pipe.

        Nothing is sent until the mod has reported in for the current
        game process (see module docstring). A batch that can't be
        delivered (Stellaris closed, DLL not loaded) is kept and
        retried — item indices only become "processed" (and are
        persisted) after a successful pipe write.
        """
        logger.info("[send] Sender thread started")
        pending: list = []  # undelivered (kind, ...) messages carried over
        retry_count = 0
        waiting_logged = False

        while self.running and not self._session_stop.is_set():
            # Collect new messages; block briefly only if nothing is pending.
            try:
                pending.append(self.item_queue.get(timeout=1 if not pending else 0.01))
            except queue.Empty:
                pass
            while not self.item_queue.empty():
                try:
                    pending.append(self.item_queue.get_nowait())
                except queue.Empty:
                    break

            if not self._game_active.is_set():
                if (pending or self._resync_needed.is_set()) and not waiting_logged:
                    logger.info(
                        f"[send] {len(pending)} item(s)/effect(s) queued — waiting for "
                        "Stellaris to report in (load a save with the mod enabled "
                        "and unpause; the mod checks in at the next monthly tick)")
                    waiting_logged = True
                continue
            waiting_logged = False

            # Persistent flags first, so a fresh save is configured
            # before any item lands in it.
            if self._resync_needed.is_set():
                self._resync_needed.clear()
                if self._send_batch_to_pipe(self._state_effects, quiet=True):
                    logger.info(f"[send] Save state synced ({len(self._state_effects)} flag(s))")
                else:
                    self._resync_needed.set()
                    if retry_count % 12 == 0:
                        logger.warning("  -> PIPE unavailable for state sync, retrying every 5s "
                                       "(is Stellaris running with version.dll?)")
                    retry_count += 1
                    self._session_stop.wait(timeout=5)
                    continue

            if not pending:
                continue

            # Convert to effect commands
            effects = []
            delivered_indices = []
            for msg in pending:
                if isinstance(msg, tuple) and msg[0] == "raw_effect":
                    effects.append(msg[1])
                elif isinstance(msg, tuple) and msg[0] == "item":
                    _, idx, item_id = msg
                    delivered_indices.append(idx)
                    effect = ITEM_EFFECT_MAP.get(item_id)
                    if effect:
                        effects.append(f"{effect} = yes")
                    else:
                        logger.warning(f"  -> Unknown item id {item_id}; setting flag ap_item_{item_id}")
                        effects.append(f"set_country_flag = ap_item_{item_id}")

            if self._send_batch_to_pipe(effects):
                for idx in delivered_indices:
                    self._pending_indices.discard(idx)
                    self.processed_indices.add(idx)
                if delivered_indices:
                    self._save_state()
                pending = []
                retry_count = 0
            else:
                # Keep the batch; log the first failure loudly, then
                # once a minute so a closed game doesn't spam the log.
                if retry_count % 12 == 0:
                    logger.warning(
                        f"  -> PIPE unavailable: {len(effects)} effect(s) queued, "
                        f"retrying every 5s (is Stellaris running?)")
                retry_count += 1
                self._session_stop.wait(timeout=5)

        # Undelivered items go back to "unqueued" so the server's resend
        # on reconnect re-queues them instead of being deduped away.
        for msg in pending:
            if isinstance(msg, tuple) and msg[0] == "item":
                self._pending_indices.discard(msg[1])
        logger.info("[send] Sender thread ended")

    def _send_batch_to_pipe(self, effects: list, quiet: bool = False) -> bool:
        """Send a batch of effects in a single pipe connection.

        Returns True only if every effect was written to the pipe.
        """
        if not effects:
            return True
        if sys.platform != "win32":
            for e in effects:
                logger.warning(f"  -> NO PIPE (non-Windows): {e}")
            return True  # nothing to deliver to on this platform

        from pipe_client import create_pipe_client
        pipe = create_pipe_client()
        if not pipe.connect():
            return False
        try:
            if not self._dll_status_logged:
                self._log_dll_status(pipe.status())
            for effect_cmd in effects:
                if not pipe.send_effect(effect_cmd):
                    logger.warning(f"  -> PIPE: write failed at '{effect_cmd}', will retry batch")
                    return False
            flushed = pipe.flush_commands()
            if flushed < 0:
                # Queued in the DLL but not executed yet (game thread busy
                # or window not hooked). The DLL's timer drains it; count
                # the batch as delivered.
                logger.info(f"  -> PIPE: {len(effects)} effect(s) queued in DLL (deferred execution)")
            else:
                logger.info(f"  -> PIPE: {len(effects)} effect(s) sent, {flushed} flushed")
            if not quiet:
                for e in effects:
                    logger.info(f"    {e}")
            return True
        finally:
            pipe.disconnect()

    def _log_dll_status(self, status):
        """Tell the player which delivery mode the DLL ended up in."""
        self._dll_status_logged = True
        if not status:
            logger.warning("  -> DLL did not answer STATUS (old build?) — delivery may still work")
            return
        mode = status.get("mode")
        summary = " ".join(f"{k}={v}" for k, v in status.items())
        if mode == "phase2":
            logger.info(f"  -> DLL: direct engine calls active ({summary})")
        elif mode == "phase1":
            logger.warning(f"  -> DLL: engine patterns did not match this Stellaris build; "
                           f"using the SendInput fallback, which types into the game console "
                           f"({summary}). Items still arrive but the game window may flicker. "
                           f"A DLL update for this game version is needed.")
        else:
            logger.warning(f"  -> DLL: console not ready ({summary}); check archipelago_dll.log "
                           f"next to stellaris.exe")

    def _on_game_log_reset(self):
        self._dll_status_logged = False
        self._on_game_log_reset_impl()

    def _grant_energy(self, amount: int):
        """Grant energy credits in-game from EnergyLink withdrawal."""
        self.item_queue.put(("raw_effect", f"add_resource = {{ energy = {amount} }}"))

    # ---- Thread 3: Log tailer ----
    # Only lines the mod writes count. The prefix must stand alone —
    # engine lines like "MAP_..." must never be mistaken for the mod.
    RE_AP_LINE = re.compile(
        rb"(?<![A-Za-z0-9_])AP_(?:CHECK|GOAL_COMPLETE|ENERGY_DEPOSIT|"
        rb"ENERGY_WITHDRAW|HEARTBEAT|CONNECTED|DEBUG)(?![A-Za-z0-9])")
    RE_CHECK = re.compile(r"(?<![A-Za-z0-9_])AP_CHECK\|(\d+)\|(.+)")
    RE_GOAL = re.compile(r"(?<![A-Za-z0-9_])AP_GOAL_COMPLETE")
    RE_DEPOSIT = re.compile(r"(?<![A-Za-z0-9_])AP_ENERGY_DEPOSIT\|(\d+)")
    RE_WITHDRAW = re.compile(r"(?<![A-Za-z0-9_])AP_ENERGY_WITHDRAW\|(\d+)")

    @staticmethod
    def _file_identity(st):
        # On Windows st_ctime is the creation time (st_birthtime from 3.12).
        return (getattr(st, "st_birthtime", st.st_ctime), st.st_ino)

    def _on_game_log_reset_impl(self):
        """game.log was recreated: Stellaris was restarted."""
        if self._game_active.is_set():
            logger.info("[log] game.log reset — Stellaris restarted; waiting for the mod to report in")
        self._game_active.clear()

    def _mark_game_active(self):
        """The mod wrote something: a save with the mod is loaded."""
        if not self._game_active.is_set():
            self._game_active.set()
            self._resync_needed.set()
            logger.info("[log] Stellaris is in-game (mod reported in) — syncing flags and delivering items")

    def _log_thread(self):
        """Polls game.log for AP_* lines written by the mod."""
        logger.info(f"[log] Tailer started: {self.log_path}")

        while self.running and not self._session_stop.is_set():
            try:
                if not self.log_path.exists():
                    if self._log_pos is None:
                        self._log_pos = 0
                    self._session_stop.wait(timeout=1)
                    continue

                st = self.log_path.stat()
                ident = self._file_identity(st)
                if self._log_pos is None:
                    # First look: skip whatever an earlier campaign logged.
                    self._log_pos = st.st_size
                    self._log_ident = ident
                elif st.st_size < self._log_pos or ident != self._log_ident:
                    self._log_pos = 0
                    self._log_ident = ident
                    self._on_game_log_reset()

                if st.st_size <= self._log_pos:
                    self._session_stop.wait(timeout=0.5)
                    continue

                with open(self.log_path, "rb") as f:
                    f.seek(self._log_pos)
                    while self.running and not self._session_stop.is_set():
                        raw = f.readline()
                        if not raw or not raw.endswith(b"\n"):
                            break  # EOF, or a line Stellaris is still writing
                        if self.RE_AP_LINE.search(raw):
                            line = raw.decode("utf-8", errors="replace")
                            # Handled before advancing: if a send raises,
                            # the line is re-read after reconnect.
                            self._handle_log_line(line)
                        self._log_pos += len(raw)

            except Exception as e:
                logger.error(f"[log] Error: {e}")
                self._session_stop.wait(timeout=1)

        logger.info("[log] Tailer ended")

    def _handle_log_line(self, line: str):
        self._mark_game_active()

        m = self.RE_CHECK.search(line)
        if m:
            loc_id = int(m.group(1))
            loc_name = m.group(2).strip()
            if loc_id not in self.sent_checks:
                logger.info(f"  -> CHECK: {loc_name} (ID={loc_id})")
                self._send_checks([loc_id])
                self._check_all_checks_goal()
            return

        if self.RE_GOAL.search(line):
            self._send_goal_complete()
            return

        md = self.RE_DEPOSIT.search(line)
        if md:
            self._energy_deposit(int(md.group(1)))
            return

        mw = self.RE_WITHDRAW.search(line)
        if mw:
            self._energy_withdraw(int(mw.group(1)))
            return

    def _send_checks(self, loc_ids: List[int]):
        """Send location checks; record them only once the send succeeded."""
        self.ws.send(json.dumps([{
            "cmd": "LocationChecks",
            "locations": list(loc_ids),
        }]))
        self.sent_checks.update(loc_ids)
        self._save_state()

    def _send_goal_complete(self):
        if self._goal_sent:
            return
        logger.info("  [goal] GOAL COMPLETE!")
        self.ws.send(json.dumps([{"cmd": "StatusUpdate", "status": CLIENT_GOAL}]))
        self._goal_sent = True

    def _check_all_checks_goal(self):
        """Goal 4 (All Checks): the mod can't know the location pool, so the
        bridge decides. Once every location except Victory is checked, the
        bridge sends Victory itself and reports the goal."""
        if self.goal != GOAL_ALL_CHECKS or not self.all_locations or self._goal_sent:
            return
        required = set(self.all_locations) - {VICTORY_LOCATION_ID}
        if not required.issubset(self.sent_checks):
            return
        logger.info("  [goal] ALL CHECKS COMPLETE — goal satisfied!")
        if VICTORY_LOCATION_ID in self.all_locations and VICTORY_LOCATION_ID not in self.sent_checks:
            self._send_checks([VICTORY_LOCATION_ID])
        self._send_goal_complete()

    def _energy_deposit(self, amount_ec: int):
        if not self.energy_link_enabled:
            logger.warning(f"  [energy] EnergyLink is disabled for this slot — refunding {amount_ec} EC")
            self._grant_energy(amount_ec)
            return
        units = amount_ec // self.energy_link_rate
        if units <= 0:
            logger.warning(f"  [energy] Deposit of {amount_ec} EC is below one unit "
                           f"({self.energy_link_rate} EC) — refunding")
            self._grant_energy(amount_ec)
            return
        logger.info(f"  [energy] EnergyLink deposit: {amount_ec} EC = {units} unit(s)")
        self.ws.send(json.dumps([{
            "cmd": "Set",
            "key": self.energylink_key,
            "default": 0,
            "want_reply": False,
            "operations": [{"operation": "add", "value": units}],
        }]))

    def _energy_withdraw(self, amount_ec: int):
        if not self.energy_link_enabled:
            logger.warning("  [energy] EnergyLink is disabled for this slot — withdraw ignored")
            return
        # Always ask the server: the "max 0" operation below clamps the
        # pool at zero, and the SetReply reports how much was actually
        # taken. Our cached pool value is only a hint (it can be stale).
        pool = self.energy_link_value
        withdraw = max(1, math.ceil(amount_ec / self.energy_link_rate))
        logger.info(f"  [energy] EnergyLink withdraw: requesting {withdraw} unit(s) "
                    f"= {withdraw * self.energy_link_rate} EC "
                    f"(pool: {'unknown' if pool is None else pool})")
        self.ws.send(json.dumps([{
            "cmd": "Set",
            "key": self.energylink_key,
            "default": 0,
            "want_reply": True,
            # Echoed back in SetReply so we can tell our own withdrawal
            # apart from other games'.
            "slot": self.player_id,
            "operations": [
                {"operation": "add", "value": -withdraw},
                {"operation": "max", "value": 0},
            ],
        }]))


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
