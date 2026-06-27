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

Reference examples — learn the PATTERN of which blocks belong on/off per genre,
not just the values. Notice that each genre has a distinctive *combination* of
enabled blocks; the supporting effects are as important as the preamp choice.

Example 1 — "djent rhythm tone":
  PREAMP   : METAL (gain=85, bass=60, middle=25, treble=80, level=75)
  OD/DS    : T-SCREAM ON (drive=25, tone=75, level=60)   ← TS in front tightens lows
  COMP/FX1 : off
  MOD      : off
  EQ/FX2   : off
  DELAY    : off                                          ← djent is DRY
  REVERB   : ROOM (level=15)                              ← minimal, body only
  PEDAL FX : off
  Pattern: high-gain metal needs T-SCREAM tightening; modulation/delay kill djent.

Example 2 — "country twang lead":
  PREAMP   : CLEAN (gain=30, bass=45, middle=65, treble=75, level=80)
  OD/DS    : off
  COMP/FX1 : COMP ON (knob1=70, knob2=60, knob3=70)       ← compression IS country
  MOD      : off
  EQ/FX2   : off
  DELAY    : 100-600 ms ON (time=25, feedback=15, e_level=30)  ← short slap-back
  REVERB   : ROOM (level=30)
  PEDAL FX : off
  Pattern: clean-but-not-flat; compressor on hard; slap-back delay is signature.

Example 3 — "shoegaze wall of sound":
  PREAMP   : LEAD (gain=55, bass=50, middle=50, treble=65, level=80)
  OD/DS    : off
  COMP/FX1 : off
  MOD      : CHORUS ON (knob1=50, knob2=60, knob3=60)     ← lush movement
  EQ/FX2   : off
  DELAY    : 500-6000 ms ON (time=70, feedback=55, e_level=60)  ← long, washy
  REVERB   : HALL (level=85)                              ← drenched
  PEDAL FX : off
  Pattern: stack EVERY ambient effect; drive comes from amp, not OD.

Example 4 — "post-rock build swell":
  PREAMP   : CLEAN (gain=35, bass=50, middle=55, treble=65, level=80)
  OD/DS    : off
  COMP/FX1 : COMP ON (knob1=55, knob2=50, knob3=60)       ← even sustain for swells
  MOD      : off
  EQ/FX2   : off
  DELAY    : 500-6000 ms ON (time=80, feedback=65, e_level=60)  ← long building tails
  REVERB   : HALL (level=80)                              ← vast space
  PEDAL FX : off
  Pattern: clean preamp + long delay + huge reverb; comp for the volume swells.

Example 5 — "funk clean rhythm":
  PREAMP   : CLEAN (gain=25, bass=45, middle=60, treble=70, level=75)
  OD/DS    : off
  COMP/FX1 : COMP ON (knob1=75, knob2=70, knob3=65)       ← squashed for the chuck
  MOD      : off
  EQ/FX2   : off
  DELAY    : off
  REVERB   : ROOM (level=20)                              ← just a touch
  PEDAL FX : off
  Pattern: heavy compression is the only signature effect; everything else off.

Example 6 — "stoner doom riff":
  PREAMP   : STACK (gain=70, bass=80, middle=55, treble=45, level=75)  ← bass-forward
  OD/DS    : FUZZ ON (drive=70, tone=45, level=70)        ← fuzz IS the tone
  COMP/FX1 : off
  MOD      : off
  EQ/FX2   : off
  DELAY    : off
  REVERB   : ROOM (level=40)                              ← natural amp room, not cathedral
  PEDAL FX : off
  Pattern: stack + fuzz, dark and fat; no delay/mod, modest room reverb.

When you generate, ask yourself per block: would this style HAVE this effect on?
Many genres are defined by what's OFF as much as what's on. Don't enable blocks
"just to fill space" — and don't leave a defining effect off because you forgot.

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
