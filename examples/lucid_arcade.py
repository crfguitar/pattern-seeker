"""Lucid Arcade - an original instrumental in a Pi'erre Bourne vein: bright, bouncy,
a little video-game, 154 BPM half-time, E major, with room for a rapper.

    python examples/lucid_arcade.py          # compose, print the plan and the checks
    python examples/lucid_arcade.py build    # add the channels
    python examples/lucid_arcade.py write    # write the patterns (lay them out with arrange)
    python examples/lucid_arcade.py rewrite Lead 808   # new notes, playlist kept

Drums, 808 and FX come only from the Producergrind "Life of Pierre" kit (its 808s
are all tuned to C: note 60 = C1). The melody is hand-written for FLEX synths: a
square pluck lead, Juno bells answering it, a Juno pad under. The kit's "Signature"
vox (most likely the producer tag) is left out on purpose.

The loop: Amaj9 | G#m7 | F#m9 | B6 - IV iii ii V in E that never lands on I, so it
floats. The 808 bounces on its own rhythm (kick on its first hit of each group),
jumps the octave into every fourth bar. The bridge turns to C#m9 | Amaj7 | E/G# |
F#m7 B.

Form (bars): Intro 8 | Hook 16 | Verse 1 16 | Hook 16 | Bridge 8 | Verse 2 16
             | Hook 16 | Outro 8 = 104 bars, 2:42.
"""

import collections
import json
import os
import random
import statistics
import sys

TEMPO = 154
SAMPLES = os.environ.get("PATTERN_SEEKER_SAMPLES", os.path.join(os.path.expanduser("~"), "Music", "Samples"))
KIT = os.path.join(SAMPLES, r"LIFE OF PIERRE Drum Kit\LIFE OF PIERRE Drum Kit (Producergrind)")

# channel: (sound, colour, volume, pan). Hats left (drum-panning memory).
BAND = {
    "Kick": (KIT + r"\PG LOP - Kicks\PG LOP Kick 03.wav", "#C8553D", 0.76, 0.0),
    "Snare": (KIT + r"\PG LOP - Snares\PG LOP Snare - No Lie.wav", "#E0A33A", 0.62, 0.0),
    "Clap": (KIT + r"\PG LOP - Snares\PG LOP Clap 01.wav", "#E8C15A", 0.44, 0.0),
    "Hat": (KIT + r"\PG LOP - Hihats\PG LOP Hihat - Classic.wav", "#D9CB5E", 0.42, -0.15),
    "Perc": (KIT + r"\PG LOP - Percs\PG LOP Perc - Classic.wav", "#A8B05A", 0.30, 0.20),
    "Triangle": (KIT + r"\PG LOP - Percs\PG LOP Perc - Nudy Triangle.wav", "#BFAE7A", 0.24, 0.30),
    "808": (KIT + r"\PG LOP - 808s\PG LOP 808 - Let It Go - C.wav", "#7A4FA0", 0.50, 0.0),
    "Laser": (KIT + r"\PG LOP - FX\PG LOP FX - Switched On Me Lazer.wav", "#708090", 0.30, 0.0),
    "Hit": (KIT + r"\PG LOP - FX\PG LOP FX - Ballad Hit.wav", "#8A8A8A", 0.32, 0.0),
    "Lead": ("FLEX/Mobile Synth Pluck/Synpluck Glass", "#4FB0C0", 0.50, 0.0),
    "Bells": ("FLEX/Saif Sameer Synthwave/Juno Bells", "#7FC0E0", 0.32, 0.25),
    "Pad": ("FLEX/Saif Sameer Synthwave/Juno Super Pad", "#5A6FA8", 0.36, 0.0),
}
ONCE = {"Laser", "Hit"}                                  # FX keep their own level

# ---- harmony ------------------------------------------------------------------------------
LOOP = ["Amaj9", "G#m7", "F#m9", "B6"]
BRIDGE = ["C#m9", "Amaj7", "E/G#", "F#m7 B"]
PAD = {"Amaj9": (57, 64, 68, 71, 73), "G#m7": (56, 63, 66, 71), "F#m9": (54, 61, 64, 68, 69),
       "B6": (59, 63, 66, 68), "C#m9": (56, 61, 64, 71, 75), "Amaj7": (57, 61, 64, 68),
       "E/G#": (56, 64, 68, 71), "F#m7": (54, 61, 64, 69), "B": (59, 63, 66, 71)}
