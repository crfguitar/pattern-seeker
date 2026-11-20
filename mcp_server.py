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
        "four-bar chord progression on the keys channel, a soft pad on the synth "
        "channel and, in rock and country, a guitar part. Call fl_status first to see the rack and tempo, list_genres to pick a "
        "style, then new_beat. Every new_beat can be undone with back. Each call to "
        "new_beat gives a different groove and progression, so call it again when the "
        "user wants 'another one'. When the rack lacks a part (no drums, no keys, no "
        "pad), build it first: list_sounds finds instruments and samples on this PC, "
        "add_channel loads one into a new channel, channel_params and set_channel "
        "shape it. build_rack (or new_beat with build=true) does all of that for a "
        "genre in one call. Name new channels Kick, Snare, Clap, Hat, 808, Piano or Pad so "
        "new_beat knows what to write on them."),
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
             passing: bool = False, build: bool = False, guitar: bool = True) -> dict:
    """Write a fresh beat onto FL Studio's current pattern (or a new one).

    genre: a name from list_genres, or 'auto' to pick one that fits the project tempo.
    key: C, C#, D ... B (flats like Bb work too). scale: 'minor' or 'major'.
    bass / chords / pad / guitar: write the bass line, the keys chords, the pad,
      the guitar (rock: power chords; country: picking; other genres have none).
      A part that is off leaves its channel exactly as it was.
    play: start FL's transport. set_tempo: change FL's tempo to suit the genre.
    tempo: an exact BPM (e.g. 90) to set FL to; use it whenever the user names a
      tempo. With genre 'auto' it also picks a genre that fits that tempo.
    passing: end the progression on a passing diminished chord a semitone under the
      first chord (B dim leading back to C), on the last beat or two of bar four.
    new_pattern: write into a new empty pattern instead of the selected one.
    build: first build the genre's rack (see build_rack): a channel is added for
      every part the rack has no channel for, then the beat is written on them.
      Use it when the rack is empty or lacks parts, or when asked to build / set
      up the instruments. Channels added can't be removed from here. The result
      lists them under `built`.

    A part is only written to a channel whose sound suits the genre: classical
    plays a "Cello" channel and never an 808, rock a "Rock Kick". Plainly named
    channels ("Kick", "Bass") suit every genre. Channels of other kits are silenced
    in this pattern. Parts with no fitting channel come back under noChannelFor:
    offer build=true. Returns the
    genre, the chord progression, which channel got which part, and any warnings.
    FL briefly opens the piano roll while chords are written - that is expected."""
    try:
        return dict(ok=True, **engine.new_beat(genre, key, scale, bass, chords, pad,
                                               play, set_tempo, new_pattern, tempo,
                                               passing, build, guitar))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def write_part(channel: int | str, notes: list[list[float]]) -> dict:
    """Play your own notes on any channel - a solo, a melody, a riff - by writing
    them into that channel's piano roll on the current pattern.

    channel: the rack index fl_status shows (0 = first channel) or the channel name.
    notes: [[pitch, start, length, velocity], ...]. pitch is a MIDI note (60 = C5 in
      FL, middle C). start and length are in beats from the pattern start (beat 0 =
      bar 1; a 4-bar pattern is 16 beats); fractions are allowed and need not sit on
      the grid (0.1667 = a sixteenth-note triplet). velocity 1-127.

    Calling it again on the same channel replaces the notes it wrote before; notes
    you entered by hand stay. Undo with back. Use fl_status first for the channel
    and lastBeat (key, chords) so the part fits the beat."""
    try:
        return dict(ok=True, **engine.write_part(channel, notes))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def build_rack(genre: str, parts: list[str] | None = None) -> dict:
    """Build the instruments a genre needs: adds a channel, with a fitting stock
    sound loaded, named and coloured, for each part the rack has no channel for.

    genre: a name from list_genres (not 'auto').
    parts: limit it to some of: drums (= kick, snare, clap, hat, openhat, perc),
      bass, chords, pad, guitar. Default: every part the genre has.
    Trap gets 808 drums, an 808 bass, a dark piano and a pad; house gets 909s, a
    synth bass and a dance piano; rock the HQ Rock drum kit, a picked rock bass, a
    piano and an overdriven guitar; jazz the HQ Jazz kit with a ride, an upright
    bass and a Rhodes; country an acoustic kit, a bass and a clean bright guitar;
    classical a cello, a grand piano and strings, and no drums. Channels are named
    after their sound ("Rock Kick", "Cello") and a part counts as there only when
    its channel has the genre's kind of sound, so a rack can hold several kits.
    Parts already there are listed under `kept`.

    Takes a few seconds per channel and FL comes to the front. Channels can't be
    removed from here. To build and write a beat in one go use new_beat(build=true)."""
    try:
        return dict(ok=True, **engine.build_rack(genre, parts))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def list_sounds(search: str = "", kind: str = "all", limit: int = 40) -> dict:
    """Find instruments and samples on this PC that add_channel can load.

    search: words that must all appear in the sound's id, e.g. "909 kick", "flex",
      "snare trap", "3x osc pad". Empty lists everything.
    kind: 'instrument' (every plugin FL has scanned - native and VST - plus saved
      channel presets), 'sample' (FL's packs and the user's sample folders) or 'all'.
    Returns ids such as "Fruity/FLEX" or "Drums/Kicks/909 Kick"; `total` says how
    many matched when more than `limit` did."""
    try:
        return dict(ok=True, **engine.list_sounds(search, kind, limit))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def add_channel(sound: str, name: str | None = None, color: str | None = None,
                volume: float | None = None, pan: float | None = None,
                show: bool = False) -> dict:
    """Add a new channel to FL's rack with an instrument or a sample loaded in it.

    sound: an id or name from list_sounds ("FLEX", "Drums/Kicks/909 Kick"), or the
      full path of a .fst preset or an audio file.
    name: what to call the channel. new_beat finds its channels by name, so use
      Kick, Snare, Clap, Hat, Open hat, Perc, 808 (or Bass), Piano (or Keys), Pad.
    color: "#RRGGBB". volume: 0 to 1 (FL's default is 0.78). pan: -1 left to 1 right.
    show: leave the plugin's window open (it is closed by default).

    FL Studio comes to the front while it loads. The channel goes at the end of
    the rack; returns its index and the role new_beat will give it. There is no
    undo for this: the user removes a channel in FL (right-click > Delete)."""
    try:
        return dict(ok=True, **engine.add_channel(sound, name, color, volume, pan, show))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def channel_params(channel: int | str, search: str = "", limit: int = 60,
                   presets: bool = False) -> dict:
    """What can be shaped on a channel: its color, volume, pan and - when it holds
    a plugin - the plugin's parameters and presets.

    channel: rack index or channel name. search: only parameters whose name
    contains this ("cutoff", "attack", "reverb"); a VST can have hundreds.
    presets: also list the names of the plugin's presets (presetCount is always
    given). FL cannot say which preset is loaded until set_channel loads one.
    Each parameter has an index, a name, a value from 0 to 1 and, when the plugin
    gives one, the text it shows for that value ("shows")."""
    try:
        return dict(ok=True, **engine.channel_params(channel, search, limit, presets))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def set_channel(channel: int | str, name: str | None = None, color: str | None = None,
                volume: float | None = None, pan: float | None = None,
                params: dict[str, float] | None = None, preset: int = 0,
                preset_name: str | None = None, show: bool | None = None) -> dict:
    """Shape a channel: rename, recolour, level, pan, plugin preset and parameters.

    channel: rack index or channel name.
    name / color ("#RRGGBB") / volume (0 to 1) / pan (-1 to 1): the channel itself.
    preset_name: load the plugin preset with this name (or the only one containing
      it); names come from channel_params(presets=true).
    preset: or step through the presets: 1 = next, -1 = previous, 5 = five on.
    params: {parameter name or index: value}, every value from 0 to 1, e.g.
      {"Decay": 0.3, "Release": 0.6}. Get names from channel_params. A name may be
      a part of the real one when only one parameter contains it. Presets are
      stepped before parameters are set.
    show: true opens the plugin's window, false closes it.

    Returns the channel as it is now, the parameters changed (with the text the
    plugin shows) and any names that matched nothing (unknownParams)."""
    try:
        return dict(ok=True, **engine.set_channel(channel, name, color, volume, pan,
                                                  params, preset, preset_name, show))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def back() -> dict:
    """Undo the last new_beat or write_part (or the one before, when called again):
    restores the exact steps, 808 notes, chords, pad and parts the pattern held before."""
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
