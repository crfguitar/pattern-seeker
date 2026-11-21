"""EQ for the Divertimento in B-flat (examples/divertimento.py) on CFilteR-01,
worked out from the score rather than guessed:

    python examples/divertimento_eq.py         # ranges, clashes, the bands as JSON

1. Range check. The low cut sits at 0.65 x each part's lowest fundamental in
   ANY movement, 12 dB/oct, so its lowest note loses under 1 dB. The basses
   only get a subsonic cut (25 Hz): their fundamentals are the floor of the mix.
2. Clashes. The score is sliced into 16ths, as played (the exposition and the
   refrains count every time they come round). Whenever two parts sound
   together and one's fundamental sits within a semitone of the other's
   fundamental or 2nd harmonic, that slice counts against the pair at that
   frequency, louder notes weighing more.
3. Pockets. Each clash is cut on the SUPPORTING part: the one not carrying
   the tune at that moment (`leads`), else the lower one in PRIORITY. Clashes
   within half an octave on one part merge; the strongest two per part become
   bells of -1.5 to -3 dB (the second at most -2), deeper the more it happens, at Q 2.5-3.5. No boosts, nothing above
   4 kHz, no shelves or high cuts, so the air over 8 kHz is untouched.
"""

import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import divertimento as score  # noqa: E402

LOW_CUT = 0.65
SUBSONIC = {"Basses": 25}
# who keeps the frequency when two accompanying parts clash (first = most important)
PRIORITY = ["Violins 1", "Flute", "Oboe", "Clarinet", "Cellos", "Basses", "Horns",
            "Bassoon", "Violas", "Violins 2"]
SLICE = 0.25
MAX_POCKETS = 2
FLOOR = {"Basses": 90}          # never cut the basses' own fundamentals


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def name(m):
    return "%s%d" % (NAMES[m % 12], m // 12 - 1)


def nice(f):
    step = 5 if f < 100 else 10 if f < 1000 else 50
    return int(round(f / step) * step)


def played(piece):
    """(section, times it is played) for every section."""
    for mv in piece:
        count = collections.Counter(mv["order"])
        for i, sec in enumerate(mv["sections"]):
            yield sec, count[i]


def clashes(piece):
    """{(cut part, semitone): weight} and {(cut part, keeper): weight}."""
    where, pairs = collections.Counter(), collections.Counter()
    for sec, times in played(piece):
        slots = collections.defaultdict(dict)     # slot -> {inst: (pitch, vel)}
        for inst, notes in sec["parts"].items():
            for p, s, d, v in notes:
                k = int(round(s / SLICE))
                while k * SLICE < s + d - 1e-6:
                    old = slots[k].get(inst)
                    if old is None or v > old[1]:
                        slots[k][inst] = (p, v)
                    k += 1
        for k, sounding in slots.items():
            t = k * SLICE
            lead = {i for a, b, i in sec["leads"] if a <= t < b}
            names = sorted(sounding)
            for x in range(len(names)):
                for y in range(x + 1, len(names)):
                    a, b = names[x], names[y]
                    (pa, va), (pb, vb) = sounding[a], sounding[b]
                    if abs(pa - pb) <= 1:
                        at = min(pa, pb)
                    elif abs(pa - (pb + 12)) <= 1:      # b's 2nd harmonic on a
                        at = pa
                    elif abs(pb - (pa + 12)) <= 1:
                        at = pb
                    else:
                        continue
                    if (a in lead) != (b in lead):
                        cut, keep = (b, a) if a in lead else (a, b)
                    else:
                        cut, keep = sorted((a, b), key=PRIORITY.index, reverse=True)
                    w = times * SLICE * (va + vb) / 200.0
                    where[cut, at] += w
                    pairs[cut, keep] += w
    return where, pairs


def ranges(piece):
    out = {}
    for mv in piece:
        for sec in mv["sections"]:
            for inst, notes in sec["parts"].items():
                lo, hi = out.setdefault(inst, {}).get(mv["movement"], (127, 0))
                out[inst][mv["movement"]] = (min(lo, min(n[0] for n in notes)),
                                             max(hi, max(n[0] for n in notes)))
    return out


def pockets(where, cut_below):
    """Merge each part's clash pitches into half-octave clusters; the strongest
    become cuts at the weighted centre."""
    per = collections.defaultdict(list)
    for (inst, p), w in where.items():
        per[inst].append((p, w))
    found_by = {}
    for inst, rows in per.items():
        rows.sort()
        groups, cur = [], []
        for p, w in rows:
            if cur and p - cur[0][0] > 6:
                groups.append(cur)
                cur = []
            cur.append((p, w))
        groups.append(cur)
        found = []
        for g in groups:
            w = sum(x for _, x in g)
            centre = sum(p * x for p, x in g) / w
            f = hz(centre)
            if f < cut_below[inst] * 1.3 or f < FLOOR.get(inst, 0) or f > 4000:
                continue
            found.append((w, f))
        found.sort(reverse=True)
        found_by[inst] = found
    top = max(f[0][0] for f in found_by.values() if f)
    out = {}
    for inst, found in found_by.items():
        cuts = []
        for n, (w, f) in enumerate(found[:MAX_POCKETS]):
            share = w / top
            if share < 0.06:
                continue
            depth = min(3.0 if n == 0 else 2.0, 1.5 + 1.5 * min(1.0, share))
            gain = -round(depth * 2) / 2
            q = 3.5 if f > 1000 else 3.0 if f > 300 else 2.5
            cuts.append({"shape": "bell", "freq": nice(f), "gain": gain, "q": q, "weight": w})
        out[inst] = cuts
    return out


def main():
    piece = score.compose()
    rng = ranges(piece)
    lowcut, bands = {}, {}
    print("RANGES (all movements)")
    for inst in score.ORCHESTRA:
        per = rng[inst]
        low = min(lo for lo, _ in per.values())
        cut = SUBSONIC.get(inst) or nice(LOW_CUT * hz(low))
        loss = 10 * math.log10(1 + (hz(low) / cut) ** -4)
        lowcut[inst] = cut
        print("  %-10s lowest %-4s %6.1f Hz -> low cut %3d Hz (-%.2f dB at that note)  | %s"
              % (inst, name(low), hz(low), cut, loss,
                 "  ".join("%s %s-%s" % (mv.split(".")[0], name(a), name(b))
                           for mv, (a, b) in per.items())))
    where, pairs = clashes(piece)
    print("\nWORST CLASHES (cut part <- keeps the frequency, weight)")
    for (cut, keep), w in pairs.most_common(14):
        print("  %-10s <- %-10s %7.1f" % (cut, keep, w))
    cuts = pockets(where, lowcut)
    print("\nPLAN")
    for inst in score.ORCHESTRA:
        bands[inst] = [{"shape": "low cut", "freq": lowcut[inst], "slope": 12}]
        for c in cuts.get(inst, []):
            print("  %-10s bell %5d Hz %+.1f dB Q %.1f  (weight %.1f)"
                  % (inst, c["freq"], c["gain"], c["q"], c["weight"]))
            bands[inst].append({k: c[k] for k in ("shape", "freq", "gain", "q")})
    print("\n" + json.dumps(bands))


if __name__ == "__main__":
    main()
