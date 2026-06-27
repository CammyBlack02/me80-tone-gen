"""LLM layer — text description → SemanticPatch via Ollama structured output.

The model only sees type *names* (not raw indices), and Ollama's JSON-schema
constraint guarantees the model can't emit an invalid amp/effect type. We still
re-validate after parsing — structural validity ≠ musical sensibility.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from .schema import SemanticPatch

DEFAULT_MODEL = "qwen2.5:14b"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_RETRIES = 2


SYSTEM_PROMPT = """\
You are a Boss ME-80 patch designer. Convert a natural-language tone description
into a single ME-80 patch as JSON matching the supplied schema.

Hard constraints:
- Choose ONLY from the legal type names supplied in the schema's enum fields.
- Knob values are integers 0-99. 0 = minimum, 99 = maximum (50 is mid).
- The ME-80's signal chain (fixed): PEDAL FX → COMP/FX1 → OD/DS → PREAMP → MOD → EQ/FX2 → DELAY → REVERB.
- Preamp is always on (enabled=true).
- patch_name: max 16 ASCII chars, uppercase, descriptive (e.g. "BLUES LEAD", "PUPPETS RHYTHM").

How to use each block:
- For every block, set `enabled` to true if it serves the tone, false otherwise.
- When enabled=false, still pick a sensible default `type` and knob values — they
  won't affect the sound but the schema requires complete values.
- When enabled=true, choose knob values DECIDEDLY. Do not leave knobs at 50
  unless 50 is genuinely correct for that knob in that tone. A flat patch where
  everything sits at 50 is almost never the answer. Use the full 0-99 range.
- If the description names a specific effect (e.g. "spring reverb", "tape echo",
  "chorus"), the matching block MUST be enabled with the matching type.

Taste guidelines:
- High-gain metal: METAL preamp, often T-SCREAM in front to tighten lows,
  scooped mids (middle ~30-40), bass and treble pushed.
- Bluesy lead: CRUNCH or LEAD preamp, gentle OVERDRIVE or no OD, midrange
  forward (middle ~60), ROOM or SPRING reverb at moderate level.
- Clean sparkle: CLEAN or COMBO preamp, treble pushed, optional CHORUS mod,
  HALL or ROOM reverb.
- Edge-of-breakup: TWEED or CRUNCH preamp at gain ~40-55, no OD, light reverb.
- Surf / spaghetti western: CLEAN preamp, SPRING reverb (level ~50), TREMOLO
  via MOD or EQ/FX2.
- Ambient / shoegaze: CLEAN or LEAD preamp, DELAY (often 100-600 ms or longer)
  with moderate feedback, lush HALL reverb.

Output a single JSON object matching the schema. Every block MUST appear in the
output. No prose outside the `rationale` field.
"""


@dataclass
class GenerationError(Exception):
    """Raised when generation fails after all retries."""

    message: str
    last_raw: str = ""
    last_error: str = ""

    def __str__(self) -> str:
        return self.message


def _user_prompt(description: str, recipe_seed: dict | None) -> str:
    parts = [f"Tone description: {description}"]
    if recipe_seed:
        # Curated recipe matched against the description — give the model a clear
        # directive to anchor on it rather than guess from scratch.
        recipe_id = recipe_seed.get("id", "unknown")
        recipe_desc = recipe_seed.get("description", "")
        patch = recipe_seed.get("patch", recipe_seed)
        parts.append(
            f"A curated reference recipe matches this description (id: {recipe_id}).\n"
            f"Notes: {recipe_desc}\n\n"
            "Use this recipe's preamp type and effect-type choices as your anchor — "
            "do not deviate from them unless the user's description explicitly "
            "contradicts. Knob values below are starting points; you may adjust "
            "them to fit any extra detail in the description (e.g. 'more reverb', "
            "'tighter low end').\n\n"
            "Reference recipe patch settings:"
        )
        parts.append(json.dumps(patch, indent=2))
    return "\n\n".join(parts)


def generate_patch(
    description: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    retries: int = DEFAULT_RETRIES,
    recipe_seed: dict | None = None,
    client: "object | None" = None,
) -> SemanticPatch:
    """Generate one SemanticPatch from a tone description.

    `client` is dependency-injected for testing; in normal use we instantiate
    `ollama.Client()` lazily so importing this module doesn't require Ollama.
    """
    if client is None:
        import ollama
        client = ollama.Client()

    schema = SemanticPatch.model_json_schema()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(description, recipe_seed)},
    ]

    last_raw = ""
    last_error = ""
    for attempt in range(retries + 1):
        response = client.chat(  # type: ignore[attr-defined]
            model=model,
            messages=messages,
            format=schema,
            options={"temperature": temperature},
        )
        last_raw = response["message"]["content"]
        try:
            return SemanticPatch.model_validate_json(last_raw)
        except ValidationError as exc:
            last_error = str(exc)
            messages.append({"role": "assistant", "content": last_raw})
            messages.append({
                "role": "user",
                "content": (
                    "That JSON failed schema validation. Errors:\n"
                    f"{last_error}\n\nReturn corrected JSON matching the schema exactly."
                ),
            })

    raise GenerationError(
        message=f"Failed to generate valid patch after {retries + 1} attempts",
        last_raw=last_raw,
        last_error=last_error,
    )
