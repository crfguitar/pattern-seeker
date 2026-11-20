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
        "new_beat knows what to write on them. For a whole song rather than a loop, "
        "new_song writes a pattern per section (verse, chorus, bridge) and lays them out "
        "in the playlist; arrange lays out patterns that already exist."),
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
             passing: bool = False, build: bool = False, guitar: bool = True,
             drums: bool = True) -> dict:
    """Write a fresh beat onto FL Studio's current pattern (or a new one).

    genre: a name from list_genres, or 'auto' to pick one that fits the project tempo.
    key: C, C#, D ... B (flats like Bb work too). scale: 'minor' or 'major'.
    bass / chords / pad / guitar: write the bass line, the keys chords, the pad,
      the guitar (rock: power chords; country: picking; other genres have none).
      A part that is off leaves its channel exactly as it was.
    drums: false writes no drums (a breakdown) and empties the drum channels.
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
                                               passing, build, guitar, drums))
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
                show: bool = False, route: bool = True) -> dict:
    """Add a new channel to FL's rack with an instrument or a sample loaded in it.

    sound: an id or name from list_sounds ("FLEX", "Drums/Kicks/909 Kick"), or the
      full path of a .fst preset or an audio file.
    name: what to call the channel. new_beat finds its channels by name, so use
      Kick, Snare, Clap, Hat, Open hat, Perc, 808 (or Bass), Piano (or Keys), Pad.
    color: "#RRGGBB". volume: 0 to 1 (FL's default is 0.78). pan: -1 left to 1 right.
    show: leave the plugin's window open (it is closed by default).
    route: send the channel through its own mixer insert, named and coloured
      after it (see route_channels). On by default.

    FL Studio comes to the front while it loads. The channel goes at the end of
    the rack; returns its index, its mixer insert and the role new_beat will give
    it. There is no undo for this: the user removes a channel in FL (right-click >
    Delete)."""
    try:
        return dict(ok=True, **engine.add_channel(sound, name, color, volume, pan, show,
                                                  route))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def route_channels(channels: list[int | str] | None = None, reroute: bool = False) -> dict:
    """Give channels their own mixer insert instead of summing them into the master:
    each channel is routed to a free insert, which is named and coloured after it.

    channels: rack indexes or names; default every channel still going straight to
      the master (fl_status shows each channel's `insert`, 0 = master).
    reroute: also move channels that already have an insert.

    A free insert is one no channel plays through and the user hasn't named. An
    insert already named like the channel (a template's labelled insert, e.g. one
    with an EQ on it) is used first; otherwise insert N for rack index N (FL's
    Sampler sits at index 0, so the first instrument gets insert 1) when it is
    free, else the lowest free insert. Effects on an insert are left as they
    are. add_channel and build_rack already route the channels they add."""
    try:
        return dict(ok=True, **engine.route_channels(channels, reroute))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def eq(channel: int | str, bands: list[dict], clear: bool = True) -> dict:
    """Set the EQ of one channel: CFilteR-01 (the user's Pro-Q 4 clone) on the
    channel's mixer insert, in real units.

    channel: rack index or channel name. It must have its own insert
      (route_channels) with CFilteR-01 in one of the insert's slots.
    bands: [{"shape": "low cut", "freq": 40, "slope": 12},
            {"shape": "bell", "freq": 65, "gain": -2, "q": 1.2}, ...]
      shape: bell, low shelf, low cut (= high pass), high shelf, high cut
      (= low pass), notch, band pass, tilt shelf, flat tilt, all pass.
      freq in Hz (10-30000), gain in dB (-30..30), q 0.025-40 (default 1),
      slope in dB/oct (0-96 or "brickwall"; default the plugin's 12).
      Optional "band" (1-24; default 1, 2, 3 in order), "on" (false = bypassed).
    clear: switch every other band off, so the EQ is exactly these bands.

    Returns each band as CFilteR-01 now shows it ("Low Cut 40.000 Hz ..."), read
    back from the plugin."""
    try:
        return dict(ok=True, **engine.eq(channel, bands, clear))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def mix_eq(genre: str, clear: bool = True) -> dict:
    """Give every part in the rack the genre's starting EQ, on CFilteR-01 on each
    channel's mixer insert: a low cut under each part, and the genre's own cuts
    and lifts so the parts fit together (e.g. jazz: the upright steps aside at the
    kick's 65 Hz, the Rhodes is cut below 140 Hz, the ride loses some 4 kHz ping).

    Starting points chosen from how the instruments sit, not by ear: invite the
    user to tune them, then use eq for a single channel. Channels without an
    insert or without CFilteR-01 come back under problems."""
    try:
        return dict(ok=True, **engine.mix_eq(genre, clear))
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
def new_song(genre: str = "auto", key: str = "C", scale: str = "minor",
             structure: str = "ABABCB", bars: int = 8, tempo: float | None = None,
             set_tempo: bool = False, build: bool = False, track: int = 1,
             start_bar: int | None = None, bass: bool = True, chords: bool = True,
             pad: bool = True, guitar: bool = True, passing: bool = False) -> dict:
    """Make a whole song, not a loop: a new pattern for every section, then the
    sections laid out along a playlist track as pattern clips.

    structure: one letter per section, in song order. A = verse (no pad, so it
      sits lower), B = chorus (every part), C = bridge (a breakdown without
      drums); any other letter is a full part of its own. "ABABCB" is verse
      chorus verse chorus bridge chorus; "AABA", "ABAB", "BABCB" work the same way.
      Every letter gets its own groove and chord progression; a repeated letter
      reuses its pattern, so both verses are the same.
    bars: how long each section lasts (8 by default; patterns are 4 bars and
      repeat to fill it). ABABCB at 8 bars is a 48-bar song.
    genre, key, scale, tempo, set_tempo, bass, chords, pad, guitar, passing,
      build: as in new_beat; they hold for the whole song.
    track: the playlist track the clips go on. start_bar: where the song starts;
      by default where the playlist's content ends now (bar 1 when it is empty).

    FL comes to the front and the mouse moves for a few seconds per section: the
    clips are clicked into the playlist, each one checked against what FL
    reports. The playlist must be open. FL is left in song mode, not playing.
    Returns the patterns (section, number, chords) and the arrangement (which
    bars each section covers). back takes the clips out again; calling back
    further empties the patterns."""
    try:
        return dict(ok=True, **engine.new_song(genre, key, scale, structure, bars, tempo,
                                               set_tempo, build, track, start_bar, bass,
                                               chords, pad, guitar, passing))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def arrange(sections: list[dict], track: int = 1, start_bar: int | None = None,
            song_mode: bool = True) -> dict:
    """Place patterns in FL's playlist as clips, one after another on a track:
    the step from loops to a song.

    sections: in song order, [{"pattern": 1, "bars": 8}, {"pattern": 2}, ...].
      pattern is the pattern number (new_beat returns it; fl_status shows the
      selected one). bars is how long the section lasts; a shorter pattern is
      repeated to fill it. Without bars the pattern is placed once.
    track: the playlist track (1 = the top one).
    start_bar: the bar the first section starts on. Leave it out to continue
      where the playlist's content ends now (bar 1 when it is empty), so calling
      arrange once per new pattern builds the song up section by section.
    song_mode: switch FL to song mode afterwards, so Play plays the arrangement.

    Use it after new_beat(new_pattern=true) to put that pattern in the song, or
    to lay out patterns the user made. FL comes to the front and the mouse moves
    while the clips are clicked in; the playlist must be open. It does not look
    for clips already on the track, so pick a free track or the end of the song.
    back takes the clips out again."""
    try:
        return dict(ok=True, **engine.arrange(sections, track, start_bar, song_mode))
    except SeekerError as e:
        return _fail(e)


@mcp.tool()
def back() -> dict:
    """Undo the last new_beat or write_part (or the one before, when called again):
    restores the exact steps, 808 notes, chords, pad and parts the pattern held before.
    After arrange or new_song it first takes the clips out of the playlist again
    (through FL's own undo, so it should follow straight after)."""
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
