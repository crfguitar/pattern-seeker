"""Inner Light - an original trap instrumental built only from the Lunch77 "Inner
Light" drum kit, 80 BPM (a 160 trap feel), B-flat minor, with room for a rapper.

    python examples/inner_light.py          # compose, print the plan and the checks
    python examples/inner_light.py render   # cut the loop chops and tune the 808 (CHOPS)
    python examples/inner_light.py build    # add the channels
    python examples/inner_light.py write    # write the patterns (lay them out with arrange)
    python examples/inner_light.py rewrite 808 Hat   # new notes, playlist kept

The idea: a storm outside, a light inside. The kit's music-box arpeggio (Extras 13)
is first heard muffled, as if through a wall, under thunder (Extras 33) and tape
crackle (Extras 35); it opens up at the hook and goes back behind the wall in the
bridge. A reversed chop of the loop rises into each hook, a gasp (Vox 32) breathes
in before each drop.

The loop, measured: 80.0 BPM exactly (onsets 0.750 s apart), first downbeat at
1.474 s, 16 bars, a pentatonic arpeggio on D# G# F C# A# with a passing E, about
+10 cents sharp, and no bass at all (nothing under C#4). So the 808 sets the
harmony: Gb (the E becomes its 7th) - Ab | Bbm, i.e. IV - V | vi in D-flat,
with Eb on the loop's last half bar (an almost bare D#).

Form (bars): Intro 8 | Hook 8 | Verse 1 16 | Hook 8 | Bridge 8 | Verse 2 16
             | Hook 8 | Outro 8 = 80 bars, 4:00.
"""

import collections
import json
import os
import random
import statistics
import sys

TEMPO = 80
SAMPLES = os.environ.get("PATTERN_SEEKER_SAMPLES", os.path.join(os.path.expanduser("~"), "Music", "Samples"))
KIT = os.path.join(SAMPLES, r"Inner Light Drumkit\Inner Light Drumkit")
CHOPS = os.path.join(SAMPLES, r"Pattern Seeker\Inner Light")
LOOP = KIT + r"\Extras\Lunch77 Inner-Light Extra (13).wav"
LOOP_FIRST, BAR_S = 1.474, 3.0                          # downbeat, seconds per bar at 80

# channel: (sample, colour, volume, pan). Hats left, near centre (drum-panning memory).
BAND = {
    "Kick": (KIT + r"\Kicks\Lunch77 Inner-Light Kick (87).wav", "#C8553D", 0.78, 0.0),
    "Snare": (KIT + r"\Snares\Lunch77 Inner-Light Snare (17).wav", "#E0A33A", 0.66, 0.0),
    "Clap": (KIT + r"\Claps\Lunch77 Inner-Light Clap (40).wav", "#E8C15A", 0.46, 0.0),
    "Hat": (KIT + r"\Closed Hats\Lunch77 Inner-Light Closed Hat (48).wav", "#D9CB5E", 0.42, -0.15),
    "Open hat": (KIT + r"\Open Hats\Lunch77 Inner-Light Open Hat (34).wav", "#C9B85A", 0.30, -0.15),
    "Perc": (KIT + r"\Percs\Lunch77 Inner-Light Perc (46).wav", "#A8B05A", 0.32, 0.25),
    "Crash": (KIT + r"\Crashes\Lunch77 Inner-Light Crash (6).wav", "#8A8A8A", 0.28, 0.20),
    "808": (CHOPS + r"\808 (1) tuned.wav", "#7A4FA0", 0.50, 0.0),
    "Vox": (KIT + r"\Vox\Lunch77 Inner-Light Vox (32).wav", "#B07AA0", 0.38, 0.0),
    "Loop": (CHOPS + r"\Loop A.wav", "#4F8FC0", 0.62, 0.0),
    "Loop Hook": (CHOPS + r"\Loop B.wav", "#5FA0D0", 0.62, 0.0),
    "Loop Muffled": (CHOPS + r"\Loop A muffled.wav", "#3F6F90", 0.60, 0.0),
    "Loop Reverse": (CHOPS + r"\Loop B reversed.wav", "#6F7FB0", 0.42, 0.0),
    "Storm": (KIT + r"\Extras\Lunch77 Inner-Light Extra (33).wav", "#506070", 0.40, 0.0),
    "Crackle": (KIT + r"\Extras\Lunch77 Inner-Light Extra (35).wav", "#707070", 0.20, 0.0),
}
ONCE = {"Loop", "Loop Hook", "Loop Muffled", "Loop Reverse", "Storm", "Crackle"}   # long samples


