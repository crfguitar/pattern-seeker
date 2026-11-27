"""Crate Weather - a hand-written instrumental in the style of Madlib-era
underground hip hop, C minor, 88 BPM, with room for a rapper.

    python examples/crate_weather.py          # compose, print the plan and the checks
    python examples/crate_weather.py build    # add the twelve channels
    python examples/crate_weather.py write    # write the patterns, lay out the song
    python examples/crate_weather.py rewrite Rhodes Flute   # new notes, playlist kept

What makes it that style:
  * Drums from the user's MF DOOM kit (the "Doomsday" kick, snare and hat),
    loose and swung: MPC-style 16th swing, the snare a hair late, small
    timing and velocity drift, ghost rims, a drop-out at the end of phrases.
  * A four-bar "sample" loop on a dusty Rhodes (chopped rhythm, chords pushed
    ahead of the bar): Cm9 | Abmaj9 | Dbmaj7 (the odd bII turn) | G7alt.
  * A tape-saturated electric bass, lazy and low, approach notes into each bar.
  * Flute and vibes for the hook; scratchy organ under it; tambourine and
    shaker; a turntable scratch at the joins.
  * Room for the rapper: in the verses only drums, bass and the Rhodes play
    (the Rhodes softer), with a short vibes answer in the last beat of every
    fourth bar, where a line usually ends. No melody under the voice.

Form (bars): Intro 8 | Verse 1 16 | Hook 8 | Verse 2 16 | Hook 8 | Break 4
             | Verse 3 16 | Hook 8 | Outro 8 = 92 bars, about 4:11.

Dynamics per the Divertimento rules: LEVEL per section, eased over the last
two bars, velocities kept within 50-100.
"""

import collections
import json
import os
import random
import statistics
import sys

TEMPO = 88
SAMPLES = os.environ.get("PATTERN_SEEKER_SAMPLES", os.path.join(os.path.expanduser("~"), "Music", "Samples"))
KIT = os.path.join(SAMPLES, r"MF DOOM KIT\The Lunch77 MF DOOM Drumkit")

# channel: (sound, colour, volume, pan)
BAND = {
    "Doom Kick": (KIT + r"\Kicks\Kick (Doomsday).wav", "#B5523B", 0.85, 0.0),
    "Doom Snare": (KIT + r"\Snares\Snare (Doomsday).wav", "#D9963A", 0.72, 0.0),
    "Doom Hat": (KIT + r"\Closed Hats\HiHat (Doomsday).wav", "#CDBF5A", 0.40, 0.22),
    "Rim": (KIT + r"\Snares\Glassy Rim.wav", "#A8B05A", 0.38, -0.15),
    "Tambourine": (KIT + r"\Percs\3 perc -tambourine.wav", "#C9A55A", 0.30, 0.35),
    "Shaker": (KIT + r"\Crashes & Cymbals\SHAKER I.wav", "#BFAE7A", 0.28, -0.30),
    "Scratch": (KIT + r"\FX\Binky Rules - Turntable scratch.wav", "#8A8A8A", 0.42, 0.0),
    "Tape Bass": ("FLEX/Chill-Lo-Fi/Old Tape Electric Bass", "#7A4FA0", 0.58, 0.0),
    "Rhodes": ("FLEX/Chill-Lo-Fi/Dusty Rhodes", "#C07A3A", 0.56, -0.05),
    "Vibes": ("FLEX/General Midi Library/Vibraphone", "#5FA8B8", 0.40, -0.28),
    "Flute": ("FLEX/Chill-Lo-Fi/Fluffy Flute", "#7FBF7A", 0.44, 0.18),
    "Organ": ("FLEX/Chill-Lo-Fi/Lofi Scratchy Organ", "#6F6FA8", 0.28, 0.0),
}

# ---- harmony (C4 = 60) ------------------------------------------------------------------
LOOP = ["Cm9", "Abmaj9", "Dbmaj7", "G7alt"]
RHODES = {   # rootless, moving by step: Bb D Eb G -> G Bb C Eb -> F Ab C Eb -> F B Eb Ab
    "Cm9": [58, 62, 63, 67], "Abmaj9": [55, 58, 60, 63],
    "Dbmaj7": [53, 56, 60, 63], "G7alt": [53, 59, 63, 68],
}
ORGAN = {    # the shell an octave over: third and seventh
    "Cm9": [63, 70], "Abmaj9": [67, 72], "Dbmaj7": [65, 72], "G7alt": [65, 71],
}
ROOT = {"Cm9": 36, "Abmaj9": 32, "Dbmaj7": 37, "G7alt": 31}   # C2 Ab1 Db2 G1: a real bass