# 808: C1 sample at note 60. A1 69, G#1 68, F#1 66, B1 71, C#2 73, E1 64.
BASS = {"Amaj9": 69, "G#m7": 68, "F#m9": 66, "B6": 71, "C#m9": 73, "Amaj7": 69,
        "E/G#": 68, "F#m7": 66, "B": 71}
BELL = {"Amaj9": (85, 88, 92), "G#m7": (83, 87, 90), "F#m9": (85, 88, 92), "B6": (83, 87, 90)}

# the hook melody, (pitch, beat, length); E5 = 76
HOOK_LEAD = [
    [(80, 0, .5), (76, .5, .5), (83, 1, .75), (80, 1.75, .75), (76, 2.5, .5), (80, 3, .5), (81, 3.5, .5)],
    [(83, 0, .75), (80, .75, .75), (78, 1.5, .5), (75, 2, 1), (78, 3, .5), (80, 3.5, .5)],
    [(80, 0, .5), (76, .5, .5), (85, 1, .75), (83, 1.75, .75), (80, 2.5, .5), (76, 3, .5), (78, 3.5, .5)],
    [(78, 0, .75), (75, .75, .75), (71, 1.5, .5), (75, 2, .5), (78, 2.5, .5), (80, 3, 1)],
]
HOOK_END = [(83, 0, .75), (80, .75, .75), (78, 1.5, 1.5), (87, 3, .5), (83, 3.5, .5)]   # every 8th bar
BRIDGE_LEAD = [
    [(87, 0, 1.5), (85, 1.5, .5), (83, 2, 2)],
    [(81, 0, 1), (80, 1, 1), (76, 2, 2)],
    [(80, 0, 1.5), (83, 1.5, .5), (88, 2, 2)],
    [(85, 0, 2), (87, 2, 1), (83, 3, 1)],
]

# 808 groups per bar, (beat, length); the kick takes the first of each group
B808 = [[(0, 1.5), (1.5, 1.0), (2.5, 1.5)],
        [(0, .75), (.75, .75), (1.5, 1.0), (2.75, 1.25)],
        [(0, 1.5), (1.5, 1.0), (2.5, 1.0), (3.5, .5)],
        [(0, .75), (.75, 1.75), (2.5, .75), (3.25, .75)]]
KICK_AT = [{0, 2.5}, {0, .75, 2.75}, {0, 2.5}, {0, 2.5}]

LEVEL = {"Intro": -6, "Hook 1": 3, "Verse 1": -2, "Hook 2": 4, "Bridge": -5,
         "Verse 2": -1, "Hook 3": 5, "Outro": -6}


class Sec:
    def __init__(self, name, bars, color):
        self.name, self.bars, self.color = name, bars, color
        self.parts = collections.defaultdict(list)

    def add(self, ch, pitch, start, length, vel):
        self.parts[ch].append([pitch, round(start, 4), round(length, 4), vel])


def hit(s, rng, ch, t, vel, pitch=60, length=0.2):
    s.add(ch, pitch, max(0.0, t + rng.uniform(-0.005, 0.005)), length, vel + rng.randint(-3, 3))


def chords(s, bars, prog=LOOP, vel=68):
    for i in range(bars):
        name = prog[i % 4]
        if name == "F#m7 B":
            for j, (c, at) in enumerate((("F#m7", 0), ("B", 2))):
                for k, p in enumerate(PAD[c]):
                    s.add("Pad", p, i * 4 + at, 1.95, vel - k)
            continue
        for k, p in enumerate(PAD[name]):
            s.add("Pad", p, i * 4, 3.95, vel - k)


def bells(s, rng, bars, vel=72, from_bar=0):
    """Three chord tones rising, then the middle one twice: the verses' sparkle."""
    for i in range(from_bar, bars):
        lo, mid, hi = BELL[LOOP[i % 4]]
        for at, p in ((0, lo), (0.75, mid), (1.5, hi), (2.5, mid), (3.25, lo)):
            hit(s, rng, "Bells", i * 4 + at, vel - (4 if at > 2 else 0), p, 0.6)


