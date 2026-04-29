r"""Named pipe client for communicating with the Stellaris DLL bridge.

Connects to \\.\pipe\stellaris_archipelago and sends effect commands
that the DLL executes on the game's main thread.

This replaces save-file injection as the inbound (client → game) channel.
The outbound channel (game → client) still uses log file tailing.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger("StellarisClient")

# Windows named pipe path
PIPE_NAME = r"\\.\pipe\stellaris_archipelago"

# Only import win32 APIs on Windows
try:
    import win32file
    import win32pipe
    import pywintypes
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class PipeClient:
    """Client for the DLL bridge named pipe."""

    def __init__(self):
        self.handle = None
        self.connected = False
        self._last_attempt = 0.0
        self._retry_interval = 2.0  # seconds between connection attempts

    def connect(self) -> bool:
        """Try to connect to the DLL bridge pipe. Returns True on success."""
        if not HAS_WIN32:
            logger.warning("pywin32 not installed — pipe client disabled.")
            logger.warning("Install it with: pip install pywin32")
            return False

        if self.connected:
            return True

        now = time.time()
        if now - self._last_attempt < self._retry_interval:
            return False
        self._last_attempt = now

        try:
            self.handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None,
            )
            self.connected = True
            logger.info("🔌 Connected to DLL bridge pipe!")
            return True
        except pywintypes.error as e:
            # Pipe doesn't exist yet — DLL not loaded
            if e.winerror == 2:  # ERROR_FILE_NOT_FOUND
                pass  # silent, will retry
            elif e.winerror == 231:  # ERROR_PIPE_BUSY
                logger.debug("Pipe busy, will retry...")
            else:
                logger.warning(f"Pipe connection failed: {e}")
            return False

    def disconnect(self):
        """Close the pipe connection."""
        if self.handle:
            try:
                win32file.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
        self.connected = False

    def send_command(self, command: str) -> Optional[str]:
        """Send a command and return the response. Returns None on failure."""
        if not self.connected:
            if not self.connect():
                return None

        try:
            # Send
            message = command + "\n"
            win32file.WriteFile(self.handle, message.encode("utf-8"))

            # Read response
            result, data = win32file.ReadFile(self.handle, 4096)
            response = data.decode("utf-8").strip()
            return response

        except pywintypes.error as e:
            logger.warning(f"Pipe communication error: {e}")
            self.disconnect()
            return None

    def send_effect(self, effect: str) -> bool:
        """Send a single effect command. Returns True on success."""
        response = self.send_command(f"EFFECT {effect}")
        if response and response.startswith("OK"):
            return True
        if response:
            logger.warning(f"Effect command failed: {response}")
        return False

    def send_batch(self, effects: list) -> bool:
        """Send multiple effect commands as a batch. Returns True on success."""
        if not effects:
            return True
        batch = "|".join(effects)
        response = self.send_command(f"BATCH {batch}")
        if response and response.startswith("OK"):
            return True
        if response:
            logger.warning(f"Batch command failed: {response}")
        return False

    def ping(self) -> Optional[str]:
        """Check if the bridge is alive. Returns status string or None."""
        return self.send_command("PING")

    def set_flag(self, flag_name: str) -> bool:
        """Set a country flag on the player's empire."""
        return self.send_effect(f"set_country_flag = {flag_name}")

    def grant_resources(self, resources: dict) -> bool:
        """Grant resources to the player. e.g. {"energy": 500, "minerals": 300}"""
        parts = " ".join(f"{k} = {v}" for k, v in resources.items())
        return self.send_effect(f"add_resource = {{ {parts} }}")

    def fire_event(self, event_id: str) -> bool:
        """Fire a country event on the player."""
        return self.send_effect(f"country_event = {{ id = {event_id} }}")

    def flush_commands(self) -> int:
        """Tell the DLL to execute all queued commands now."""
        response = self.send_command("FLUSH")
        if response and response.startswith("OK FLUSHED"):
            try: return int(response.split()[-1])
            except (ValueError, IndexError): return 0
        return -1


class FallbackPipeClient:
    """No-op pipe client for when pywin32 is not available or on non-Windows."""

    def __init__(self):
        self.connected = False
        self._warned = False

    def connect(self) -> bool:
        if not self._warned:
            logger.info("DLL bridge not available (non-Windows or pywin32 missing)")
            logger.info("Items cannot be received — outbound checks still work via log tailing")
            self._warned = True
        return False

    def disconnect(self):
        pass

    def send_effect(self, effect: str) -> bool:
        return False

    def send_batch(self, effects: list) -> bool:
        return False

    def ping(self):
        return None

    def set_flag(self, flag_name: str) -> bool:
        return False

    def grant_resources(self, resources: dict) -> bool:
        return False

    def fire_event(self, event_id: str) -> bool:
        return False

    def flush_commands(self) -> int:
        return -1


def create_pipe_client():
    """Create the appropriate pipe client for this platform."""
    if HAS_WIN32:
        return PipeClient()
    return FallbackPipeClient()