LEVEL = {"Intro": -6, "Verse 1": -3, "Hook 1": 4, "Verse 2": -2, "Hook 2": 5,
         "Break": -5, "Verse 3": -1, "Hook 3": 6, "Outro": -4}

# ---- tunes --------------------------------------------------------------------------------
HOOK_A = ("r:0.5 G5:0.5 Bb5:0.5 C6:1.5 Bb5:1 | G5:2 Eb5:1 F5:1"
          " | Eb5:0.5 F5:0.5 Ab5:1.5 G5:0.5 F5:1 | Eb5:1.5 B4:0.5 r:2")
HOOK_B = ("r:0.5 G5:0.5 Bb5:0.5 C6:1 D6:0.5 Eb6:1 | D6:1.5 C6:0.5 Bb5:1 G5:1"
          " | Ab5:1 G5:0.5 F5:0.5 Eb5:1 C5:1 | B4:2 r:2")
INTRO_FLUTE = "r:2 G5:1 Bb5:1 | C6:3 Bb5:1 | Ab5:2 G5:1 F5:1 | Eb5:2 D5:0.5 B4:1.5"
ANSWERS = [  # vibes, the last beat of every fourth bar (beats from that bar's start)
    [("G5", 3.0, 0.4), ("Bb5", 3.33, 0.4), ("C6", 3.67, 0.6)],
    [("Eb6", 3.0, 0.3), ("D6", 3.25, 0.3), ("B5", 3.5, 0.5)],
    [("F5", 3.0, 0.4), ("Ab5", 3.33, 0.4), ("B5", 3.67, 0.6)],
    [("C6", 3.25, 0.3), ("G5", 3.5, 0.3), ("Eb5", 3.75, 0.5)],
]
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name):
    pc, rest = PC[name[0]], name[1:]
    while rest and rest[0] in "#b":
        pc += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + pc


class Sec:
    def __init__(self, name, bars, color):
        self.name, self.bars, self.color = name, bars, color
        self.parts = collections.defaultdict(list)

    def add(self, ch, pitch, start, length, vel):
        self.parts[ch].append([pitch, start, length, vel])


def tune(s, text, bar, vel, ch="Flute", shift=0, legato=0.9):
    t = bar * 4
    for b, chunk in enumerate(text.split("|")):
        at = 0.0
        for tok in chunk.split():
            name, length = tok.split(":")
            length = float(length)
            if name != "r":
                accent = 3 if at == 0 else 0
                s.add(ch, midi(name) + shift, t + b * 4 + at, length * legato, vel + accent)
            at += length


# ---- the loop -------------------------------------------------------------------------------
# The Rhodes plays like a chopped record: a long hit, a short restrike, and the
# next chord pushed in a sixteenth early (it belongs to the next bar).
CHOP = [(0.0, 1.35, 0), (1.5, 0.4, -6), (2.75, 0.9, -3)]


def rhodes(s, bar, bars, vel, chop=CHOP):
    for i in range(bars):
        c, t = LOOP[i % 4], (bar + i) * 4
        nxt = LOOP[(i + 1) % 4]
        for at, length, dv in chop:
            for k, p in enumerate(RHODES[c]):
                s.add("Rhodes", p, round(t + at + k * 0.012, 4), length, vel + dv - k)
        if i % 4 != 3 and i < bars - 1:                      # the push into the next chord
            for k, p in enumerate(RHODES[nxt]):
                s.add("Rhodes", p, round(t + 3.75 + k * 0.012, 4), 0.2, vel - 8 - k)


def bass(s, bar, bars, vel, busy=True):
    """Lazy and low: root, a fifth or octave late in the bar, a slide in."""
    for i in range(bars):
        c, t = LOOP[i % 4], (bar + i) * 4
        r, nxt = ROOT[c], ROOT[LOOP[(i + 1) % 4]]
        s.add("Tape Bass", r, t + 0.02, 1.3, vel + 4)
        s.add("Tape Bass", r, t + 1.81, 0.4, vel - 6)
        s.add("Tape Bass", r + (7 if c != "G7alt" else 12), t + 2.5, 0.9, vel - 2)
        if busy and i < bars - 1:
            # chromatic approach: from above when the next root is lower, else from below
            s.add("Tape Bass", nxt + (1 if nxt <= r else -1), t + 3.5, 0.45, vel - 4)
        elif busy:
            s.add("Tape Bass", r + 12, t + 3.5, 0.4, vel - 6)