def render():
    """Cut the loop on its own grid (80 BPM, downbeat 1.474 s): A = bars 1-8 (the
    softer half), B = bars 9-16 (fuller), A muffled (low-passed, a little narrower),
    B's last two bars reversed. Tune 808 (1) from C1 -4 cents to the loop's +10."""
    import numpy as np
    import soundfile as sf
    from scipy.signal import butter, resample_poly, sosfiltfilt
    os.makedirs(CHOPS, exist_ok=True)
    x, sr = sf.read(LOOP, always_2d=True)

    def cut(bar0, bars):
        a = int(round((LOOP_FIRST + bar0 * BAR_S) * sr))
        return x[a:a + int(round(bars * BAR_S * sr))].copy()

    def fades(y, fin=0.003, fout=0.03):
        n, m = int(fin * sr), int(fout * sr)
        y[:n] *= np.linspace(0, 1, n)[:, None]
        y[-m:] *= np.linspace(1, 0, m)[:, None]
        return y

    def norm(y, peak_db=-1.0):
        return y * (10 ** (peak_db / 20) / (np.max(np.abs(y)) + 1e-12))

    a, b = cut(0, 8), cut(8, 8)
    gain = 10 ** (-1 / 20) / max(np.max(np.abs(a)), np.max(np.abs(b)))   # one gain: B stays fuller
    sf.write(CHOPS + r"\Loop A.wav", fades(a * gain), sr, subtype="PCM_24")
    sf.write(CHOPS + r"\Loop B.wav", fades(b * gain), sr, subtype="PCM_24")
    sos = butter(4, 850, "lowpass", fs=sr, output="sos")
    mu = sosfiltfilt(sos, a, axis=0)
    mid, side = mu.mean(1, keepdims=True), (mu[:, :1] - mu[:, 1:]) / 2
    mu = np.hstack([mid + 0.6 * side, mid - 0.6 * side])
    sf.write(CHOPS + r"\Loop A muffled.wav", fades(norm(mu, -2.0)), sr, subtype="PCM_24")
    rv = cut(14, 2)[::-1].copy()
    sf.write(CHOPS + r"\Loop B reversed.wav", fades(norm(rv, -2.0), 0.4, 0.01), sr, subtype="PCM_24")
    b8, sr8 = sf.read(KIT + r"\808s\Lunch77 Inner-Light 808 (1).wav", always_2d=True)
    up = 2 ** (14 / 1200)                                # play 14 cents higher = shorter by `up`
    num, den = 10000, int(round(10000 * up))
    sf.write(CHOPS + r"\808 (1) tuned.wav", resample_poly(b8, num, den, axis=0), sr8, subtype="PCM_24")
    for f in sorted(os.listdir(CHOPS)):
        i = sf.info(os.path.join(CHOPS, f))
        print("%-22s %6.2fs" % (f, i.duration))


# ---- harmony ------------------------------------------------------------------------------
# 808 sample is C1 at note 60: Gb1 = 66, Ab1 = 68, Bb1 = 70, Eb1 = 63.
ROOT = {"Gb": 66, "Ab": 68, "Bb": 70, "Eb": 63}


def chord_at(bar, beat, loop_last=False):
    """Two-bar cycle under the loop: Gb (1-2) Ab (3-4) | Bbm. The loop's very last half
    bar is an almost bare D#: Eb."""
    if bar % 2 == 0:
        return "Gb" if beat < 2 else "Ab"
    if loop_last and bar % 8 == 7 and beat >= 2:
        return "Eb"
    return "Bb"


