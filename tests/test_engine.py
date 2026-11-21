"""The headless engine and the MCP server, against the real FL script on a fake rack.

    python -m unittest discover tests
"""

import asyncio
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_seeker import FakeRack, load_script, Event  # noqa: E402
from seeker import engine as engine_mod, link, sounds as real_sounds, wire  # noqa: E402
from seeker.engine import Engine, SeekerError, resolve_genre, resolve_key  # noqa: E402
from seeker.generator import KEYS  # noqa: E402


class FakeLink:
    """link's module API, delivered straight into the FL script in-process."""

    def __init__(self, rack, script):
        self.rack, self.script = rack, script
        self.responses, self.n = {}, 0
        self.closed = False

    def _drain(self):
        asm, out = wire.Assembler(), []
        for packet in self.rack.sent:
            done = asm.feed(packet)
            if done:
                out.append(done)
        del self.rack.sent[:]
        return out

    def heartbeat(self):
        self.script._heartbeat()
        found = None
        for kind, body in self._drain():
            if kind == wire.HEARTBEAT:
                found = body
        return found

    def send(self, req):
        self.n += 1
        req = dict(req, id=str(self.n))
        for packet in wire.encode(wire.REQUEST, self.n % 100, req):
            self.script.OnSysEx(Event(packet))
        for kind, body in self._drain():
            if kind == wire.RESPONSE:
                self.responses[body["id"]] = body
        return req["id"]

    def response(self, request_id):
        return self.responses.pop(request_id, None)

    def problem(self):
        return ""
    script_version = staticmethod(link.script_version)

    def close(self):
        self.closed = True


