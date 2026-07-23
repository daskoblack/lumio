"""Tests du regroupement de mots en captions et du formatage SRT."""

import pytest

from lectio.core.config import SubtitlesConfig
from lectio.core.models import Course, Script, Section, SectionKind
from lectio.pipeline.subtitles import _format_timestamp, _group_into_captions, generate_srt
from lectio.providers.stt.base import STTProvider, WordTiming


def _word(text: str, start: float, end: float) -> WordTiming:
    return WordTiming(word=text, start_s=start, end_s=end)


def test_format_timestamp():
    assert _format_timestamp(0) == "00:00:00,000"
    assert _format_timestamp(65.25) == "00:01:05,250"


def test_group_into_captions_respects_word_limit():
    config = SubtitlesConfig(max_chars_per_line=1000, max_lines=5, max_words_per_caption=3)
    words = [_word(f"w{i}", i, i + 0.5) for i in range(7)]
    captions = _group_into_captions(words, config)
    assert [c[2] for c in captions] == ["w0 w1 w2", "w3 w4 w5", "w6"]
    assert captions[0][0] == 0
    assert captions[0][1] == 2.5


def test_group_into_captions_respects_char_limit():
    config = SubtitlesConfig(max_chars_per_line=10, max_lines=1, max_words_per_caption=99)
    words = [_word("abcde", 0, 1), _word("fghij", 1, 2), _word("k", 2, 3)]
    captions = _group_into_captions(words, config)
    # "abcde fghij" = 11 chars > 10 -> coupe avant le 2e mot
    assert captions[0][2] == "abcde"
    assert captions[1][2] == "fghij k"


class _FakeSTT(STTProvider):
    def __init__(self, words_by_path: dict[str, list[WordTiming]]) -> None:
        self._words_by_path = words_by_path

    async def transcribe_words(self, audio_path: str, language: str) -> list[WordTiming]:
        return self._words_by_path[audio_path]


@pytest.mark.asyncio
async def test_generate_srt_offsets_by_section(tmp_path):
    sections = [
        Section(
            index=0, kind=SectionKind.INTRO, title="Intro", actual_duration_s=10.0,
            script=Script(section_id="", audio_path="a0.mp3"),
        ),
        Section(
            index=1, kind=SectionKind.CONCEPT, title="Concept", actual_duration_s=20.0,
            script=Script(section_id="", audio_path="a1.mp3"),
        ),
    ]
    course = Course(title="T", source_pdf="x.pdf", sections=sections)
    stt = _FakeSTT({
        "a0.mp3": [_word("bonjour", 0.0, 0.5)],
        "a1.mp3": [_word("suite", 0.0, 0.4)],  # doit être décalé de +10s dans le SRT final
    })

    out = tmp_path / "subs.srt"
    config = SubtitlesConfig()
    path = await generate_srt(stt, course, config, out)

    content = out.read_text(encoding="utf-8")
    assert path == str(out)
    assert "bonjour" in content
    assert "00:00:10" in content  # décalage cumulé appliqué à la 2e section