LEVEL = {"Intro": -6, "Hook 1": 4, "Verse 1": -2, "Hook 2": 5, "Bridge": -6,
         "Verse 2": -1, "Hook 3": 6, "Outro": -5}


class Sec:
    def __init__(self, name, bars, color):
        self.name, self.bars, self.color = name, bars, color
        self.parts = collections.defaultdict(list)

    def add(self, ch, pitch, start, length, vel):
        self.parts[ch].append([pitch, round(start, 4), round(length, 4), vel])


def hit(s, rng, ch, t, vel, pitch=60, length=0.25):
    s.add(ch, pitch, max(0.0, t + rng.uniform(-0.006, 0.006)), length, vel + rng.randint(-3, 3))


def long(s, ch, t, beats, vel):
    s.add(ch, 60, t, beats - 0.02, vel)


KICKS = [[0, 0.75, 2.5], [0, 1.75, 2.5, 3.25], [0, 0.75, 2.25, 2.75], [0, 1.5, 2.5, 3.75]]
VERSE_KICKS = [[0, 2.5], [0, 1.75, 2.5], [0, 0.75, 2.5], [0, 2.25, 3.5]]


def hats(s, rng, t, i, busy, roll_every=2):
    """16ths (8ths when not busy) with a roll at the end of every other bar."""
    step = 1 if busy else 2
    roll = i % roll_every == roll_every - 1
    for k in range(0, 16, step):
        if roll and k >= 12:
            break
        v = 76 if k % 4 == 0 else 68 if k % 2 == 0 else 60
        hit(s, rng, "Hat", t + k * 0.25, v, length=0.1)
    if roll:
        kind = (i // roll_every) % 3
        if kind == 0:                                    # sextuplets over beat 4
            n, d = 6, 1 / 6
        elif kind == 1:                                  # 32nds over beat 4
            n, d = 8, 0.125
        else:                                            # triplet 16ths, then a 32nd burst
            n, d = 3, 1 / 3
        for r in range(n):
            hit(s, rng, "Hat", t + 3 + r * d, 58 + int(16 * r / n), length=0.06)
        if kind == 2:
            for r in range(4):
                hit(s, rng, "Hat", t + 3.5 + r * 0.125, 64 + 3 * r, length=0.05)


def drums(s, rng, bar0, bars, kicks=KICKS, busy=True, end="fill", open_hat=True, perc=False):
    """end: 'fill' = a snare pickup into the next section, 'cut' = everything stops after
    beat 2 of the last bar (the gasp sits alone), None = play through."""
    kicks_at = []
    for i in range(bars):
        t = (bar0 + i) * 4
        last = i == bars - 1
        cut = last and end == "cut"
        for k in kicks[i % 4]:
            if cut and k >= 2:
                continue
            kicks_at.append(t + k)
            hit(s, rng, "Kick", t + k, 94 if k == 0 else 86)
        for beat in (1, 3):
            if cut and beat == 3:
                continue
            hit(s, rng, "Snare", t + beat, 92)
            hit(s, rng, "Clap", t + beat + 0.008, 82)
        if last and end == "fill":
            for k, v in ((3.5, 70), (3.625, 74), (3.75, 80), (3.875, 86)):
                hit(s, rng, "Snare", t + k, v)
        if cut:
            for k in range(0, 8, 2 if not busy else 1):
                hit(s, rng, "Hat", t + k * 0.25, 70 if k % 4 == 0 else 62, length=0.1)
            continue
        hats(s, rng, t, i, busy)
        if open_hat and i % 2 == 1:
            hit(s, rng, "Open hat", t + 2.5, 72, length=0.5)
        if perc:
            for k in ((0.5, 2.75) if i % 2 == 0 else (1.25, 3.5)):
                hit(s, rng, "Perc", t + k, 64)
    return kicks_at


def bass(s, kicks_at, bar0, bars, loop_last=False, stop=None, octave=False):
    """808 on every kick and on each chord change, held to the next one."""
    starts = set(round(k, 4) for k in kicks_at)
    for i in range(bars):
        t = (bar0 + i) * 4
        for c in (0, 2):
            if not any(abs(k - (t + c)) < 0.5 for k in starts):
                if chord_at(i, c, loop_last) != chord_at(i, c - 0.01, loop_last) or c == 0:
                    starts.add(t + c)
    starts = sorted(x for x in starts if stop is None or x < stop)
    end = (bar0 + bars) * 4 if stop is None else stop
    for j, t in enumerate(starts):
        nxt = starts[j + 1] if j + 1 < len(starts) else end
        bar, beat = int(t // 4) - bar0, t % 4
        root = ROOT[chord_at(bar, beat, loop_last)]
        up = octave and bar % 2 == 1 and beat >= 3        # a jump to the octave on the last kick
        s.add("808", root + (12 if up else 0), t, max(0.2, nxt - t - 0.04),
              92 if beat == 0 else 84)


# ---- sections -----------------------------------------------------------------------------
def riser(s, rng, bar):
    """The reversed chop swells over two bars; the gasp breathes in on the last beat."""
    long(s, "Loop Reverse", bar * 4, 8, 82)
    hit(s, rng, "Vox", bar * 4 + 7, 78, length=1.0)


def intro(rng):
    s = Sec("Intro", 8, "#3F6F90")
    long(s, "Crackle", 0, 32, 80)
    long(s, "Storm", 0, 20, 84)                           # thunder, about 5 bars of it
    long(s, "Loop Muffled", 0, 32, 90)                    # the light, through the wall
    for i in range(4, 8):                                 # a tick creeps in
        for k in (0.5, 2.75) if i % 2 == 0 else (1.25, 3.5):
            hit(s, rng, "Perc", i * 4 + k, 54 + (i - 4) * 3)
    riser(s, rng, 6)
    return s


def hook(name, rng):
    s = Sec(name, 8, "#5FA0D0")
    long(s, "Crackle", 0, 32, 70)
    long(s, "Loop Hook", 0, 32, 100)
    hit(s, rng, "Crash", 0, 84, length=3)
    kicks = drums(s, rng, 0, 8, KICKS, busy=True, end="fill" if name != "Hook 3" else None)
    bass(s, kicks, 0, 8, loop_last=True, octave=True)
    return s


def verse(name, rng, busy):
    s = Sec(name, 16, "#4F8FC0")
    long(s, "Crackle", 0, 64, 72)
    long(s, "Loop", 0, 32, 96)
    long(s, "Loop", 32, 32, 96)
    hit(s, rng, "Crash", 0, 70, length=3)
    kicks = drums(s, rng, 0, 16, VERSE_KICKS, busy=busy, end="cut", open_hat=busy, perc=True)
    bass(s, kicks, 0, 16, stop=15 * 4 + 2)
    riser(s, rng, 14)
    return s


def bridge(rng):
    s = Sec("Bridge", 8, "#3F6F90")
    long(s, "Crackle", 0, 32, 84)
    long(s, "Storm", 0, 20, 80)
    long(s, "Loop Muffled", 0, 32, 92)
    for i in range(6):                                    # the 808 alone, long, under the wall
        for c in (0, 2) if i % 2 == 0 else (0,):
            s.add("808", ROOT[chord_at(i, c)], i * 4 + c, (2 if i % 2 == 0 else 4) - 0.05, 70)
        for k in (0.5, 2.75) if i % 2 == 0 else (1.25, 3.5):
            hit(s, rng, "Perc", i * 4 + k, 60)
    for i in (6, 7):                                      # the build: kick on the beat, hats rising
        t = i * 4
        for b in range(4):
            hit(s, rng, "Kick", t + b, 78 + (i - 6) * 6)
        for k in range(16 if i == 6 else 32):
            d = 0.25 if i == 6 else 0.125
            hit(s, rng, "Hat", t + k * d, 58 + int(18 * (k * d) / 4) + (i - 6) * 6, length=0.06)
        for k in range(8 if i == 7 else 0):
            hit(s, rng, "Snare", t + 2 + k * 0.25, 62 + k * 3)
    riser(s, rng, 6)
    return s


def outro(rng):
    s = Sec("Outro", 8, "#3F6F90")
    long(s, "Crackle", 0, 32, 80)
    long(s, "Loop Muffled", 0, 32, 92)                   # back behind the wall
    long(s, "Storm", 8, 20, 76)
    kicks = drums(s, rng, 0, 4, VERSE_KICKS, busy=False, end=None, open_hat=False)
    bass(s, kicks, 0, 4)
    s.add("808", ROOT["Gb"], 16, 7.9, 74)                # the 808 rings out under the last bars
    s.add("808", ROOT["Bb"], 24, 7.9, 66)
    return s


def compose(seed=77):
    rng = random.Random(seed)
    secs = [intro(rng), hook("Hook 1", rng), verse("Verse 1", rng, False), hook("Hook 2", rng),
            bridge(rng), verse("Verse 2", rng, True), hook("Hook 3", rng), outro(rng)]
    for i, s in enumerate(secs):
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        end = s.bars * 4
        for ch, notes in s.parts.items():
            for n in notes:
                if ch not in ONCE:                        # long samples keep their own level
                    ramp = max(0.0, (n[1] - (end - 8)) / 8) * (nxt - level) * 0.5
                    n[3] = int(round(min(100, max(50, n[3] + level + ramp))))
                n[1] = round(max(0.0, n[1]), 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)
    return secs


def check(secs):
    meds = []
    for s in secs:
        for b in range(s.bars):
            vs = [n[3] for ch, ns in s.parts.items() if ch not in ONCE
                  for n in ns if b * 4 <= n[1] < b * 4 + 4]
            meds.append((s.name, b + 1, statistics.median(vs) if vs else None))
    return sorted(((abs(b[2] - a[2]), a, b) for a, b in zip(meds, meds[1:]) if a[2] and b[2]),
                  reverse=True)


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    do = argv[1] if len(argv) > 1 else "plan"
    if do == "render":
        return render()
    secs = compose()
    if do == "plan":
        bar = 1
        for s in secs:
            vs = [n[3] for ch, ns in s.parts.items() if ch not in ONCE for n in ns] or [0]
            print("bars %2d-%2d  %-8s %4d notes  vel %d-%d  %s" % (
                bar, bar + s.bars - 1, s.name, sum(len(v) for v in s.parts.values()),
                min(vs), max(vs), " ".join(sorted(s.parts))))
            bar += s.bars
        print("%d bars, %.2f minutes at %d BPM" % (bar - 1, (bar - 1) * 4 / TEMPO, TEMPO))
        for jump, a, b in check(secs)[:4]:
            print("  median move %.1f: %s %d -> %s %d" % (jump, a[0], a[1], b[0], b[1]))
        return
    from seeker import link
    from seeker.engine import Engine
    engine = Engine()
    try:
        if do == "build":
            have = {c["name"] for c in engine.status()["channels"]}
            for name, (sample, color, volume, pan) in BAND.items():
                if name in have:
                    continue
                made = engine.add_channel(sample, name, color, volume, pan)
                print(name, "-> channel", made["channel"], "insert", made.get("insert"),
                      made["warnings"], file=sys.stderr, flush=True)
        elif do == "rewrite":
            first = int(os.environ.get("FIRST_PATTERN", "2"))
            parts = argv[2:] or list(BAND)
            for n, sec in enumerate(secs):
                engine._song(pattern=first + n)
                for ch in parts:
                    if sec.parts.get(ch):
                        bad = engine.write_part(ch, sec.parts[ch])["problems"]
                        print("pattern %d %s %s %s" % (first + n, sec.name, ch, bad or "ok"), flush=True)
        elif do == "write":
            sections = [{"name": s.name, "color": s.color, "parts": dict(s.parts)} for s in secs]
            done = engine.write_song(sections, tempo=TEMPO, arrange=False)
            print(json.dumps({"sections": done["sections"], "problems": done["problems"],
                              "warnings": done.get("warnings")}, default=str))
    finally:
        link.close()


if __name__ == "__main__":
    main(sys.argv)
