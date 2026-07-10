"""LLM layer — text description → SemanticPatch via Ollama structured output.

The model only sees type *names* (not raw indices), and Ollama's JSON-schema
constraint guarantees the model can't emit an invalid amp/effect type. We still
re-validate after parsing — structural validity ≠ musical sensibility.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import ValidationError

from . import enums
from .schema import SemanticPatch

DEFAULT_MODEL = "qwen2.5:14b"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_RETRIES = 2

_VARIANT_TEMP_LO = 0.2
_VARIANT_TEMP_HI = 0.8


def evenly_spaced_temperatures(n: int) -> list[float]:
    """N temperatures for variant generation.

    n=1 → [DEFAULT_TEMPERATURE] (single variant means no diversity; use the
    model's normal default). n>=2 → evenly spaced across [0.2, 0.8] inclusive.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if n == 1:
        return [DEFAULT_TEMPERATURE]
    step = (_VARIANT_TEMP_HI - _VARIANT_TEMP_LO) / (n - 1)
    return [_VARIANT_TEMP_LO + i * step for i in range(n)]


def _knob_reference() -> str:
    """Per-type knob meanings, rendered for the system prompt.

    Generated from the enums tables so the prompt, the JSON schema field
    descriptions, and the renderer can never drift apart.
    """
    lines = [
        "Knob meanings for the generic-knob blocks (types not listed use "
        "generic depth/amount knobs):"
    ]
    for block_name, table in enums.KNOBS_BY_BLOCK.items():
        for type_name, labels in table.items():
            named = ", ".join(f"knob{i + 1}={label}" for i, label in enumerate(labels))
            lines.append(f"- {block_name} {type_name}: {named}")
    return "\n".join(lines)


SYSTEM_PROMPT = f"""\
You are a Boss ME-80 patch designer. Convert a natural-language tone description
into a single ME-80 patch as JSON matching the supplied schema.

Hard constraints:
- Choose ONLY from the legal type names supplied in the schema's enum fields.
- Knob values are integers 0-99. 0 = minimum, 99 = maximum (50 is mid).
- The ME-80's signal chain (fixed): PEDAL FX → COMP/FX1 → OD/DS → PREAMP → MOD →
  EQ/FX2 → DELAY → REVERB.
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

{_knob_reference()}

Delay TIME knob: the range-named delay types map the 0-99 TIME knob roughly
linearly across the named millisecond range. On "100-600 ms", time=25 is about
225 ms. Pick the type whose range contains the target time (slap-back is about
80-140 ms; a quarter note at 120 BPM is 500 ms; long ambient trails want
"500-6000 ms").

Reference examples — learn the PATTERN of which blocks belong on/off per genre,
not just the values. Notice that each genre has a distinctive *combination* of
enabled blocks; the supporting effects are as important as the preamp choice.

Example 1 — "djent rhythm tone":
  PREAMP   : METAL (gain=85, bass=60, middle=25, treble=80, level=75)
  OD/DS    : T-SCREAM ON (drive=25, tone=75, level=60)   -- TS in front tightens lows
  COMP/FX1 : off
  MOD      : off
  EQ/FX2   : off
  DELAY    : off                                          -- djent is DRY
  REVERB   : ROOM (level=15)                              -- minimal, body only
  PEDAL FX : off
  Pattern: high-gain metal needs T-SCREAM tightening; modulation/delay kill djent.

Example 2 — "country twang lead":
  PREAMP   : CLEAN (gain=30, bass=45, middle=65, treble=75, level=80)
  OD/DS    : off
  COMP/FX1 : COMP ON (knob1=70, knob2=60, knob3=70)       -- compression IS country
  MOD      : off
  EQ/FX2   : off
  DELAY    : 100-600 ms ON (time=25, feedback=15, e_level=30)  -- short slap-back
  REVERB   : ROOM (level=30)
  PEDAL FX : off
  Pattern: clean-but-not-flat; compressor on hard; slap-back delay is signature.

Example 3 — "shoegaze wall of sound":
  PREAMP   : LEAD (gain=55, bass=50, middle=50, treble=65, level=80)
  OD/DS    : off
  COMP/FX1 : off
  MOD      : CHORUS ON (knob1=50, knob2=60, knob3=60)     -- lush movement
  EQ/FX2   : off
  DELAY    : 500-6000 ms ON (time=70, feedback=55, e_level=60)  -- long, washy
  REVERB   : HALL (level=85)                              -- drenched
  PEDAL FX : off
  Pattern: stack EVERY ambient effect; drive comes from amp, not OD.

Example 4 — "post-rock build swell":
  PREAMP   : CLEAN (gain=35, bass=50, middle=55, treble=65, level=80)
  OD/DS    : off
  COMP/FX1 : COMP ON (knob1=55, knob2=50, knob3=60)       -- even sustain for swells
  MOD      : off
  EQ/FX2   : off
  DELAY    : 500-6000 ms ON (time=80, feedback=65, e_level=60)  -- long building tails
  REVERB   : HALL (level=80)                              -- vast space
  PEDAL FX : off
  Pattern: clean preamp + long delay + huge reverb; comp for the volume swells.

Example 5 — "funk clean rhythm":
  PREAMP   : CLEAN (gain=25, bass=45, middle=60, treble=70, level=75)
  OD/DS    : off
  COMP/FX1 : COMP ON (knob1=75, knob2=70, knob3=65)       -- squashed for the chuck
  MOD      : off
  EQ/FX2   : off
  DELAY    : off
  REVERB   : ROOM (level=20)                              -- just a touch
  PEDAL FX : off
  Pattern: heavy compression is the only signature effect; everything else off.

Example 6 — "stoner doom riff":
  PREAMP   : STACK (gain=70, bass=80, middle=55, treble=45, level=75)  -- bass-forward
  OD/DS    : FUZZ ON (drive=70, tone=45, level=70)        -- fuzz IS the tone
  COMP/FX1 : off
  MOD      : off
  EQ/FX2   : off
  DELAY    : off
  REVERB   : ROOM (level=40)                              -- natural amp room, not cathedral
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


def probe_ready(
    model: str = DEFAULT_MODEL, client: object | None = None
) -> dict[str, str | bool]:
    """Check Ollama reachability and whether `model` is pulled.

    Never raises for the two expected failure modes (unreachable, model missing)
    — those are the states the caller wants to render to a user, not exceptions
    to handle.
    """
    import httpx
    import ollama

    if client is None:
        client = ollama.Client()

    try:
        response = client.list()  # type: ignore[attr-defined]
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError):
        return {
            "ready": False,
            "issue": "ollama_unreachable",
            "message": "Cannot reach the Ollama server.",
            "fix": "brew services start ollama  (or: ollama serve)",
        }
    except ollama.ResponseError as exc:
        return {
            "ready": False,
            "issue": "ollama_error",
            "message": f"Ollama returned an error: {exc}",
            "fix": "",
        }

    names = {m.model for m in response.models}
    if model not in names:
        return {
            "ready": False,
            "issue": "model_not_pulled",
            "model": model,
            "message": f"Model {model!r} is not pulled.",
            "fix": f"ollama pull {model}",
        }

    return {"ready": True, "model": model}


def _as_friendly_transport_error(exc: Exception, model: str) -> GenerationError | None:
    """Translate an Ollama transport failure into an actionable GenerationError.

    The two most common real-world failures — server not running, model not
    pulled — deserve a one-line instruction, not a traceback. Returns None for
    anything unrecognized so genuine bugs still surface raw.
    """
    import httpx
    import ollama

    if isinstance(exc, ollama.ResponseError):
        if exc.status_code == 404 or "not found" in str(exc).lower():
            return GenerationError(
                message=(
                    f"Model {model!r} is not available in Ollama. "
                    f"Pull it first: ollama pull {model}"
                ),
                last_error=str(exc),
            )
        return GenerationError(
            message=f"Ollama returned an error: {exc}", last_error=str(exc)
        )
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, ConnectionError)):
        return GenerationError(
            message=(
                "Cannot reach the Ollama server. Is it running? "
                "Start it with `ollama serve` (or `brew services start ollama`)."
            ),
            last_error=str(exc),
        )
    return None


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
    client: object | None = None,
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
    for _ in range(retries + 1):
        try:
            response = client.chat(  # type: ignore[attr-defined]
                model=model,
                messages=messages,
                format=schema,
                options={"temperature": temperature},
            )
        except Exception as exc:
            friendly = _as_friendly_transport_error(exc, model)
            if friendly is None:
                raise
            raise friendly from exc
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


def generate_variants(
    description: str,
    *,
    n: int = 3,
    temperatures: list[float] | None = None,
    model: str = DEFAULT_MODEL,
    retries: int = DEFAULT_RETRIES,
    recipe_seed: dict | None = None,
    client: object | None = None,
) -> list[SemanticPatch]:
    """Generate N patches in parallel with per-variant temperature.

    If `temperatures` is None: uses `evenly_spaced_temperatures(n)`.
    If `temperatures` is provided: its length MUST equal `n`; a mismatch
    raises ValueError before any Ollama calls are made.

    Results are returned in input (temperature) order, not completion order.
    If any variant raises GenerationError, the whole call raises — no partial
    success.
    """
    if temperatures is None:
        temps = evenly_spaced_temperatures(n)
    else:
        if len(temperatures) != n:
            raise ValueError(
                f"len(temperatures)={len(temperatures)} does not match n={n}"
            )
        temps = list(temperatures)

    if client is None:
        import ollama
        client = ollama.Client()

    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = [
            executor.submit(
                generate_patch,
                description,
                model=model,
                temperature=t,
                retries=retries,
                recipe_seed=recipe_seed,
                client=client,
            )
            for t in temps
        ]
        return [f.result() for f in futures]
