"""Parsowanie linii wejściowych formularza na pary (kind, yt_id)."""
import re
from urllib.parse import parse_qs, urlsplit

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
}
SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
VIDEO_PATH_PREFIXES = {"shorts", "live", "embed"}


class LinkError(ValueError):
    pass


def _video(video_id):
    if not video_id or not VIDEO_ID_RE.match(video_id):
        raise LinkError("nieprawidłowe ID filmu")
    return "video", video_id


def parse_line(line):
    """Zwraca ("video" | "playlist", yt_id) albo rzuca LinkError."""
    line = line.strip()
    if VIDEO_ID_RE.match(line):
        return "video", line

    url = line if "://" in line else "https://" + line
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        raise LinkError("nieprawidłowy URL") from None
    if parts.scheme not in ("http", "https"):
        raise LinkError("nieprawidłowy URL")

    query = parse_qs(parts.query)
    segments = [s for s in parts.path.split("/") if s]

    if host in SHORT_HOSTS:
        return _video(segments[0] if segments else None)

    if host not in YOUTUBE_HOSTS:
        raise LinkError("to nie jest link do YouTube")

    # watch?v=X&list=Y traktujemy jako pojedynczy film.
    if "v" in query:
        return _video(query["v"][0])

    playlist_id = query.get("list", [None])[0]
    if segments[:1] == ["playlist"] or segments == ["embed", "videoseries"]:
        if playlist_id and PLAYLIST_ID_RE.match(playlist_id):
            return "playlist", playlist_id
        raise LinkError("nieprawidłowe ID playlisty")

    if len(segments) >= 2 and segments[0] in VIDEO_PATH_PREFIXES:
        return _video(segments[1])

    raise LinkError("nieobsługiwany link (obsługiwane są filmy i playlisty)")


def parse_input(text):
    """Zwraca (items, errors).

    items: lista unikalnych (kind, yt_id) w kolejności wystąpienia,
    errors: lista (numer_linii, treść, komunikat).
    """
    items, errors, seen = [], [], set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = parse_line(line)
        except LinkError as e:
            errors.append((lineno, line, str(e)))
            continue
        if item not in seen:
            seen.add(item)
            items.append(item)
    return items, errors
