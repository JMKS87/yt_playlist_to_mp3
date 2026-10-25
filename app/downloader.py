"""Wrappery yt_dlp: rozwijanie playlist i pobieranie pojedynczego filmu do mp3."""
import yt_dlp
from yt_dlp.postprocessor.metadataparser import MetadataParserPP
from yt_dlp.utils import DownloadError

OUTTMPL = "%(upload_date>%Y-%m-%d|0000-00-00)s - %(title).150B - %(channel,uploader)s.%(ext)s"

# Tagi, które FFmpegMetadata dodałby sam z siebie, a których nie chcemy (np. genre = tagi filmu).
# Pusta wartość meta_<tag> sprawia, że ffmpeg nie zapisuje tagu.
_DROPPED_TAGS = (
    "description", "synopsis", "genre", "album", "album_artist", "composer", "track", "disc", "show",
)

_INTERPRET = MetadataParserPP.Actions.INTERPRET
_METADATA_ACTIONS = [
    (_INTERPRET, "%(title)s", "%(meta_title)s"),
    (_INTERPRET, "%(channel,uploader|)s", "%(meta_artist)s"),
    (_INTERPRET, "%(upload_date>%Y-%m-%d|)s", "%(meta_date)s"),
    *((_INTERPRET, "", f"(?P<meta_{tag}>)") for tag in _DROPPED_TAGS),
]

_UNAVAILABLE_TITLES = {"[Private video]", "[Deleted video]"}


class DownloaderError(Exception):
    pass


def _clean_error(e):
    msg = str(e)
    return msg.removeprefix("ERROR: ").strip()


def _format_date(yyyymmdd):
    if yyyymmdd and len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return None


def expand_playlist(playlist_id):
    """Zwraca (tytuł_playlisty, [(video_id, tytuł, błąd | None), ...])."""
    opts = {"extract_flat": "in_playlist", "quiet": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    except DownloadError as e:
        raise DownloaderError(_clean_error(e)) from None

    entries = []
    for entry in info.get("entries") or []:
        if not entry or not entry.get("id"):
            continue
        title = entry.get("title")
        error = None
        if title in _UNAVAILABLE_TITLES or entry.get("availability") == "private":
            error = f"Film niedostępny: {title or 'prywatny'}"
        entries.append((entry["id"], title, error))
    return info.get("title"), entries


def download_video(video_id, out_dir, temp_dir, quality, overwrite):
    """Pobiera film jako mp3 do `out_dir` (ścieżka absolutna).

    Pobieranie i konwersja odbywają się w `temp_dir`, więc przerwana praca nie zostawia
    w `out_dir` niepełnego pliku, który przy kolejnej próbie zostałby uznany za gotowy.

    Zwraca słownik: title, channel, upload_date (YYYY-MM-DD | None), filepath (absolutna).
    """
    opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "paths": {"home": out_dir, "temp": temp_dir},
        "outtmpl": OUTTMPL,
        "windowsfilenames": True,
        "overwrites": overwrite,
        # Bez tego yt-dlp nie zauważy gotowego .mp3 i pobierze film jeszcze raz.
        "final_ext": "mp3",
        "postprocessors": [
            {"key": "MetadataParser", "when": "pre_process", "actions": _METADATA_ACTIONS},
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(quality)},
            {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": False, "add_infojson": False},
        ],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
    except DownloadError as e:
        raise DownloaderError(_clean_error(e)) from None

    downloads = info.get("requested_downloads") or []
    if not downloads or not downloads[0].get("filepath"):
        raise DownloaderError("yt-dlp nie zwrócił ścieżki pliku")
    return {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "upload_date": _format_date(info.get("upload_date")),
        "filepath": downloads[0]["filepath"],
    }
