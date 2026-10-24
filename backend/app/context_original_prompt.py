"""Select the effective prompt for an explicitly approved original-settings turn.

The saved prompt is authoritative only after the caller has verified ownership and
that the saved tool configuration is in effect. This helper performs no I/O.
"""


def effective_prompt_for_turn(current_prompt: str, saved_prompt: str | None, *,
                              continue_original: bool) -> str:
    if not continue_original:
        return current_prompt
    if not isinstance(saved_prompt, str) or not saved_prompt.strip():
        raise ValueError("Original conversation has no saved effective system prompt")
    return saved_prompt
