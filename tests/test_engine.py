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
from seeker import engine as engine_mod, link, wire  # noqa: E402
from seeker.engine import Engine, SeekerError, resolve_genre, resolve_key  # noqa: E402


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

    def write_script(self, notes):
        self.written.append(notes)
        return True

    def find_piano_roll(self):
        return 1

    def bring_forward(self, hwnd):
        return True

    def run_from_menu(self, hwnd):
        self.script.OnRefresh(0x20000)      # what FL reports when a roll script edits
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

    def test_every_press_is_different(self):
        a = self.engine.new_beat("boom bap", chords=False, pad=False)
        b = self.engine.new_beat("boom bap", chords=False, pad=False)
        self.assertNotEqual(a["tag"], b["tag"])

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
        self.assertEqual(names, {"list_genres", "fl_status", "new_beat", "back"})
        self.assertFalse(getattr(genres, "is_error", getattr(genres, "isError", False)))
        self.assertIn("Trap", str(genres.content))


if __name__ == "__main__":
    unittest.main()
