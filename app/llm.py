# ============================================================================
# llm.py — call Google Gemini to turn a prompt into an answer.
#
# This is the ONLY file that talks to Gemini. Everything else just calls
# generate_answer(prompt) and gets back a string.
#
# It uses key_manager to pick an API key, and if that key is rate-limited it
# marks it as cooling down and tries the next key. If all keys are cooling
# down, it raises a friendly error the API layer can show to the user.
# ============================================================================

# The official Google Gemini library.
import google.generativeai as genai

from app.key_manager import key_manager, AllKeysCoolingDown


# Which Gemini model to use. "gemini-flash-latest" is an alias that always
# points to the current stable, fast, free-tier-friendly "flash" model — so it
# keeps working even when Google renames specific versions.
MODEL_NAME = "gemini-flash-latest"

# A friendly message shown when every key is temporarily rate-limited.
ALL_KEYS_BUSY_MESSAGE = "All AI keys are cooling down, please try again in a minute."


def _looks_like_rate_limit(error: Exception) -> bool:
    """
    Decide whether an error from Gemini is a rate-limit / quota problem.

    Gemini signals these with things like HTTP 429 or the words "quota" /
    "rate limit" in the message. We check the text in a simple, robust way.
    """
    message = str(error).lower()
    return (
        "429" in message
        or "quota" in message
        or "rate limit" in message
        or "resource has been exhausted" in message
    )


def generate_answer(prompt: str) -> str:
    """
    Send `prompt` to Gemini and return the generated answer text.

    Tries each available key once. If a key is rate-limited, it's put on
    cooldown and we try the next one. If none are available, we return the
    friendly "try again in a minute" message.
    """
    # Try at most as many times as we have keys (each key once per request).
    number_of_keys = len(key_manager.keys)

    for _attempt in range(number_of_keys):
        # 1) Get a key that isn't cooling down. If none, tell the user nicely.
        try:
            api_key = key_manager.get_key()
        except AllKeysCoolingDown:
            return ALL_KEYS_BUSY_MESSAGE

        # 2) Try to generate the answer with this key.
        try:
            genai.configure(api_key=api_key)                 # use this key
            model = genai.GenerativeModel(MODEL_NAME)         # pick the model
            response = model.generate_content(prompt)         # send the prompt
            return response.text                              # success! return answer

        except Exception as error:
            # 3) If it's a rate-limit error, cool this key down and loop to the
            #    next key. Any other error we re-raise (it's a real problem).
            if _looks_like_rate_limit(error):
                key_manager.mark_rate_limited(api_key)
                continue  # try the next key
            raise  # not a rate-limit issue — let it surface

    # If the loop finished without returning, every key got rate-limited.
    return ALL_KEYS_BUSY_MESSAGE
