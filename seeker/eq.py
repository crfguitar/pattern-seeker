"""CFilteR-01 (the user's own Pro-Q 4 clone) as FL sees it: band settings in real
units -> the plugin's normalised parameter values.

The curves are the plugin's own (CFilter/Source/Parameters.cpp) and were checked
live in FL: 40 Hz -> 0.17315 read back "40.000 Hz", -2 dB -> 0.466667 "-2.00 dB",
Low Cut -> 0.222222 "Low Cut".
"""
import math

PLUGIN = "CFilteR-01"
BANDS = 24
PARAMS_PER_BAND = 24
# offsets inside a band's block of parameters
USED, ENABLED, FREQ, GAIN, Q, SHAPE, SLOPE = range(7)

SHAPES = ["bell", "low shelf", "low cut", "high shelf", "high cut", "notch",
          "band pass", "tilt shelf", "flat tilt", "all pass"]
MIN_FREQ, MAX_FREQ = 10.0, 30000.0
MIN_GAIN, MAX_GAIN = -30.0, 30.0
MIN_Q, MAX_Q = 0.025, 40.0


class EqError(ValueError):
    pass


def norm_freq(hz):
    hz = min(max(float(hz), MIN_FREQ), MAX_FREQ)
    return math.log(hz / MIN_FREQ) / math.log(MAX_FREQ / MIN_FREQ)


def norm_gain(db):
    db = min(max(float(db), MIN_GAIN), MAX_GAIN)
    return (db - MIN_GAIN) / (MAX_GAIN - MIN_GAIN)


def norm_q(q):
    q = min(max(float(q), MIN_Q), MAX_Q)
    return math.log(q / MIN_Q) / math.log(MAX_Q / MIN_Q)


def norm_slope(db_oct):
    """dB/oct (0-96, or 'brickwall') -> 0..1, the plugin's piecewise curve."""
    if isinstance(db_oct, str) and "brick" in db_oct.lower():
        return 1.0
    v = min(max(float(db_oct), 0.0), 96.0)
    if v <= 36:
        return v / 60.0
    if v <= 48:
        return 0.6 + (v - 36) / 120.0
    return 0.7 + (v - 48) / 240.0


def norm_shape(shape):
    want = str(shape).strip().lower().replace("_", " ").replace("-", " ")
    want = {"high pass": "low cut", "hpf": "low cut", "hp": "low cut",
            "low pass": "high cut", "lpf": "high cut", "lp": "high cut",
            "peak": "bell", "peaking": "bell"}.get(want, want)
    if want not in SHAPES:
        raise EqError("shape %r: use one of %s." % (shape, ", ".join(SHAPES)))
    return SHAPES.index(want) / float(len(SHAPES) - 1)


def band_sets(slot, bands):
    """[{band?, shape, freq, gain?, q?, slope?, on?}, ...] -> the mixer command's
    `set` rows [[slot, parameter index, value]]. Bands without a number take
    1, 2, 3 ... in order."""
    rows, used = [], set()
    for n, b in enumerate(bands, 1):
        if not isinstance(b, dict):
            raise EqError("each band is an object like {\"shape\": \"low cut\", "
                          "\"freq\": 40}.")
        num = int(b.get("band", n))
        if not 1 <= num <= BANDS:
            raise EqError("band %d: CFilteR-01 has bands 1-%d." % (num, BANDS))
        if num in used:
            raise EqError("band %d is given twice." % num)
        used.add(num)
        base = (num - 1) * PARAMS_PER_BAND
        if "freq" not in b:
            raise EqError("band %d needs a freq (Hz)." % num)
        rows.append([slot, base + USED, 1.0])
        rows.append([slot, base + ENABLED, 1.0 if b.get("on", True) else 0.0])
        rows.append([slot, base + SHAPE, norm_shape(b.get("shape", "bell"))])
        rows.append([slot, base + FREQ, norm_freq(b["freq"])])
        rows.append([slot, base + GAIN, norm_gain(b.get("gain", 0.0))])
        rows.append([slot, base + Q, norm_q(b.get("q", 1.0))])
        if "slope" in b:
            rows.append([slot, base + SLOPE, norm_slope(b["slope"])])
    return rows, used


def clear_sets(slot, keep=()):
    """Mark every band not in `keep` unused (a flat EQ but for the given bands)."""
    return [[slot, (n - 1) * PARAMS_PER_BAND + USED, 0.0]
            for n in range(1, BANDS + 1) if n not in keep]


def describe(rows):
    """The read-back rows [slot, index, name, value, text] -> {"Band 1": "Low Cut
    40.000 Hz ..."}, the plugin's own words for what it now holds."""
    out = {}
    for row in rows:
        name, text = row[2], (row[4] if len(row) > 4 else "").strip()
        parts = name.split(" ", 2)
        if len(parts) == 3 and parts[0] == "Band" and parts[2] != "Used":
            out.setdefault("Band " + parts[1], []).append(text)
    return {k: " ".join(v) for k, v in out.items()}
