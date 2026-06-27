"""The 82-key params template — every patch starts from this dict.

Source: spec §3.4 (verified template, derived from real Contra_1.tsl data).
Knobs default to "50" (musical mid, always valid). Switches default to off
except the preamp, which is always on by hardware design.
"""

from __future__ import annotations

# Sample-defaults for the BPM/tempo-sync fields. The pedal stores tempo as both
# decimal and a high/low hex-byte pair: value = int(h,16)*256 + int(l,16).
# 1556 → 0x0614. We keep the sample values until tempo-sync is implemented.
_DEFAULT_BPM = "1556"
_DEFAULT_BPM_H = "06"
_DEFAULT_BPM_L = "14"


def default_params() -> dict[str, str | None]:
    """Return a fresh copy of the 82-key params template.

    Always return a new dict — callers mutate this freely.
    """
    return {
        # Patch name as 16 ASCII codes (decimal strings), space-padded.
        **{f"name{i}": "32" for i in range(1, 17)},
        "patchname": " " * 16,
        # Comp / FX1
        "comp_sw": "0", "comp_type": "0",
        "comp1": "50", "comp2": "50", "comp3": "50",
        # Overdrive / Distortion
        "odds_sw": "0", "odds_type": "0",
        "odds1": "50", "odds2": "50", "odds3": "50",
        # Preamp (always on by hardware design — start with CLEAN as a safe default)
        "amp_sw": "1", "amp_type": "1",
        "amp1": "50", "amp2": "50", "amp3": "50", "amp4": "50", "amp5": "50",
        # Modulation
        "mod_sw": "0", "mod_type": "0",
        "mod1": "50", "mod2": "50", "mod3": "50",
        # EQ / FX2
        "fx2_sw": "0", "fx2_type": "0",
        "fx2_1": "50", "fx2_2": "50", "fx2_3": "50", "fx2_4": "50",
        # Delay
        "dly_sw": "0", "dly_type": "0",
        "dly1": "50", "dly2": "50", "dly3": "50",
        # Reverb (single-knob LEVEL only)
        "rev_sw": "0", "rev_type": "0", "rev": "50",
        # Pedal FX (expression pedal — no stored knob trio)
        "pdlfx_sw": "0", "pdlfx_type": "0",
        # Noise suppressor
        "ns_thresh": "20",
        # CTL footswitch
        "ctl_target": "0", "ctl_target_h": "00", "ctl_target_l": "00",
        "ctl_mode": "1", "ctrl_knob_value": "100",
        # Tempo-sync values
        "delay_bpm": _DEFAULT_BPM,
        "delay_bpm_h": _DEFAULT_BPM_H,
        "delay_bpm_l": _DEFAULT_BPM_L,
        "modulation_bpm": _DEFAULT_BPM,
        "modulation_bpm_h": _DEFAULT_BPM_H,
        "modulation_bpm_l": _DEFAULT_BPM_L,
        # Dummy placeholder slots — keep at zero per spec.
        **{
            k: v
            for i in range(1, 5)
            for k, v in (
                (f"value_dummy_{i}", "0"),
                (f"value_dummy_{i}_h", "00"),
                (f"value_dummy_{i}_l", "00"),
            )
        },
        # Patch-internal fields kept null in real exports.
        "currentPatchNo": None,
        "prevCurrentPatchNo": None,
        "id": None,
    }


# Expected key count, asserted at module load to catch accidental edits.
_EXPECTED_PARAM_KEYS = 82
_actual = len(default_params())
if _actual != _EXPECTED_PARAM_KEYS:  # pragma: no cover
    raise AssertionError(
        f"default_params() returned {_actual} keys, expected {_EXPECTED_PARAM_KEYS}"
    )
