# me80-tone-gen

Type a tone description like _"warm bluesy lead with spring reverb"_ — get back a Boss ME-80 patch you can import straight into BOSS TONE STUDIO. Fully local. No cloud, no paid APIs, no telemetry.

```
$ tone-gen "master of puppets rhythm tone" -o lead.tsl

  Recipe matched: master-of-puppets-rhythm
Patch: 'MASTER OF PUPPET'
Signal chain: IN → PEDAL FX → COMP/FX1 → OD/DS → PREAMP → MOD → EQ/FX2 → DELAY → REVERB → OUT

  [off] PEDAL FX  WAH
  [off] COMP/FX1  COMP
  [ON ] OD/DS     T-SCREAM
           DRIVE    30
           TONE     70
           LEVEL    60
  [ON ] PREAMP    METAL
           GAIN     70
           BASS     65
           MIDDLE   30
           TREBLE   70
           LEVEL    65
  [off] MOD       CHORUS
  [off] EQ/FX2    EQ
  [off] DELAY     100-600 ms
  [ON ] REVERB    ROOM
           LEVEL    20
```

## What it does

- **Text → patch.** A natural-language description becomes a complete, valid ME-80 patch: preamp choice, effect blocks, knob values, the lot.
- **Writes `.tsl` livesets.** Output is the exact same format BOSS TONE STUDIO uses — import the file, drag onto a user memory slot, you're done.
- **Hardware-verified.** Writer output round-trips cleanly into BTS and onto the pedal. The knob value range (0–99) was confirmed against an actual ME-80 export.
- **Recipe-augmented.** A curated set of famous tones (Master of Puppets, AC/DC, SRV, Gilmour, surf, U2, Hendrix, modern fingerstyle) acts as known-good seeds when your description matches one. Generic descriptions fall back to the model's general taste.
- **Two interfaces, one core.** CLI for piping and batch generation, web UI for browsing and previewing.

## What it's not

- **Not an audio-to-settings converter.** Plays no audio, hears nothing, can't reverse-engineer a recording. Text in, patch out.
- **Not a guarantee of accuracy.** The ME-80 has a fixed palette of amps and effects — many famous tones can only be approximated, not replicated. Treat output as a *starting point*, then tweak by ear.
- **Not a real-time patch editor.** The `.tsl` is imported into BTS like any other liveset. There's no live USB parameter writing.

## Requirements

- Python **3.11+**
- [Ollama](https://ollama.com) installed and running locally
- A structured-output-capable model pulled (default: `qwen2.5:14b`)
- BOSS TONE STUDIO for ME-80 (only needed to import the generated `.tsl` onto your pedal)

Tested on Apple Silicon (Mac) and Linux. Should run anywhere Ollama runs.

## Install

```bash
git clone https://github.com/CammyBlack02/me80-tone-gen
cd me80-tone-gen
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# If you don't have Ollama yet:
brew install ollama          # macOS
brew services start ollama
ollama pull qwen2.5:14b      # ~9 GB
```

## Usage

### CLI

```bash
# Print the patch as a knob list
tone-gen "warm bluesy lead with spring reverb"

# Also write a .tsl liveset to disk
tone-gen "ambient post-rock swell" -o ambient.tsl

# Machine-readable JSON output (no formatting noise)
tone-gen "lo-fi crunchy garage rock" --json

# Read from stdin (pipe-friendly)
echo "djent rhythm tone" | tone-gen -o djent.tsl

# Batch: one description per line → single multi-patch liveset
tone-gen --batch descriptions.txt -o bank.tsl

# Override model or sampling
tone-gen "spaghetti western lead" --model llama3.1:8b --temp 0.6

# Disable recipe matching (rely purely on model knowledge)
tone-gen "djent tone" --no-recipes
```

Real exit codes (`0` on success, `1` on generation failure, `2` on usage error) — safe to script around.

### Web UI

```bash
tone-gen-serve
# → http://127.0.0.1:8765
```

Single-page UI: text input, options, results panel with recipe match indicator, download `.tsl` button. The browser builds the download from the same JSON the API returns — no second round-trip.

### Importing onto the pedal

1. Connect ME-80 via USB and power on
2. Open BOSS TONE STUDIO
3. **Import** → select your `.tsl`
4. Drag the patch onto a user memory slot

The physical knobs won't reflect the loaded patch until you move one — that's normal ME-80 behaviour, not a bug. The included knob list shows you the target positions.

## Recipes

The `recipes.json` file (in `src/me80_tone_gen/`) is the RAG layer. When a description includes one of a recipe's aliases, that recipe's settings are passed to the model as a known-good seed. The model can still tweak knob values to match extra detail in the description ("master of puppets with more reverb" → keeps METAL+T-SCREAM, ups the reverb).

To add or refine a recipe, edit `recipes.json`. Format:

```json
{
  "id": "your-recipe-id",
  "aliases": ["phrase one", "phrase two", "artist name"],
  "description": "What this tone is and why it sounds the way it does.",
  "patch": { "preamp": {...}, "od_ds": {...}, ... }
}
```

Substring matching, case-insensitive. Longer matched aliases beat shorter ones, so more specific descriptions still route correctly. Use `--recipes path/to/custom.json` to point the CLI at a different file.

## Development

```bash
pip install -e '.[dev]'
pytest                          # unit tests (no Ollama needed)
ruff check src tests scripts   # lint (also run in CI)
./scripts/fetch_reference.sh    # downloads Contra_1.tsl for full conformance tests
```

Tests anchored against a real BTS export will skip cleanly if the reference file isn't present.

To measure generation quality (needs Ollama running), run the structural eval suite — it scores pass-rates for guitarist-agreeable assertions ("djent leaves delay off", "surf uses spring reverb") across repeated runs, so prompt or model changes become measurable instead of vibes:

```bash
python scripts/run_eval.py                        # full suite, 3 runs per case
python scripts/run_eval.py --no-recipes --out b.json   # A/B the raw prompt
```

## License

**[PolyForm Noncommercial License 1.0.0](LICENSE)** — free for personal use, hobby projects, research, and noncommercial organizations. **Commercial use requires a license** from the copyright holder.

If you want to use this commercially (host it with ads, embed it in a paid product, sell it bundled with hardware, etc.) open an issue or reach out via GitHub and we'll work something out.

## Acknowledgements

The `.tsl` format was reverse-engineered with reference to the community parser at [`johnsrude/BossToneStudio`](https://github.com/johnsrude/BossToneStudio). That repo provided the original `Contra_1.tsl` sample we use as the structural conformance reference (fetched via `scripts/fetch_reference.sh`, not bundled here).

Built with [Ollama](https://ollama.com), [FastAPI](https://fastapi.tiangolo.com), and [Pydantic](https://pydantic.dev).

The v0.1.0 implementation was paired with [Claude Code](https://claude.com/claude-code) (model: Claude Opus 4.7) in a single session. The spec, hardware verification, design decisions, and taste calls came from the author; Claude wrote most of the code and tests against that spec.
