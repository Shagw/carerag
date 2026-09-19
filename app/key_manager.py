# ============================================================================
# key_manager.py — hand out Gemini API keys and rotate them when rate-limited.
#
# WHY: Gemini's free tier limits how many requests a single key can make in a
# short time. If we have several keys, we can switch to another when one gets
# rate-limited, so the app keeps working.
#
# HOW IT WORKS:
#   - We keep a pool of keys (from your .env, via settings.gemini_api_keys).
#   - get_key() returns a key that is NOT currently "cooling down".
#   - When a request fails with a rate-limit error, we call mark_rate_limited(key)
#     which puts that key on a cooldown timer.
#   - If EVERY key is cooling down, get_key() raises AllKeysCoolingDown, and the
#     API turns that into the friendly "try again in a minute" message.
# ============================================================================

import time
from typing import Dict, List

from app.config import settings


# How long (in seconds) a key stays on cooldown after being rate-limited.
COOLDOWN_SECONDS = 60


class AllKeysCoolingDown(Exception):
    """Raised when every API key is currently cooling down (all rate-limited)."""
    pass


class KeyManager:
    """
    Manages the pool of Gemini API keys and their cooldown state.

    We create ONE shared instance at the bottom of this file, so the whole app
    shares the same cooldown memory.
    """

    def __init__(self, keys: List[str]):
        # The list of API keys we were given (1 to 5 of them).
        self.keys = keys

        # Remembers when each key is "cooling down UNTIL" (a future timestamp).
        # If a key isn't in here, it's available. Example: {"AIza...": 1699999999.0}
        self.cooldown_until: Dict[str, float] = {}

        # If no keys were configured at all, fail early with a clear message.
        if not self.keys:
            raise ValueError(
                "No Gemini API keys found. Please set GEMINI_API_KEY_1 in your .env file."
            )

    def get_key(self) -> str:
        """
        Return the first key that is not currently cooling down.

        Raises AllKeysCoolingDown if every key is on cooldown right now.
        """
        now = time.time()  # current time in seconds

        for key in self.keys:
            # When is this key cooling down until? (0.0 means "never / available".)
            cooling_until = self.cooldown_until.get(key, 0.0)

            # If the cooldown time has passed (or never set), the key is usable.
            if now >= cooling_until:
                return key

        # If we get here, no key was available.
        raise AllKeysCoolingDown()

    def mark_rate_limited(self, key: str) -> None:
        """
        Put a key on cooldown because it just hit a rate limit.
        It won't be handed out again until COOLDOWN_SECONDS have passed.
        """
        self.cooldown_until[key] = time.time() + COOLDOWN_SECONDS


# One shared KeyManager for the whole app, built from the keys in your .env.
key_manager = KeyManager(settings.gemini_api_keys)