def hook_bells(s, rng, bars, vel=76, phrase=HOOK_LEAD, end=HOOK_END, from_bar=0):
    """The hook's signal now the lead is gone (the user found it too intrusive): the
    old melody's skeleton on the bells - only its notes that fall on a beat, held to
    the next one - so the hook keeps its shape at a whisper."""
    for i in range(from_bar, bars):
        bar = end if end and i % 8 == 7 else phrase[i % 4]
        on = [(p, at) for p, at, _ in bar if at == int(at)]
        for j, (p, at) in enumerate(on):
            nxt = on[j + 1][1] if j + 1 < len(on) else 4
            hit(s, rng, "Bells", i * 4 + at, vel - (3 if at else 0), p, min(nxt - at, 2) - 0.05)


def lead(s, rng, bars, vel=84, phrase=HOOK_LEAD, end=HOOK_END, from_bar=0):
    """No longer called: the user took the lead out. Kept for the melody's record."""
    for i in range(from_bar, bars):
        bar = end if end and i % 8 == 7 else phrase[i % 4]
        for p, at, length in bar:
            accent = 4 if at in (0, 1, 2, 3) else 0
            hit(s, rng, "Lead", i * 4 + at, vel + accent, p, length - 0.04)


def bass(s, rng, bars, prog=LOOP, kicks=True, octave=True):
    for i in range(bars):
        t = i * 4
        name = prog[i % 4]
        groups = B808[i % 4]
        for j, (at, length) in enumerate(groups):
            c = name
            if name == "F#m7 B":
                c = "F#m7" if at < 2 else "B"
            root = BASS[c]
            up = octave and i % 4 == 3 and j == len(groups) - 1   # the octave jump into the loop
            s.add("808", root + (12 if up else 0), t + at, length - 0.03, 92 if at == 0 else 84)
            if kicks and at in KICK_AT[i % 4]:
                hit(s, rng, "Kick", t + at, 94 if at == 0 else 86)


def drums(s, rng, bars, busy=False, fill=True, triangle=True):
    for i in range(bars):
        t = i * 4
        last = i == bars - 1
        hit(s, rng, "Snare", t + 2, 92)
        hit(s, rng, "Clap", t + 2.01, 80)
        if i % 4 == 3 and not last:
            hit(s, rng, "Snare", t + 3.75, 64)            # a ghost into the next phrase
        if last and fill:
            for k, v in ((3, 66), (3.25, 72), (3.5, 78), (3.75, 86)):
                hit(s, rng, "Snare", t + k, v)
        for k in range(8):                               # 8ths, the bounce on the offbeats
            if last and fill and k >= 6:
                break
            hit(s, rng, "Hat", t + k * 0.5, 74 if k % 2 == 0 else 64, length=0.08)
        if i % 2 == 1 and not (last and fill):            # a burst: 16th triplets over beat 3
            for r in range(3):
                hit(s, rng, "Hat", t + 3 + r / 6, 60 + r * 4, length=0.05)
        if busy:
            for k in (0.75, 1.75):
                hit(s, rng, "Hat", t + k, 58, length=0.05)
        hit(s, rng, "Perc", t + (1.5 if i % 2 == 0 else 3.5), 66)
        if triangle and i % 4 == 1:
            hit(s, rng, "Triangle", t + 1, 68, length=0.3)


# ---- sections -----------------------------------------------------------------------------
def intro(rng):
    s = Sec("Intro", 8, "#5A6FA8")
    chords(s, 8, vel=66)
    bells(s, rng, 4, vel=70)
    hook_bells(s, rng, 8, vel=72, from_bar=4)             # the hook's shape arrives halfway
    for k in range(8):                                   # hats tease the drop
        hit(s, rng, "Hat", 24 + k * 0.5, 58 + k * 2, length=0.08)
    s.add("Laser", 60, 30.5, 1.5, 80)                    # into the drop
    return s


