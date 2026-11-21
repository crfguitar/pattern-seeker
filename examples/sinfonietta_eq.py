"""EQ for the Sinfonietta in D (examples/sinfonietta.py) on CFilteR-01.

    python examples/sinfonietta_eq.py          # print the ranges and the plan
    python examples/sinfonietta_eq.py apply    # set it on every channel's insert

1. Range check. Every note each instrument plays in all three movements is read
   from the score. The low cut sits at 0.65 x the lowest fundamental at
   12 dB/oct, so the lowest note in any movement loses under 1 dB.
   Contrabass and timpani only get a subsonic cut, far below their lowest notes.
2. Pockets. Each cut goes on the voice that supports in the clash, at
   1.5-3 dB with Q 2-4. Nothing is boosted. Every cut is below 4 kHz, and
   there are no high cuts or shelves, so the air above 8 kHz is untouched.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import sinfonietta as score  # noqa: E402

LOW_CUT = 0.65                      # x the lowest fundamental
SUBSONIC = {"Basses": 25, "Timpani": 30}

# (channel, Hz, dB, Q, why) - the cut goes on the supporting voice in each clash
POCKETS = [
    # cello vs bassoon / horn low-mids: the cellos own the bass line's body
    ("Bassoon", 150, -2.0, 2.5, "doubles the cello line in unison: steps back from the cello body"),
    ("Horns", 160, -2.0, 3.0, "held roots sit on the cello body"),
    ("Cellos", 400, -1.5, 3.0, "leaves the horn / viola low-mid pocket"),
    # basses under cellos: their 2nd harmonic sits on the cello fundamentals
    ("Basses", 140, -1.5, 2.5, "2nd harmonic lands on the cello fundamentals"),
    # viola vs inner winds (clarinet, horn fifth)
    ("Violas", 450, -2.0, 2.5, "clarinet's upper fundamentals; violas only accompany"),
    ("Clarinet", 260, -1.5, 3.0, "viola body; also a lead in the wind episodes, so kept light"),
    ("Horns", 520, -1.5, 3.0, "horn fifth vs viola and clarinet throat"),
    # violin I / II vs upper woodwinds
    ("Violins 2", 1200, -2.0, 2.5, "oboe formant: oboe sustains above the pulses"),
    ("Violins 2", 3000, -2.0, 2.0, "violin I's presence: the melody stays in front"),
    ("Oboe", 2800, -2.0, 3.0, "held chord tones vs violin I presence"),
    ("Flute", 1800, -1.5, 3.5, "octave double vs violin I's 2nd harmonic, narrow"),
    # timpani: boxy shell resonance, clears viola / horn; fundamentals untouched
    ("Timpani", 380, -2.0, 3.0, "boxy shell resonance over the violas and horns"),
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]


def name(m):
    return "%s%d" % (NAMES[m % 12], m // 12 - 1)


def ranges(piece):
    """{channel: {movement: (low, high)}} from every note written."""
    out = {}
    for mv in piece:
        for sec in mv["sections"]:
            for inst, notes in sec["parts"].items():
                lo, hi = out.setdefault(inst, {}).get(mv["movement"], (127, 0))
                out[inst][mv["movement"]] = (min(lo, min(n[0] for n in notes)),
                                             max(hi, max(n[0] for n in notes)))
    return out


def nice(f):
    step = 5 if f < 100 else 10
    return int(round(f / step) * step)


def plan(piece):
    rng = ranges(piece)
    bands, report = {}, []
    for inst in score.ORCHESTRA:
        per = rng.get(inst, {})
        low = min(lo for lo, _ in per.values())
        where = [mv for mv, (lo, _) in per.items() if lo == low]
        cut = SUBSONIC.get(inst) or nice(LOW_CUT * hz(low))
        ratio = hz(low) / cut
        loss = 10 * math.log10(1 + ratio ** -4)        # 12 dB/oct Butterworth
        bands[inst] = [{"shape": "low cut", "freq": cut, "slope": 12}]
        report.append((inst, per, low, where, cut, loss))
    for inst, f, gain, q, _ in POCKETS:
        bands[inst].append({"shape": "bell", "freq": f, "gain": gain, "q": q})
    return bands, report


def main(argv):
    piece = score.compose()
    bands, report = plan(piece)
    for inst, per, low, where, cut, loss in report:
        spans = "  ".join("%s %s-%s" % (mv.split(".")[0], name(lo), name(hi))
                          for mv, (lo, hi) in per.items())
        print("%-10s lowest %-4s %6.1f Hz (%s)  low cut %3d Hz, -%.1f dB there  |  %s"
              % (inst, name(low), hz(low), "/".join(w.split(".")[0] for w in where),
                 cut, loss, spans))
    if len(argv) < 2 or argv[1] != "apply":
        return
    from seeker import link
    from seeker.engine import Engine
    engine = Engine()
    try:
        for inst, wanted in bands.items():
            done = engine.eq(inst, wanted)
            print("\n%s (insert %d, slot %d)" % (inst, done["insert"], done["slot"]))
            for b in done["bands"]:
                print("   ", b)
            for w in done["warnings"]:
                print("   !", w)
    finally:
        link.close()


if __name__ == "__main__":
    main(sys.argv)
