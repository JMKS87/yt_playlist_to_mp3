import pytest

from app.links import LinkError, parse_input, parse_line

VID = "dQw4w9WgXcQ"
PL = "PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI"


@pytest.mark.parametrize("line, expected", [
    (VID, ("video", VID)),
    (f"  {VID}  ", ("video", VID)),
    (f"https://www.youtube.com/watch?v={VID}", ("video", VID)),
    (f"https://www.youtube.com/watch?v={VID}&list={PL}&index=3", ("video", VID)),
    (f"https://www.youtube.com/watch?list={PL}&v={VID}", ("video", VID)),
    (f"https://m.youtube.com/watch?v={VID}", ("video", VID)),
    (f"https://music.youtube.com/watch?v={VID}&si=abc", ("video", VID)),
    (f"youtube.com/watch?v={VID}", ("video", VID)),
    (f"http://youtube.com/watch?v={VID}", ("video", VID)),
    (f"https://youtu.be/{VID}", ("video", VID)),
    (f"https://youtu.be/{VID}?si=xyz&t=42", ("video", VID)),
    (f"https://youtu.be/{VID}?list={PL}", ("video", VID)),
    (f"https://www.youtube.com/shorts/{VID}", ("video", VID)),
    (f"https://www.youtube.com/live/{VID}?feature=share", ("video", VID)),
    (f"https://www.youtube.com/embed/{VID}", ("video", VID)),
    (f"https://www.youtube-nocookie.com/embed/{VID}?start=10", ("video", VID)),
    (f"https://WWW.YouTube.com/watch?v={VID}", ("video", VID)),
    (f"https://www.youtube.com/playlist?list={PL}", ("playlist", PL)),
    (f"https://music.youtube.com/playlist?list={PL}", ("playlist", PL)),
    (f"https://www.youtube.com/embed/videoseries?list={PL}", ("playlist", PL)),
])
def test_parse_line_ok(line, expected):
    assert parse_line(line) == expected


@pytest.mark.parametrize("line", [
    "https://www.youtube.com/@nazwa",
    "https://www.youtube.com/@nazwa/videos",
    "https://www.youtube.com/channel/UC1234567890abcdefghijk",
    "https://www.youtube.com/c/nazwa",
    "https://www.youtube.com/",
    "https://www.youtube.com/watch?v=za_krotkie",
    "https://www.youtube.com/watch?v=",
    "https://www.youtube.com/playlist",
    "https://www.youtube.com/playlist?list=zle!znaki",
    f"https://www.youtube.com/watch?list={PL}",
    "https://youtu.be/",
    f"https://vimeo.com/watch?v={VID}",
    f"https://youtube.com.evil.example/watch?v={VID}",
    f"ftp://youtube.com/watch?v={VID}",
    "dQw4w9WgXc",
    "dQw4w9WgXcQQ",
    "dQw4w9WgX!Q",
    "coś zupełnie innego",
])
def test_parse_line_error(line):
    with pytest.raises(LinkError):
        parse_line(line)


def test_parse_input_skips_blank_lines_and_deduplicates():
    text = f"""
    {VID}

    https://youtu.be/{VID}
    https://www.youtube.com/playlist?list={PL}
    https://www.youtube.com/watch?v=aaaaaaaaaaa&list={PL}
    https://www.youtube.com/playlist?list={PL}
    """
    items, errors = parse_input(text)
    assert errors == []
    assert items == [("video", VID), ("playlist", PL), ("video", "aaaaaaaaaaa")]


def test_parse_input_reports_bad_lines_with_numbers():
    text = f"{VID}\nhttps://www.youtube.com/@kanal\n\nzle\n"
    items, errors = parse_input(text)
    assert items == [("video", VID)]
    assert [(lineno, line) for lineno, line, _ in errors] == [
        (2, "https://www.youtube.com/@kanal"),
        (4, "zle"),
    ]


def test_parse_input_empty():
    assert parse_input("  \n\n ") == ([], [])