class FakePianoRoll:
    """Stands in for the window automation: 'running' the script lands an edit."""

    def __init__(self, script):
        self.script, self.written = script, []
        self.tile = engine_mod.pianoroll.tile
        self.MAX_STEPS = engine_mod.pianoroll.MAX_STEPS

    def write_script(self, notes):
        self.written.append(notes)
        return True

    def find_piano_roll(self):
        return 1

    def bring_forward(self, hwnd):
        return True

    def run_from_menu(self, hwnd):
        self.script.OnRefresh(0x20000)      # what FL reports when a roll script edits
        rack = getattr(self, "rack", None)
        if rack is not None and self.written and self.written[-1]:
            # like FL, the pattern grows to the bar its last note ends in
            end = max(s + l for _, s, l, _ in self.written[-1])
            bars = int(-(-end // 16))
            rack.length_beats[rack.pattern] = max(rack.length_beats.get(rack.pattern, 0),
                                                  bars * 4)
        return True

    def press_run_last_script(self):
        pass

    def close_script_dialogs(self):
        return False


class EngineFixture(unittest.TestCase):
    """A fake rack running the real FL script, wired to a fresh engine."""

    def setUp(self):
        self.rack = FakeRack(["Kick", "Clap", "Closed hat", "Snare", "808", "FL Keys",
                              "Padilion"])
        self.script = load_script(self.rack)
        self.script.OnInit()
        self.fake = FakeLink(self.rack, self.script)
        self.roll = FakePianoRoll(self.script)
        self.saved = engine_mod.link, engine_mod.pianoroll
        engine_mod.link, engine_mod.pianoroll = self.fake, self.roll
        self.engine = Engine(seed=3)

    def tearDown(self):
        engine_mod.link, engine_mod.pianoroll = self.saved

    def lit(self, ch):
        return sorted(s for p, c, s in self.rack.grid if p == self.rack.pattern and c == ch)


class EngineTest(EngineFixture):
    def test_status_maps_the_rack(self):
        st = self.engine.status()
        self.assertTrue(st["connected"])
        roles = {c["name"]: c["role"] for c in st["channels"]}
        self.assertEqual(roles["Kick"], "kick")
        self.assertEqual(roles["808"], "bass")
        self.assertEqual(roles["FL Keys"], "chords")
        self.assertEqual(roles["Padilion"], "pad")

    def test_new_beat_writes_everything_and_back_restores(self):
        self.rack.grid[(1, 0, 5)] = 90          # a hand-made kick the user had
        out = self.engine.new_beat("trap", key="A", scale="minor")
        self.assertEqual(out["genre"], "Trap")
        self.assertEqual(out["key"], "A minor")
        self.assertEqual(out["warnings"], [])
        self.assertIn(0, self.lit(0))           # downbeat kick
        self.assertTrue(self.lit(4))            # 808 written
        self.assertEqual(len(self.roll.written), 2)     # chords, then pad
        self.assertEqual(sum(c["beats"] for c in out["progression"]), 16)
        self.assertTrue(self.rack.playing)
        self.engine.back()
        self.assertEqual(self.lit(0), [5])
        self.assertEqual(self.roll.written[-1], [])     # rolls emptied again

    def test_parts_switched_off_are_left_alone(self):
        self.rack.grid[(1, 4, 3)] = 100
        out = self.engine.new_beat("house", bass=False, chords=False, pad=False, play=False)
        self.assertEqual(self.lit(4), [3])
        self.assertEqual(self.roll.written, [])
        self.assertIsNone(out["progression"])
        self.assertFalse(self.rack.playing)

    def test_write_part_plays_free_notes_on_any_channel(self):
        self.rack.names.append("Guitar")
        out = self.engine.write_part(7, [[61, 0, 0.5, 110], [64, 0.1667, 0.25, 90]])
        self.assertEqual(out["channel"], "Guitar")
        self.assertEqual(out["notes"], 2)
        self.assertEqual(out["problems"], [])
        self.assertEqual(self.roll.written[-1], [(61, 0, 2, 110), (64, 0.6668, 1, 90)])
        self.assertEqual(self.engine.write_part("guitar", [[60, 1, 1]])["notes"], 1)
        self.engine.back()
        self.assertEqual(self.roll.written[-1], [(61, 0, 2, 110), (64, 0.6668, 1, 90)])
        self.engine.back()
        self.assertEqual(self.roll.written[-1], [])         # roll emptied again

    def test_write_part_explains_bad_input(self):
        for channel, notes in ((12, [[60, 0, 1]]), ("Tuba", [[60, 0, 1]]), (0, []),
                               (0, [[200, 0, 1]]), (0, [[60, -1, 1]]), (0, [["x"]])):
            with self.assertRaises(SeekerError):
                self.engine.write_part(channel, notes)

    def test_off_grid_steps_survive_into_the_script(self):
        from seeker import pianoroll
        src = pianoroll.script_source([(61, 0.6668, 1, 90), (60, 4, 2, 100)])
        self.assertIn("(61, 0.6668, 1, 90)", src)
        self.assertIn("(60, 4, 2, 100)", src)

    def test_every_press_is_different(self):
        a = self.engine.new_beat("boom bap", chords=False, pad=False)
        b = self.engine.new_beat("boom bap", chords=False, pad=False)
        self.assertNotEqual(a["tag"], b["tag"])

    def test_exact_tempo_is_set(self):
        out = self.engine.new_beat("boom bap", key="C", scale="major", tempo=90)
        self.assertEqual(out["tempo"], 90.0)
        self.assertEqual(self.rack.tempo, 90.0)
        auto = self.engine.new_beat(tempo="140")
        self.assertEqual(self.rack.tempo, 140.0)
        self.assertNotIn(auto["genre"], ("Boom Bap", "Lo-Fi", "R&B"))
        for bad in ("fast", 5, 900):
            with self.assertRaises(SeekerError):
                self.engine.new_beat("house", tempo=bad)

    def test_passing_diminished_chord_ends_the_progression(self):
        for _ in range(6):
            out = self.engine.new_beat("boom bap", key="C", scale="major", passing=True)
            prog = out["progression"]
            self.assertTrue(prog[-1]["chord"].endswith("dim"), prog)
            self.assertIn(prog[-1]["beats"], (1, 2))
            self.assertGreaterEqual(prog[-2]["beats"], 1)
            self.assertEqual(sum(c["beats"] for c in prog), 16)
            # a semitone under the first chord, so it leads back to the top
            first = prog[0]["chord"].rstrip("m")
            self.assertEqual((KEYS.index(prog[-1]["chord"][:-3]) + 1) % 12, KEYS.index(first))
        plain = self.engine.new_beat("boom bap", key="C", scale="major")
        self.assertFalse(any(c["chord"].endswith("dim") for c in plain["progression"]))

    def test_bad_input_is_explained(self):
        with self.assertRaises(SeekerError):
            self.engine.new_beat("polka")
        with self.assertRaises(SeekerError):
            self.engine.new_beat(key="H")
        with self.assertRaises(SeekerError):
            self.engine.back()

    def test_fl_not_answering_is_explained(self):
        self.fake.heartbeat = lambda: None
        clock = iter(range(0, 10 ** 6))
        engine_mod.time = types.SimpleNamespace(time=lambda: next(clock), sleep=lambda s: None)
        try:
            with self.assertRaises(SeekerError) as ctx:
                self.engine.new_beat()
            self.assertIn("MIDI settings", str(ctx.exception))
        finally:
            import time
            engine_mod.time = time

    def test_name_parsing(self):
        self.assertEqual(resolve_genre("Boom Bap"), resolve_genre("boombap"))
        for said, key in (("rock n roll", "rocknroll"), ("Rock & Roll", "rocknroll"),
                          ("rock and roll", "rocknroll"), ("classic soul", "soul"),
                          ("Motown", "soul"), ("jazz", "jazz"), ("swing", "jazz"),
                          ("Country", "country"), ("orchestral", "classical")):
            self.assertEqual(resolve_genre(said), key, said)
        self.assertIsNone(resolve_genre("auto"))
        self.assertEqual(resolve_key("Bb"), resolve_key("A#"))


class WindowText(EngineFixture):
    """The desktop window shows the engine's results; check what it says."""

    def window(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ps_window", os.path.join(ROOT, "pattern_seeker.pyw"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_status_text_names_the_parts_and_where_they_went(self):
        text = self.window().beat_text(self.engine.new_beat("trap", key="A"))
        first, second = text.split("\n")[:2]
        self.assertIn("Trap", first)
        self.assertIn("808 + chords + synth in A minor", first)
        self.assertIn("chords → FL Keys", second)
        self.assertIn("synth → Padilion", second)

    def test_missing_parts_are_listed(self):
        self.rack.names[:] = ["Kick", "Snare", "Closed hat"]
        text = self.window().beat_text(self.engine.new_beat("house"))
        self.assertIn("No channel for: bass, chords, synth", text)
        self.assertNotIn("openhat", text)


class FakeSounds:
    """sounds, with FL's side of open_in_fl played by the fake rack."""
    SoundError = real_sounds.SoundError
    ITEMS = [{"kind": "instrument", "name": "FLEX", "id": "Fruity/FLEX", "path": "flex.fst"},
             {"kind": "instrument", "name": "FL Keys", "id": "Fruity/FL Keys", "path": "k.fst"},
             {"kind": "sample", "name": "909 Kick", "id": "Drums/Kicks/909 Kick",
              "path": "909.wav"},
             {"kind": "sample", "name": "909 Snare", "id": "Drums/Snares/909 Snare",
              "path": "909s.wav"}]

    def __init__(self, rack):
        self.rack, self.opened, self.answers = rack, [], True

    def search(self, text="", kind="all"):
        return real_sounds.search(text, kind, self.ITEMS)

    def resolve(self, sound):
        return real_sounds.resolve(sound, self.ITEMS)

    def open_in_fl(self, item, name=None):
        self.opened.append((item["id"], name))
        if not self.answers:
            return
        index = len(self.rack.names)
        if item["kind"] == "instrument":    # FL names the channel after the plugin
            self.rack.names.append(item["name"])
            self.rack.plugins[index] = {"name": item["name"], "steps": [], "params": [
                ["Cutoff", 0.5], ["Resonance", 0.1], ["Amp Attack", 0.0], ["", 0.0]]}
            self.rack.props[index] = {"editor": 1}
        else:                               # a sampler preset carries the name
            self.rack.names.append(name or item["name"])


class SoundsFixture(EngineFixture):
    def setUp(self):
        super().setUp()
        self.sounds = FakeSounds(self.rack)
        self.saved_sounds, engine_mod.sounds = engine_mod.sounds, self.sounds

    def tearDown(self):
        engine_mod.sounds = self.saved_sounds
        super().tearDown()


class ChannelsTest(SoundsFixture):
    def test_list_sounds_filters_by_words_and_kind(self):
        out = self.engine.list_sounds("909")
        self.assertEqual(out["total"], 2)
        self.assertEqual(self.engine.list_sounds("kick 909")["sounds"],
                         [{"kind": "sample", "id": "Drums/Kicks/909 Kick"}])
        self.assertEqual(self.engine.list_sounds(kind="instruments")["total"], 2)
        self.assertEqual(self.engine.list_sounds(limit=1)["shown"], 1)

    def test_add_channel_loads_names_and_closes_the_plugin_window(self):
        out = self.engine.add_channel("flex", name="Pad 2", color="#E0782F", volume=0.6)
        self.assertEqual(out["channel"], 7)
        self.assertEqual((out["name"], out["plugin"], out["sound"]),
                         ("Pad 2", "FLEX", "Fruity/FLEX"))
        self.assertEqual(self.rack.names[7], "Pad 2")
        self.assertEqual(self.rack.props[7], {"editor": 0, "color": 0xE0782F, "volume": 0.6})
        self.assertEqual(out["warnings"], [])

    def test_a_new_drum_gets_its_role_from_its_name(self):
        self.rack.names[:] = ["Snare", "Hat"]
        out = self.engine.add_channel("Drums/Kicks/909 Kick", name="Kick")
        self.assertEqual((out["channel"], out["kind"], out["role"]), (2, "sample", "kick"))
        self.assertEqual(self.sounds.opened, [("Drums/Kicks/909 Kick", "Kick")])
        beat = self.engine.new_beat("house", chords=False, pad=False, bass=False)
        self.assertEqual(beat["written"]["kick"], "Kick")
        self.assertTrue(self.lit(2))

    def test_add_channel_explains_what_went_wrong(self):
        with self.assertRaises(SeekerError) as ctx:
            self.engine.add_channel("909")              # two sounds fit
        self.assertIn("Drums/Kicks/909 Kick", str(ctx.exception))
        for bad in ({"sound": "tuba"}, {"sound": ""}, {"sound": "flex", "color": "orange"},
                    {"sound": "flex", "volume": 3}, {"sound": "flex", "pan": "left"}):
            with self.assertRaises(SeekerError):
                self.engine.add_channel(**bad)
        self.assertEqual(self.sounds.opened, [])        # nothing reached FL
        self.sounds.answers = False                     # FL never adds the channel
        clock = iter(range(0, 10 ** 6))
        engine_mod.time = types.SimpleNamespace(time=lambda: next(clock), sleep=lambda s: None)
        try:
            with self.assertRaises(SeekerError) as ctx:
                self.engine.add_channel("flex")
            self.assertIn("didn't add a channel", str(ctx.exception))
        finally:
            import time
            engine_mod.time = time

    def test_channel_params_lists_named_parameters(self):
        self.engine.add_channel("flex", name="Lead")
        out = self.engine.channel_params("lead")
        self.assertEqual((out["plugin"], out["paramCount"], out["presetCount"]),
                         ("FLEX", 3, 5))
        self.assertNotIn("preset", out)         # FL can't say which one is loaded
        self.assertEqual(self.engine.channel_params("lead", presets=True)["presets"][1],
                         "Warm Pad")
        self.assertEqual(out["params"][0],
                         {"index": 0, "name": "Cutoff", "value": 0.5, "shows": "50%"})
        self.assertEqual([p["name"] for p in self.engine.channel_params(7, "a")["params"]],
                         ["Resonance", "Amp Attack"])
        sampler = self.engine.channel_params("Kick")
        self.assertEqual(sampler["params"], [])
        self.assertEqual(sampler["volume"], 0.7812)

    def test_set_channel_tweaks_parameters_presets_and_the_channel(self):
        self.engine.add_channel("flex", name="Lead")
        out = self.engine.set_channel("Lead", params={"cutoff": 0.25, "2": 0.4, "Drive": 1},
                                      preset=2, pan=-0.3, name="Pluck")
        self.assertEqual(self.rack.plugins[7]["params"][0][1], 0.25)
        self.assertEqual(self.rack.plugins[7]["params"][2][1], 0.4)
        self.assertEqual(out["unknownParams"], ["Drive"])
        self.assertEqual([c["name"] for c in out["changed"]], ["Cutoff", "Amp Attack"])
        self.assertEqual(out["changed"][0]["shows"], "25%")
        self.assertEqual(out["preset"], "Glass Keys")
        self.rack.plugins[7]["preset"] = 4      # the user moved on by hand meanwhile
        out = self.engine.set_channel("Pluck", preset_name="warm")
        self.assertEqual((out["preset"], self.rack.plugins[7]["preset"]), ("Warm Pad", 1))
        self.assertEqual(self.engine.set_channel("Pluck", preset=-2)["preset"], "Glass Bell")
        self.assertEqual(self.engine.set_channel("Pluck", preset_name="Glass Bell")["preset"],
                         "Glass Bell")           # already there: back after the look-see step
        for bad, says in (("glass", "2 presets match"), ("tuba", "No preset named")):
            with self.assertRaises(SeekerError) as ctx:
                self.engine.set_channel("Pluck", preset_name=bad)
            self.assertIn(says, str(ctx.exception))
        self.assertEqual(self.rack.plugins[7]["preset"], 4)     # and nothing moved
        self.assertEqual((out["name"], out["pan"]), ("Pluck", -0.3))
        self.assertEqual(self.rack.names[7], "Pluck")
        self.engine.set_channel(7, show=True)
        self.assertEqual(self.rack.props[7]["editor"], 1)

    def test_set_channel_explains_bad_input(self):
        for bad in ({"params": {"Cutoff": 0.5}},        # Kick is a sampler
                    {"params": {"Cutoff": 7}}, {"params": {"Cutoff": "high"}},
                    {"preset": "next"}, {}):
            with self.assertRaises(SeekerError):
                self.engine.set_channel("Kick", **bad)
        with self.assertRaises(SeekerError):
            self.engine.channel_params("Tuba")


class RoutingTest(SoundsFixture):
    def test_unrouted_channels_get_their_own_named_insert(self):
        out = self.engine.route_channels()
        got = {r["channel"]: r["insert"] for r in out["routed"]}
        # insert N for index N; index 0 can't use the master, so it takes the
        # lowest insert left over and nobody else moves
        self.assertEqual(got, {"Kick": 7, "Clap": 1, "Closed hat": 2, "Snare": 3,
                               "808": 4, "FL Keys": 5, "Padilion": 6})
        self.assertEqual(self.rack.inserts[3], 3)
        self.assertEqual(self.rack.insert_names[3], "Snare")
        self.assertIn(3, self.rack.insert_colors)
        self.assertEqual(self.engine.status()["channels"][3]["insert"], 3)
        self.assertEqual(self.engine.route_channels()["routed"], [])   # nothing left

    def test_template_labels_and_taken_inserts_are_respected(self):
        self.rack.inserts[1] = 2                 # Clap already plays through insert 2
        self.rack.insert_names[9] = "Snare"      # a template's labelled insert
        self.rack.insert_names[4] = "Vocals"     # named by the user: not free
        out = self.engine.route_channels(["Snare", "808", "Clap"])
        got = {r["channel"]: r["insert"] for r in out["routed"]}
        self.assertEqual(got, {"Snare": 9, "808": 1})   # Clap kept, insert 4 skipped
        # reroute: Clap's own insert counts as free again, so it stays and gets named
        moved = self.engine.route_channels(["Clap"], reroute=True)["routed"]
        self.assertEqual(moved[0]["insert"], 2)
        self.assertEqual(self.rack.insert_names[2], "Clap")

    def test_add_channel_routes_the_new_channel(self):
        out = self.engine.add_channel("flex", name="Pad 2")
        self.assertEqual((out["channel"], out["insert"]), (7, 7))
        self.assertEqual(self.rack.insert_names[7], "Pad 2")
        out = self.engine.add_channel("Drums/Kicks/909 Kick", name="Kick 2", route=False)
        self.assertNotIn("insert", out)
        self.assertNotIn(8, self.rack.inserts)


BAND_PARAMS = ["Used", "Enabled", "Frequency", "Gain", "Q", "Shape", "Slope"] + [
    "Extra %d" % i for i in range(17)]


def fake_cfilter():
    """CFilteR-01's parameter layout: 24 bands of 24 parameters, all bands unused."""
    return {"name": "CFilteR-01", "params": [
        ["Band %d %s" % (n, p), {"Used": 0.0, "Enabled": 1.0, "Frequency": 0.575188,
                                 "Gain": 0.5, "Q": 0.5, "Slope": 0.2}.get(p, 0.0)]
        for n in range(1, 25) for p in BAND_PARAMS]}


class EqTest(SoundsFixture):
    def setUp(self):
        super().setUp()
        self.engine.route_channels()        # Kick 7, Clap 1, ... Padilion 6

    def value(self, insert, band, param):
        return self.rack.fx[(insert, 0)]["params"][(band - 1) * 24 + BAND_PARAMS.index(param)][1]

    def test_curves_match_the_plugin(self):
        from seeker import eq
        self.assertAlmostEqual(eq.norm_freq(40), 0.17315, places=5)     # read "40.000 Hz" live
        self.assertAlmostEqual(eq.norm_freq(1000), 0.575188, places=5)
        self.assertAlmostEqual(eq.norm_gain(-2), 0.466667, places=5)    # "-2.00 dB"
        self.assertAlmostEqual(eq.norm_q(1), 0.5)
        self.assertAlmostEqual(eq.norm_slope(12), 0.2)                   # "12 dB/oct"
        self.assertAlmostEqual(eq.norm_slope(72), 0.8)
        self.assertEqual(eq.norm_slope("brickwall"), 1.0)
        self.assertAlmostEqual(eq.norm_shape("high pass"), 2 / 9.0)     # "Low Cut"
        with self.assertRaises(eq.EqError):
            eq.norm_shape("wobble")

    def test_eq_sets_bands_on_the_channels_insert_and_clears_the_rest(self):
        self.rack.fx[(5, 0)] = fake_cfilter()   # FL Keys plays through insert 5
        self.rack.fx[(5, 0)]["params"][4 * 24][1] = 1.0     # an old band 5 in use
        out = self.engine.eq("FL Keys", [{"shape": "low cut", "freq": 140, "slope": 12},
                                         {"shape": "bell", "freq": 320, "gain": -2}])
        self.assertEqual((out["insert"], out["slot"], len(out["bands"])), (5, 1, 2))
        self.assertEqual(self.value(5, 1, "Used"), 1.0)
        self.assertAlmostEqual(self.value(5, 1, "Shape"), 2 / 9.0)
        self.assertAlmostEqual(self.value(5, 2, "Gain"), 28 / 60.0)
        self.assertEqual(self.value(5, 5, "Used"), 0.0)     # cleared

    def lying_cfilter(self, drops):
        """A CFilteR-01 like the one seen live: FL's value says a setting took, but the
        plugin's own text shows its old value. `drops`: how many writes of each band 4
        and 5 parameter it ignores."""
        from seeker import eq
        fx = fake_cfilter()
        real = [v for _, v in fx["params"]]
        missed = {}

        def on_set(i, value):
            if 3 <= i // 24 <= 4 and missed.get(i, 0) < drops:
                missed[i] = missed.get(i, 0) + 1
                return
            real[i] = value

        def text(i):
            v, off = real[i], i % 24
            if off == eq.FREQ:
                return "%.3f Hz" % (eq.MIN_FREQ * (eq.MAX_FREQ / eq.MIN_FREQ) ** v)
            if off == eq.GAIN:
                return "%+.2f dB" % (eq.MIN_GAIN + v * (eq.MAX_GAIN - eq.MIN_GAIN))
            if off == eq.Q:
                return "%.3f" % (eq.MIN_Q * (eq.MAX_Q / eq.MIN_Q) ** v)
            if off == eq.SHAPE:
                return eq.SHAPES[int(round(v * 9))].title()
            return "%d%%" % round(v * 100)

        fx.update(on_set=on_set, text=text)
        return fx, real

    BASS_EQ = [{"shape": "low cut", "freq": 35, "slope": 24},
               {"shape": "bell", "freq": 60, "gain": -2, "q": 1.4},
               {"shape": "bell", "freq": 100, "gain": 1.5, "q": 1.2},
               {"shape": "bell", "freq": 250, "gain": -2, "q": 1.2},
               {"shape": "bell", "freq": 800, "gain": 1.5, "q": 1.5}]

    def test_eq_resends_bands_the_plugin_didnt_take(self):
        from seeker import eq
        self.rack.fx[(5, 0)], real = self.lying_cfilter(drops=2)
        out = self.engine.eq("FL Keys", self.BASS_EQ)
        self.assertEqual(out["warnings"], [])
        self.assertIn("250.000 Hz", out["bands"][3])
        self.assertIn("-2.00 dB", out["bands"][3])
        self.assertIn("800.000 Hz", out["bands"][4])
        self.assertAlmostEqual(real[4 * 24 + eq.GAIN], eq.norm_gain(1.5))

    def test_eq_warns_when_a_band_never_takes(self):
        self.rack.fx[(5, 0)], _ = self.lying_cfilter(drops=99)
        out = self.engine.eq("FL Keys", self.BASS_EQ)
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIn("didn't take", out["warnings"][0])
        self.assertIn("Band 4 Frequency", out["warnings"][0])

    def test_eq_explains_what_is_missing(self):
        with self.assertRaisesRegex(SeekerError, "No CFilteR-01 on insert 5"):
            self.engine.eq("FL Keys", [{"freq": 100}])
        self.rack.inserts[2] = 0                # Closed hat back on the master
        with self.assertRaisesRegex(SeekerError, "route_channels"):
            self.engine.eq("Closed hat", [{"freq": 100}])

    def test_mix_eq_gives_each_part_the_genres_bands(self):
        for insert in range(1, 11):
            self.rack.fx[(insert, 0)] = fake_cfilter()
        out = self.engine.mix_eq("house")
        parts = {c["part"]: c["insert"] for c in out["channels"]}
        self.assertEqual(parts["kick"], 7)
        self.assertEqual(out["problems"], [])
        from seeker import eq
        self.assertAlmostEqual(self.value(7, 1, "Frequency"), eq.norm_freq(30))


class KitsTest(SoundsFixture):
    TRAP = ["808 Kick", "808 Snare", "808 Clap", "808 Hat", "808 Open hat", "808 Perc",
            "808 Bass", "Piano", "Pad"]

    def setUp(self):
        super().setUp()
        from seeker import kits
        ids = sorted({o for g in kits._GENRES for found in kits.parts(g).values()
                      for sound in found for o in sound.options})
        self.sounds.ITEMS = list(FakeSounds.ITEMS) + [dict(
            {"kind": "sample" if i.startswith("Drums/") else "instrument",
             "name": i.rsplit("/", 1)[-1], "id": i, "path": i},
            **({"flex": tuple(i.split("/")[1:])} if i.startswith("FLEX/") else {}))
            for i in ids]

    def steps(self, name):
        return self.lit(self.rack.names.index(name))

    def test_every_kit_sound_is_named_for_its_part_and_its_style(self):
        from seeker import kits
        from seeker.library import GENRES, GUITAR
        from seeker.mapping import detect_role
        self.assertEqual(set(kits._GENRES), set(GENRES))
        for genre in GENRES:
            spec = kits.parts(genre)
            self.assertEqual(tuple(spec), tuple(r for r in kits.ROLES if r in spec))
            self.assertTrue({"bass", "chords"} <= set(spec), genre)
            self.assertEqual("guitar" in spec, genre in GUITAR, genre)
            for role, found in spec.items():
                for sound in found:
                    self.assertTrue(sound.options, (genre, role))
                    self.assertEqual(detect_role(sound.name), role, sound.name)
                    self.assertEqual(kits.style_of(role, sound.name), sound.style, sound.name)
            # every drum the genre's grooves play has a sound in its kit
            for role in kits.DRUM_ROLES:
                if any(GENRES[genre][role]):
                    self.assertIn(role, spec, genre)
        self.assertIsNone(kits.style_of("kick", "Kick"))
        self.assertEqual(kits.style_of("bass", "808 Astronomic"), "808")

    def test_build_rack_fills_an_empty_rack_and_names_it_after_its_sounds(self):
        self.rack.names[:] = []
        out = self.engine.build_rack("trap")
        self.assertEqual(out["problems"], [])
        self.assertEqual(self.rack.names, self.TRAP)
        self.assertEqual(out["added"][0], {"part": "kick", "channel": 0, "name": "808 Kick",
                                           "sound": "Drums/Kicks/808 Kick", "insert": 1})
        self.assertTrue(out["added"][6]["sound"].startswith(("FLEX/Core 808s/", "Presets/")))
        self.assertEqual(self.rack.props[8]["volume"], 0.5)
        again = self.engine.build_rack("trap")              # nothing is added twice
        self.assertEqual((again["added"], len(again["kept"])), ([], 9))
        for bad in (("auto", None), ("polka", None), ("trap", ["tuba"])):
            with self.assertRaises(SeekerError):
                self.engine.build_rack(*bad)

    def test_a_genre_only_plays_channels_that_suit_it(self):
        self.rack.names[:] = list(self.TRAP)
        trap = self.engine.new_beat("trap", key="A", play=False)
        self.assertEqual(trap["written"]["bass"], "808 Bass")
        self.assertTrue(self.steps("808 Kick") and self.steps("808 Bass"))
        out = self.engine.new_beat("classical", key="A", play=False)      # same pattern
        self.assertEqual(out["written"], {"chords": "Piano"})   # the piano may stay
        self.assertEqual(sorted(out["noChannelFor"]), ["bass", "pad"])   # no 808, no synth
        self.assertEqual(self.steps("808 Kick"), [])            # the trap beat is silenced
        self.assertEqual(self.steps("808 Bass"), [])
        self.assertEqual(self.roll.written[-1], [])             # and its pad emptied
        self.engine.back()
        self.assertTrue(self.steps("808 Kick") and self.steps("808 Bass"))
        self.assertTrue(self.roll.written[-1] or self.roll.written[-2])

        out = self.engine.new_beat("classical", key="A", play=False, build=True)
        self.assertEqual([(a["part"], a["name"]) for a in out["built"]["added"]],
                         [("bass", "Cello"), ("pad", "Strings")])
        self.assertEqual(out["written"], {"bass": "Cello", "chords": "Piano", "pad": "Strings"})
        self.assertEqual(out["noChannelFor"], [])
        self.assertTrue(self.steps("Cello"))
        self.assertEqual(self.steps("808 Bass"), [])

    def test_kits_share_a_rack(self):
        self.rack.names[:] = list(self.TRAP)
        jazz = self.engine.build_rack("jazz")
        self.assertEqual([(a["part"], a["name"]) for a in jazz["added"]][:5],
                         [("kick", "Jazz Kick"), ("snare", "Jazz Snare"), ("hat", "Jazz Ride"),
                          ("perc", "Jazz Rim"), ("bass", "Upright Bass")])
        self.assertTrue(jazz["added"][2]["sound"].startswith("Drums/Kits/HQ Jazz Kit/Ride"))
        self.assertEqual(self.engine.build_rack("trap")["added"], [])
        out = self.engine.new_beat("jazz", key="F", scale="major", play=False)
        self.assertEqual((out["written"]["kick"], out["written"]["hat"], out["written"]["bass"]),
                         ("Jazz Kick", "Jazz Ride", "Upright Bass"))
        self.assertNotIn("pad", out["written"])                 # jazz has no pad
        self.assertEqual(out["noChannelFor"], [])
        self.assertEqual(self.steps("808 Hat"), [])
        # the upright plays in a bass's register: low E up to FL's C4, never the 808's C5
        upright = self.rack.names.index("Upright Bass")
        notes = [self.rack.pitch.get((self.rack.pattern, upright, s), 60)
                 for s in self.steps("Upright Bass")]
        self.assertTrue(notes and all(28 <= n <= 48 for n in notes), notes)
        out = self.engine.new_beat("trap", key="F", play=False)
        self.assertEqual((out["written"]["kick"], out["written"]["bass"]),
                         ("808 Kick", "808 Bass"))
        self.assertEqual(self.steps("Jazz Ride"), [])
        self.assertEqual(self.steps("Upright Bass"), [])
        self.assertTrue(self.steps("808 Hat"))

    def test_rock_gets_the_hq_kit_a_rock_bass_and_power_chords(self):
        self.rack.names[:] = ["Pad"]
        out = self.engine.new_beat("rock n roll", key="E", scale="minor", play=False, build=True)
        added = {a["part"]: a for a in out["built"]["added"]}
        self.assertEqual(sorted(added), ["bass", "chords", "clap", "guitar", "hat", "kick",
                                         "openhat", "perc", "snare"])   # the pad is optional
        self.assertEqual((added["kick"]["name"], added["perc"]["name"], added["bass"]["name"],
                          added["guitar"]["name"]),
                         ("Rock Kick", "Rock Tambourine", "Rock Bass", "Rock Guitar"))
        self.assertTrue(added["kick"]["sound"].startswith("Drums/Kits/HQ Rock Kit/Kick 1"))
        self.assertEqual(out["written"]["guitar"], "Rock Guitar")
        self.assertEqual(out["written"]["pad"], "Pad")          # the synth may stay
        power = [n for roll in self.roll.written for n in roll if n[0] < 53]
        self.assertTrue(power)
        strike = sorted(n[0] for n in power if n[1] == power[0][1])
        self.assertEqual([n - strike[0] for n in strike], [0, 7, 12])   # root, fifth, octave
        count = len(self.roll.written)
        quiet = self.engine.new_beat("rock", key="E", play=False, guitar=False)
        self.assertNotIn("guitar", quiet["written"])
        self.assertIn([], self.roll.written[count:])            # the guitar roll is emptied
        country = self.engine.build_rack("country")
        self.assertIn(("guitar", "Tele Guitar"), [(a["part"], a["name"])
                                                  for a in country["added"]])

    def test_without_building_a_near_enough_channel_stands_in(self):
        # the fixture rack: Kick, Clap, Closed hat, Snare, 808, FL Keys, Padilion
        house = self.engine.new_beat("house", play=False)
        self.assertEqual((house["written"]["kick"], house["written"]["bass"]), ("Kick", "808"))
        self.assertEqual(house["written"]["chords"], "FL Keys")
        rock = self.engine.new_beat("rock", play=False)
        self.assertEqual(rock["written"]["kick"], "Kick")       # a plain name suits anything
        self.assertNotIn("bass", rock["written"])               # but an 808 is no rock bass
        self.assertEqual(sorted(rock["noChannelFor"]), ["bass", "guitar"])
        self.assertEqual(self.lit(4), [])
        self.rack.names[:] = ["808 Kick", "808 Snare"]
        with self.assertRaises(SeekerError) as ctx:
            self.engine.new_beat("classical", chords=False, pad=False)
        self.assertIn("build=true", str(ctx.exception))

    def test_build_rack_only_adds_what_is_asked_for_and_reports_the_rest(self):
        self.rack.names[:] = ["Kick"]
        out = self.engine.build_rack("funk", ["drums", "Piano"])
        self.assertEqual([a["part"] for a in out["added"]],
                         ["snare", "clap", "hat", "openhat", "perc", "chords"])
        self.assertEqual(out["kept"], {"kick": "Kick"})
        self.sounds.ITEMS = [i for i in self.sounds.ITEMS if "ello" not in i["id"]
                             and "Contrabass" not in i["id"] and "Pizzicato" not in i["id"]]
        out = self.engine.build_rack("classical")
        self.assertEqual([a["part"] for a in out["added"]], ["chords", "pad"])
        self.assertEqual(out["problems"], ["bass: none of its sounds are on this PC"])

    def test_new_beat_can_build_the_rack_first(self):
        self.rack.names[:] = []
        out = self.engine.new_beat("boom bap", key="D", pad=False, build=True)
        self.assertEqual(len(out["built"]["added"]), 8)         # no pad was asked for
        self.assertFalse([n for n in self.rack.names if "Pad" in n or "Strings" in n])
        self.assertEqual((out["written"]["kick"], out["written"]["bass"]),
                         ("Dusty Kick", "Electric Bass"))
        self.assertIn(out["written"]["chords"], ("Rhodes", "Piano"))
        self.assertTrue(self.lit(0))
        self.assertEqual(out["noChannelFor"], [])
        self.assertNotIn("built", self.engine.new_beat("boom bap", pad=False))

    def test_a_flex_preset_is_loaded_with_its_own_knobs(self):
        self.rack.presets[:] = ["Cellos Pizzicato", "Cellos Staccato", "Cellos Sustain"]
        out = self.engine.add_channel("FLEX/Essential Strings/Cellos Staccato", name="Cello")
        self.assertEqual((out["name"], out["plugin"]), ("Cello", "Cellos Staccato"))
        # one preset on and back: FLEX reloads the preset, and ends where it began
        self.assertEqual(self.rack.plugins[out["channel"]]["preset"], 0)
        self.assertEqual(self.rack.plugins[out["channel"]]["steps"], [1, -1])

    def test_a_plugin_that_hides_its_preset_is_left_where_it_was(self):
        self.engine.add_channel("Fruity/FLEX", name="Lead")
        self.rack.presets[:] = ["Init", "Warm Pad", "Glass Keys"]
        self.rack.plugins[7]["preset"] = 2
        saved, self.script.ui.getHintMsg = self.script.ui.getHintMsg, lambda: ""
        clock = iter(range(0, 10 ** 6))
        engine_mod.time = types.SimpleNamespace(time=lambda: next(clock), sleep=lambda s: None)
        try:
            with self.assertRaises(SeekerError) as ctx:
                self.engine.set_channel("Lead", preset_name="Warm Pad")
            self.assertIn("doesn't show which preset", str(ctx.exception))
            self.assertEqual(self.rack.plugins[7]["preset"], 2)     # stepped back
        finally:
            import time
            engine_mod.time, self.script.ui.getHintMsg = time, saved


class SoundsTest(unittest.TestCase):
    def test_resolve_takes_an_id_a_name_or_words(self):
        from seeker import sounds
        items = FakeSounds.ITEMS
        self.assertEqual(sounds.resolve("fl keys", items)["id"], "Fruity/FL Keys")
        self.assertEqual(sounds.resolve("drums/snares/909 snare", items)["kind"], "sample")
        self.assertEqual(sounds.resolve("snare", items)["name"], "909 Snare")
        self.assertEqual(sounds.resolve(__file__.replace(".py", ".fst"), items + [
            {"kind": "instrument", "name": "x", "id": __file__.replace(".py", ".fst"),
             "path": "x"}])["name"], "x")
        for bad in ("", "909", "tuba"):
            with self.assertRaises(sounds.SoundError):
                sounds.resolve(bad, items)

    def test_flex_presets_are_read_from_a_pack_and_written_as_a_state(self):
        import tempfile
        from seeker import sounds

        def entry(name):
            raw = name.encode() + b"\0"
            return len(raw).to_bytes(4, "big") + raw + bytes(12)

        long_name = "A Really Long Preset Name For A Cello Section"      # length byte is printable
        pack = (bytes([1, 0, 0, 2, 0, 0, 4, 72]) + entry("presets")
                + entry("Cellos Staccato.flexpreset") + entry("Cellos Staccato.usedsamples")
                + entry(long_name + ".flex2preset") + entry("STR Bass Pizzicato.flex2preset"))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "Test.flexpack")
            with open(path, "wb") as fh:
                fh.write(pack + bytes(5000))
            self.assertEqual(sounds.flex_pack_presets(path),
                             ["Cellos Staccato", long_name, "STR Bass Pizzicato"])
        state = sounds.flex_state("Essential Strings", "Cellos Staccato")
        self.assertEqual(len(state), 2707)
        self.assertEqual(state[16:34], b"Essential Strings\0")
        self.assertEqual(state[1041:1057], b"Cellos Staccato\0")
        body = (bytes([199, 7]) + b"11.5.5\0" + bytes([28, 1, 201, 10])
                + "FLEX\0".encode("utf-16-le") + bytes([212, 4, 0, 0, 0, 0]))
        template = (b"FLhd" + (6).to_bytes(4, "little") + bytes(6)
                    + b"FLdt" + len(body).to_bytes(4, "little") + body)
        header, events = sounds._events(sounds.flex_bytes(template, "Pack", "Preset"))
        self.assertEqual([i for i, _ in events], [199, 28, 201, 212, 213])
        self.assertEqual(events[-1][1][16:21], b"Pack\0")
        self.assertEqual(len(events[-1][1]), 2707)

    def test_sampler_preset_carries_the_sample_and_the_name(self):
        from seeker import sounds
        body = (bytes([199, 6]) + b"3.1.2\0" + bytes([64, 1, 0, 21, 0, 192, 1, 0])
                + bytes([128, 1, 2, 3, 4]) + bytes([215, 3, 9, 9, 9]))
        template = (b"FLhd" + (6).to_bytes(4, "little") + bytes(6)
                    + b"FLdt" + len(body).to_bytes(4, "little") + body)
        path = "C:\\Samples\\" + "k" * 150 + ".wav"      # long enough for a 2-byte length
        header, events = sounds._events(sounds.sampler_bytes(template, path, "Kick"))
        self.assertEqual(header, template[:14])
        self.assertEqual([i for i, _ in events], [199, 64, 21, 192, 196, 128, 215])
        self.assertEqual(dict(events)[192], b"Kick\0")
        self.assertEqual(dict(events)[196], path.encode() + b"\0")
        self.assertEqual(dict(events)[215], bytes([9, 9, 9]))
        with self.assertRaises(sounds.SoundError):
            sounds.sampler_bytes(template, "C:\\\u4e2d.wav", "Kick")


class McpServerTest(unittest.TestCase):
    """The server speaks real MCP over stdio: start it and list its tools."""

    def test_tools_are_listed(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            self.skipTest("mcp package not installed")

        async def run():
            params = StdioServerParameters(command=sys.executable,
                                           args=[os.path.join(ROOT, "mcp_server.py")])
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    tools = await s.list_tools()
                    genres = await s.call_tool("list_genres", {})
                    return {t.name for t in tools.tools}, genres

        names, genres = asyncio.run(run())
        self.assertEqual(names, {"list_genres", "fl_status", "new_beat", "write_part", "back",
                                 "new_song", "arrange", "write_song",
                                 "list_sounds", "add_channel", "channel_params",
                                 "set_channel", "build_rack", "route_channels", "eq",
                                 "mix_eq", "new_ballad"})
        self.assertFalse(getattr(genres, "is_error", getattr(genres, "isError", False)))
        self.assertIn("Trap", str(genres.content))


if __name__ == "__main__":
    unittest.main()
