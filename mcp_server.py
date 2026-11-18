"""Pattern Seeker MCP server - genre-true beats in FL Studio, from any MCP client.

Lets an AI assistant (Claude Desktop, Claude Code, ...) do what the Pattern
Seeker window does: write a fresh drum groove, a 808 line, chords and a pad onto
the current FL Studio pattern, in a key and scale it picks, and undo it again.

    python mcp_server.py          # stdio transport; an MCP client starts this

Talks to FL through the Pattern Seeker controller script over two loopMIDI
ports (see README.md). Nothing may print to stdout: stdout is the MCP channel.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:                                    # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP  # noqa: E402
except ImportError:                     # 1.x
    from mcp.server.fastmcp import FastMCP  # noqa: E402

from seeker import link  # noqa: E402
from seeker.engine import Engine, SeekerError, genre_list  # noqa: E402
from seeker.generator import KEYS  # noqa: E402

mcp = FastMCP(
    "pattern-seeker",
    instructions=(
        "Pattern Seeker writes genre-authentic beats straight into FL Studio's channel "
        "rack: drums (kick, snare, clap, hats, percussion), an in-key 808 line, a "
        "four-bar chord progression on the keys channel and a soft pad on the synth "
        "channel. Call fl_status first to see the rack and tempo, list_genres to pick a "
        "style, then new_beat. Every new_beat can be undone with back. Each call to "
        "new_beat gives a different groove and progression, so call it again when the "
        "user wants 'another one'."),
)
engine = Engine()


def _fail(e):
    return {"ok": False, "error": str(e)}


@mcp.tool()
def list_genres() -> list[dict]:
    """List the genres Pattern Seeker knows, with the tempo range each one is
    idiomatic at. Use the name (or 'auto') as the genre for new_beat."""
    return [{"name": name, "bpm": {"min": lo, "max": hi}} for _, name, (lo, hi) in genre_list()]


@mcp.tool()
def fl_status() -> dict:
    """Is FL Studio connected? Returns the current pattern, tempo, whether it is
    playing, and every channel in the rack with the role Pattern Seeker gives it
    (kick, snare, clap, hat, openhat, perc, bass, chords, pad, or null = left alone)."""
    try:
        return engine.status()
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def new_beat(genre: str = "auto", key: str = "C", scale: str = "minor",
             bass: bool = True, chords: bool = True, pad: bool = True,
             play: bool = True, set_tempo: bool = False,
             new_pattern: bool = False, tempo: float | None = None,
             passing: bool = False) -> dict:
    """Write a fresh beat onto FL Studio's current pattern (or a new one).

    genre: a name from list_genres, or 'auto' to pick one that fits the project tempo.
    key: C, C#, D ... B (flats like Bb work too). scale: 'minor' or 'major'.
    bass / chords / pad: write the 808 line, the keys chords, the synth pad.
      A part that is off leaves its channel exactly as it was.
    play: start FL's transport. set_tempo: change FL's tempo to suit the genre.
    tempo: an exact BPM (e.g. 90) to set FL to; use it whenever the user names a
      tempo. With genre 'auto' it also picks a genre that fits that tempo.
    passing: end the progression on a passing diminished chord a semitone under the
      first chord (B dim leading back to C), on the last beat or two of bar four.
    new_pattern: write into a new empty pattern instead of the selected one.

    Only channels recognised as drums/808/keys/synth are touched. Returns the
    genre, the chord progression, which channel got which part, and any warnings.
    FL briefly opens the piano roll while chords are written - that is expected."""
    try:
        return dict(ok=True, **engine.new_beat(genre, key, scale, bass, chords, pad,
                                               play, set_tempo, new_pattern, tempo,
                                               passing))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def back() -> dict:
    """Undo the last new_beat (or the one before, when called again): restores the
    exact steps, 808 notes, chords and pad the pattern held before."""
    try:
        return dict(ok=True, **engine.back())
    except SeekerError as e:
        return _fail(e)


@mcp.resource("pattern-seeker://keys")
def keys() -> str:
    """The keys new_beat accepts."""
    return ", ".join(KEYS)


def main():
    state = link.install_script()     # keep FL's copy of the controller script current
    if state in ("installed", "updated"):
        print("Pattern Seeker: FL script %s - reload it in FL (View > Script output)." % state,
              file=sys.stderr)
    try:
        mcp.run()
    finally:
        link.close()


if __name__ == "__main__":
    main()
