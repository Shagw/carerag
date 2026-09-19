# ============================================================================
# config.py — ONE place that reads all of the app's settings.
#
# Every other file imports the ready-made `settings` object from here:
#       from app.config import settings
#       settings.database_url        # the Supabase connection string
#       settings.gemini_api_keys     # a list of the keys you provided
#
# The values come from your .env file (or the real environment when deployed).
# This file NEVER contains real secrets — it only reads them.
# ============================================================================

# "List" is a type hint meaning "a list of things" (here, a list of strings).
from typing import List

# pydantic-settings gives us BaseSettings: a class that automatically reads
# its fields from environment variables / the .env file, and checks their types.
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Describes every setting the app expects.

    For each field below, pydantic-settings looks for an environment variable
    with the SAME NAME (case-insensitive). So the field `database_url` is filled
    from the DATABASE_URL entry in your .env file.
    """

    # --- Database ----------------------------------------------------------
    # The Supabase Postgres connection string (from DATABASE_URL in .env).
    database_url: str

    # --- Gemini API keys ---------------------------------------------------
    # We accept up to 5 separate keys. Each one is OPTIONAL (default ""),
    # because you might only have 1 or 2. We combine them into a clean list
    # further below, in `gemini_api_keys`.
    gemini_api_key_1: str = ""
    gemini_api_key_2: str = ""
    gemini_api_key_3: str = ""
    gemini_api_key_4: str = ""
    gemini_api_key_5: str = ""

    # --- Tuning knobs (have safe defaults, so .env can leave them out) ------
    # How many top matching chunks to retrieve for each question.
    top_k: int = 5

    # Strict "I don't know" cutoff. If the closest chunk's cosine distance is
    # bigger than this, we assume the answer isn't in the documents.
    # Calibrated from real data: relevant matches were ~0.34-0.47, off-topic
    # much higher, so 0.8 accepts genuine answers while rejecting unrelated ones.
    similarity_threshold: float = 0.8

    # Where the FastAPI backend runs (used by the Streamlit UI to call it).
    api_base_url: str = "http://localhost:8000"

    # This tells pydantic-settings to also read from a file named ".env",
    # and to ignore any extra variables it doesn't recognize.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def gemini_api_keys(self) -> List[str]:
        """
        Return the API keys you actually filled in, as a simple list.

        A @property lets us call `settings.gemini_api_keys` like it's a normal
        attribute, but it runs this little bit of code to build the list.

        We collect the 5 numbered keys, then drop any that are empty/blank so
        the list only contains real keys. Example result: ["AIza...", "AIza..."]
        """
        # Put all five in a list (some may be empty strings).
        all_keys = [
            self.gemini_api_key_1,
            self.gemini_api_key_2,
            self.gemini_api_key_3,
            self.gemini_api_key_4,
            self.gemini_api_key_5,
        ]
        # Keep only the non-empty ones. `key.strip()` removes stray spaces;
        # `if key.strip()` is False for "" (empty), so blanks are skipped.
        return [key.strip() for key in all_keys if key.strip()]


# Create ONE shared settings object when this file is first imported.
# Other files import THIS object, so the .env is read only once.
settings = Settings()
