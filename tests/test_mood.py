"""The island's face, decided from what the PC is doing."""

from __future__ import annotations

from leond import mood


def test_an_attention_ping_outranks_everything() -> None:
    face = mood.decide(attention=True, busy=True, playing=True, lyrics=4, held=3)
    assert (face.mood, face.mode) == ("alert", "glow")


def test_a_turn_in_flight_thinks() -> None:
    face = mood.decide(busy=True)
    assert (face.mood, face.mode) == ("think", "face")


def test_a_song_with_a_lyric_line_hides_the_face() -> None:
    face = mood.decide(playing=True, lyrics=2)
    assert face.mode == "lyrics"
    assert face.mood == "listen"


def test_playback_without_lyrics_uses_the_waveform() -> None:
    assert mood.decide(playing=True, lyrics=-1).mode == "wave"
    # A video whose player reports a track but no lyric file is the same case.
    assert mood.decide(playing=True, lyrics=-1, level=0.9).mode == "wave"


def test_held_files_are_worth_a_glad_face() -> None:
    face = mood.decide(held=2)
    assert (face.mood, face.mode) == ("glad", "files")
    assert face.note == "2 files held"
    assert face.held == 2


def test_one_held_file_is_not_plural() -> None:
    assert mood.decide(held=1).note == "1 file held"


def test_sound_without_a_media_session_still_reacts() -> None:
    face = mood.decide(level=0.4)
    assert (face.mood, face.mode) == ("listen", "wave")


def test_a_quiet_pc_is_calm_and_watching() -> None:
    face = mood.decide(level=0.004)
    assert (face.mood, face.mode) == ("calm", "face")


def test_the_payload_is_what_the_page_reads() -> None:
    payload = mood.payload(mood.decide(held=1))
    assert set(payload) == {"mood", "mode", "note", "held"}
    assert payload["mode"] == "files"


def test_every_decision_uses_a_known_face_and_mode() -> None:
    cases = [
        mood.decide(),
        mood.decide(busy=True),
        mood.decide(playing=True, lyrics=0),
        mood.decide(playing=True),
        mood.decide(held=1),
        mood.decide(level=0.5),
        mood.decide(attention=True),
    ]
    for face in cases:
        assert face.mood in mood.MOODS
        assert face.mode in mood.MODES