def organ(s, bar, bars, vel):
    for i in range(bars):
        c, t = LOOP[i % 4], (bar + i) * 4
        for k, p in enumerate(ORGAN[c]):
            s.add("Organ", p, t, 3.9, vel - k)


def answers(s, bar, bars, vel, rng):
    for i in range(3, bars, 4):
        for name, at, length in ANSWERS[rng.randrange(4)]:
            s.add("Vibes", midi(name) - 12, (bar + i) * 4 + at, length, vel)


# ---- drums (sampler channels: 60 plays the sample as recorded) ---------------------------
SWING = 0.06          # odd sixteenths this many beats late: about 62% MPC swing


def sw(k):
    return k * 0.25 + (SWING if k % 2 else 0)


def hit(s, rng, ch, t, vel, pitch=60, length=0.25, drift=0.012):
    t = t + rng.uniform(-drift, drift)
    s.add(ch, pitch, round(max(0.0, t), 4), length, vel + rng.randint(-3, 3))


KICKS = [(0, 90), (7, 72), (10, 84)], [(0, 90), (3, 70), (10, 82), (13, 70)]


def drums(s, bar, bars, rng, shaker=False, tamb=False, drop_end=True):
    for i in range(bars):
        t = (bar + i) * 4
        last = i == bars - 1
        drop = drop_end and last                        # beat 4 drops out for the punchline
        phrase_end = i % 8 == 7 and not last
        for k, v in KICKS[i % 2]:
            if drop and k >= 12:
                continue
            hit(s, rng, "Doom Kick", t + sw(k), v)
        for beat in (1, 3):
            if drop and beat == 3:
                continue
            hit(s, rng, "Doom Snare", t + beat + 0.025, 88, drift=0.006)
            if tamb:
                hit(s, rng, "Tambourine", t + beat + 0.04, 70)
        if phrase_end:                                   # a lazy drag into the next eight
            hit(s, rng, "Doom Snare", t + sw(15), 62)
            hit(s, rng, "Doom Snare", t + 3.5 + 0.025, 70)
        for g in (6, 14):                                # ghost rims
            if rng.random() < 0.6 and not (drop and g >= 12):
                hit(s, rng, "Rim", t + sw(g) + 0.01, 56)
        for k in range(0, 16, 2):                        # hats on the eighths...
            if drop and k >= 12:
                continue
            hit(s, rng, "Doom Hat", t + sw(k), 74 if k % 4 == 0 else 64)
        for k in (3, 11, 15):                            # ...and a few swung sixteenths
            if rng.random() < 0.45 and not (drop and k >= 12):
                hit(s, rng, "Doom Hat", t + sw(k), 54)
        if shaker:
            for k in range(0, 16, 2):
                hit(s, rng, "Shaker", t + sw(k + 1), 62 if k % 4 else 58)
        if drop:
            hit(s, rng, "Scratch", t + 3.0, 74, length=0.9, drift=0)


def scratch(s, rng, t, vel=72):
    for k, p in enumerate((60, 62, 58)):
        hit(s, rng, "Scratch", t + k * 0.25, vel - k * 3, pitch=p, length=0.24, drift=0)


# ---- sections ----------------------------------------------------------------------------
def intro(rng):
    s = Sec("Intro", 8, "#C07A3A")
    rhodes(s, 0, 8, 70)                                   # the record on its own
    tune(s, INTRO_FLUTE, 4, 70)
    for i in range(4, 8):
        for k in range(0, 16, 2):
            hit(s, rng, "Shaker", (i * 4) + sw(k + 1), 58)
    bass(s, 6, 2, 70, busy=False)                        # the bass leans in at the end
    scratch(s, rng, 31.0)
    return s


def verse(name, rng, n):
    s = Sec(name, 16, "#5A7FA8")
    rhodes(s, 0, 16, 64)                                  # softer under the voice
    bass(s, 0, 16, 76)
    drums(s, 0, 16, rng, shaker=n == 3)
    answers(s, 0, 16, 60, rng)
    return s


def hook(name, rng, n):
    s = Sec(name, 8, "#7FBF7A")
    rhodes(s, 0, 8, 70)
    bass(s, 0, 8, 78)
    organ(s, 0, 8, 60)
    tune(s, HOOK_A, 0, 76)
    tune(s, HOOK_B, 4, 78)
    if n >= 2:                                            # the vibes double the flute an octave down
        tune(s, HOOK_A, 0, 64, ch="Vibes", shift=-12, legato=0.6)
        tune(s, HOOK_B, 4, 66, ch="Vibes", shift=-12, legato=0.6)
    drums(s, 0, 8, rng, shaker=True, tamb=True, drop_end=n != 3)
    return s


