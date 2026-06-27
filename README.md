# me80-tone-gen

Natural-language → Boss ME-80 patch generator. Fully local: descriptions go through Ollama, the result lands as a `.tsl` liveset file that BOSS TONE STUDIO imports directly.

See the spec for design rationale and the `.tsl` format reference. Project notes live in the Obsidian "Tone Program" vault.

## Status

Pre-MVP. CLI-first; web UI later.

## Quickstart (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Once the LLM step is wired up:
tone-gen "warm bluesy lead with spring reverb" -o lead.tsl
```

## Requirements

- Python 3.11+
- Ollama running locally with a structured-output-capable model pulled (e.g. `qwen2.5:14b`)
- BOSS TONE STUDIO for ME-80 (to import the generated `.tsl` on the actual pedal)