def hook(name, rng):
    s = Sec(name, 16, "#4FB0C0")
    s.add("Hit", 60, 0, 1.5, 84)
    chords(s, 16)
    hook_bells(s, rng, 16)
    bass(s, rng, 16)
    drums(s, rng, 16, busy=True, fill=name != "Hook 3")
    return s


def verse(name, rng, busy):
    s = Sec(name, 16, "#7A8FC0")
    s.add("Hit", 60, 0, 1.5, 76)
    chords(s, 16, vel=66)
    bells(s, rng, 16, vel=68)                             # the lead rests: the rapper's room
    bass(s, rng, 16)
    drums(s, rng, 16, busy=busy)
    s.add("Laser", 60, 62.5, 1.5, 76)
    return s


def bridge(rng):
    s = Sec("Bridge", 8, "#5A6FA8")
    chords(s, 8, BRIDGE, vel=70)
    hook_bells(s, rng, 8, vel=74, phrase=BRIDGE_LEAD, end=None)
    for i in range(8):                                   # the 808 long, one per chord
        name = BRIDGE[i % 4]
        if name == "F#m7 B":
            s.add("808", BASS["F#m7"], i * 4, 1.95, 80)
            s.add("808", BASS["B"], i * 4 + 2, 1.95, 82)
        else:
            s.add("808", BASS[name], i * 4, 3.9, 82)
        hit(s, rng, "Snare", i * 4 + 2, 84)
        for k in range(4):
            hit(s, rng, "Hat", i * 4 + k + 0.5, 62, length=0.08)
    for k, v in ((31, 66), (31.25, 72), (31.5, 78), (31.75, 86)):
        hit(s, rng, "Snare", k, v)
    return s


def outro(rng):
    s = Sec("Outro", 8, "#5A6FA8")
    chords(s, 8, vel=64)
    hook_bells(s, rng, 4, vel=70)
    bells(s, rng, 8, vel=66, from_bar=4)
    bass(s, rng, 4, octave=False)
    drums(s, rng, 4, fill=False, triangle=False)
    s.add("808", BASS["Amaj9"], 16, 7.9, 74)              # rings out under the last chords
    return s


def compose(seed=154):
    rng = random.Random(seed)
    secs = [intro(rng), hook("Hook 1", rng), verse("Verse 1", rng, False), hook("Hook 2", rng),
            bridge(rng), verse("Verse 2", rng, True), hook("Hook 3", rng), outro(rng)]
    for i, s in enumerate(secs):
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        end = s.bars * 4
        for ch, notes in s.parts.items():
            for n in notes:
                if ch not in ONCE:
                    ramp = max(0.0, (n[1] - (end - 8)) / 8) * (nxt - level) * 0.5
                    n[3] = int(round(min(100, max(50, n[3] + level + ramp))))
                n[1] = round(max(0.0, n[1]), 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)
        if s.name == "Outro":                            # fade the last four bars
            for ch, notes in s.parts.items():
                for n in notes:
                    if n[1] >= 16 and ch not in ONCE:
                        n[3] = max(50, n[3] - int((n[1] - 16) / 16 * 10))
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
    secs = compose()
    if do == "plan":
        bar = 1
        for s in secs:
            vs = [n[3] for ch, ns in s.parts.items() if ch not in ONCE for n in ns] or [0]
            print("bars %3d-%3d  %-8s %4d notes  vel %d-%d  %s" % (
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
            for name, (sound, color, volume, pan) in BAND.items():
                if name in have:
                    continue
                made = engine.add_channel(sound, name, color, volume, pan)
                print(name, "-> channel", made["channel"], "insert", made.get("insert"),
                      made["warnings"], file=sys.stderr, flush=True)
        elif do == "rewrite":
            first = int(os.environ.get("FIRST_PATTERN", "2"))
            parts = argv[2:] or list(BAND)
            for n, sec in enumerate(secs):
                engine._song(pattern=first + n)
                for ch in parts:
                    if not sec.parts.get(ch) and argv[2:]:      # named but silent here: clear it
                        engine.clear_part(ch)
                        print("pattern %d %s %s cleared" % (first + n, sec.name, ch), flush=True)
                    elif sec.parts.get(ch):
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