def break_(rng):
    """Drums out: the Rhodes chopped in stutters, bass and scratches, then a fill."""
    s = Sec("Break", 4, "#8A5A3A")
    stutter = [(k * 0.25, 0.2, -4 if k % 2 else 0) for k in range(8)] + [(2.75, 1.0, -2)]
    rhodes(s, 0, 2, 66)
    rhodes(s, 2, 1, 66, chop=stutter)
    for k, p in enumerate(RHODES["G7alt"]):
        s.add("Rhodes", p, 12 + k * 0.012, 3.5, 70 - k)
    for i, c in enumerate(LOOP):
        s.add("Tape Bass", ROOT[c], i * 4 + 0.02, 3.6, 72)
    scratch(s, rng, 3.5)
    scratch(s, rng, 7.5)
    scratch(s, rng, 11.0, 70)
    for k in range(8):                                    # the drums come back: a fill
        hit(s, rng, "Doom Snare", 14 + k * 0.25 + (SWING if k % 2 else 0), 62 + k * 3)
    hit(s, rng, "Doom Kick", 12, 84)
    hit(s, rng, "Doom Kick", 13.5, 80)
    return s


def outro(rng):
    s = Sec("Outro", 8, "#C07A3A")
    rhodes(s, 0, 4, 66)
    bass(s, 0, 4, 72)
    drums(s, 0, 4, rng, shaker=True, drop_end=False)
    tune(s, HOOK_A, 0, 68)
    rhodes(s, 4, 3, 62)
    tune(s, INTRO_FLUTE, 4, 64)
    for k, p in enumerate(RHODES["Cm9"]):                 # back home: a held Cm9
        s.add("Rhodes", p, 28 + k * 0.03, 4, 62 - k)
    s.add("Tape Bass", ROOT["Cm9"], 28.02, 3.5, 66)
    scratch(s, rng, 31.0, 64)
    return s


def compose(seed=1974):
    rng = random.Random(seed)
    secs = [intro(rng), verse("Verse 1", rng, 1), hook("Hook 1", rng, 1),
            verse("Verse 2", rng, 2), hook("Hook 2", rng, 2), break_(rng),
            verse("Verse 3", rng, 3), hook("Hook 3", rng, 3), outro(rng)]
    for i, s in enumerate(secs):
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        end = s.bars * 4
        for notes in s.parts.values():
            for n in notes:
                ramp = max(0.0, (n[1] - (end - 8)) / 8) * (nxt - level) * 0.5
                n[3] = int(round(min(100, max(50, n[3] + level + ramp))))
                n[1] = round(n[1], 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)
    return secs


def check(secs):
    meds = []
    for s in secs:
        for b in range(s.bars):
            vs = [n[3] for ns in s.parts.values() for n in ns if b * 4 <= n[1] < b * 4 + 4]
            meds.append((s.name, b + 1, statistics.median(vs) if vs else None))
    return sorted(((abs(b[2] - a[2]), a, b) for a, b in zip(meds, meds[1:]) if a[2] and b[2]),
                  reverse=True)


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    secs = compose()
    do = argv[1] if len(argv) > 1 else "plan"
    if do == "plan":
        bar = 1
        for s in secs:
            vs = [n[3] for ns in s.parts.values() for n in ns]
            print("bars %3d-%3d  %-8s %4d notes  vel %d-%d  %s" % (
                bar, bar + s.bars - 1, s.name, len(vs), min(vs), max(vs), ", ".join(sorted(s.parts))))
            bar += s.bars
        print("%d bars, %.2f minutes at %d BPM" % (bar - 1, (bar - 1) * 4 / TEMPO, TEMPO))
        for jump, a, b in check(secs)[:3]:
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
                    if sec.parts.get(ch):
                        bad = engine.write_part(ch, sec.parts[ch])["problems"]
                        print("pattern %d %s %s %s" % (first + n, sec.name, ch, bad or "ok"), flush=True)
        elif do == "write":
            sections = [{"name": s.name, "color": s.color, "parts": dict(s.parts)} for s in secs]
            done = engine.write_song(sections, tempo=TEMPO, track=1)
            print(json.dumps({"sections": [(s["section"], s["pattern"]) for s in done["sections"]],
                              "arrangement": done.get("arrangement"),
                              "problems": done["problems"],
                              "warnings": done.get("warnings")}, default=str))
    finally:
        link.close()


if __name__ == "__main__":
    main(sys.argv)
