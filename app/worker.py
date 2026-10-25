"""Wątek w tle przetwarzający kolejkę job_items."""
import logging
import os
import shutil
import threading
import time

from . import db, downloader, paths

log = logging.getLogger(__name__)

_wake = threading.Event()
_thread = None
_lock = threading.Lock()


def notify():
    """Budzi worker po dodaniu nowego zlecenia."""
    _wake.set()


def start(db_path, output_root, temp_dir, poll_seconds):
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        # Resztki po przerwanym pobieraniu; pozycja i tak wraca do kolejki i pobierze się od nowa.
        shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)
        _thread = threading.Thread(
            target=_run, args=(db_path, output_root, temp_dir, poll_seconds), name="yt-worker", daemon=True
        )
        _thread.start()


def _run(db_path, output_root, temp_dir, poll_seconds):
    conn = db.connect(db_path)
    log.info("Worker wystartował")
    while True:
        try:
            item = db.next_queued_item(conn)
        except Exception:
            log.exception("Błąd odczytu kolejki")
            time.sleep(poll_seconds)
            continue
        if item is None:
            _wake.wait(poll_seconds)
            _wake.clear()
            continue
        try:
            _process(conn, item, output_root, temp_dir)
        except Exception as e:
            log.exception("Błąd przetwarzania pozycji %s (%s)", item["id"], item["yt_id"])
            try:
                db.set_item_status(conn, item["id"], "error", str(e) or type(e).__name__)
            except Exception:
                log.exception("Nie udało się zapisać błędu pozycji %s", item["id"])
                time.sleep(poll_seconds)


def _process(conn, item, output_root, temp_dir):
    job = db.get_job(conn, item["job_id"])
    db.set_item_status(conn, item["id"], "running")
    if item["kind"] == "playlist":
        _process_playlist(conn, item)
    else:
        _process_video(conn, item, job, output_root, temp_dir)


def _process_playlist(conn, item):
    log.info("Rozwijam playlistę %s", item["yt_id"])
    try:
        title, entries = downloader.expand_playlist(item["yt_id"])
    except downloader.DownloaderError as e:
        db.set_item_status(conn, item["id"], "error", str(e))
        return
    db.finish_playlist(conn, item, title, entries)


def _process_video(conn, item, job, output_root, temp_dir):
    video_id = item["yt_id"]

    existing = db.get_video(conn, video_id)
    if existing and not job["overwrite"]:
        db.set_item_status(conn, item["id"], "skipped", f"Już pobrany: {existing['file_path']}",
                           title=existing["title"])
        return
    # Z „nadpisuj” ten sam film powtórzony w kilku playlistach zlecenia i tak pobieramy tylko raz.
    if job["overwrite"] and db.video_done_in_job(conn, job["id"], video_id):
        db.set_item_status(conn, item["id"], "skipped", "Już pobrany w tym zleceniu",
                           title=existing["title"] if existing else None)
        return

    out_dir = paths.resolve_out_dir(output_root, job["out_dir"])
    os.makedirs(out_dir, exist_ok=True)

    log.info("Pobieram %s do %s (%s kbps)", video_id, job["out_dir"], job["quality"])
    try:
        result = downloader.download_video(video_id, out_dir, temp_dir, job["quality"], bool(job["overwrite"]))
    except downloader.DownloaderError as e:
        db.set_item_status(conn, item["id"], "error", str(e))
        return

    rel_path = os.path.relpath(result["filepath"], os.path.realpath(output_root)).replace(os.sep, "/")
    db.upsert_video(conn, video_id, result["title"], result["channel"], result["upload_date"],
                    rel_path, job["quality"])
    db.set_item_status(conn, item["id"], "done", rel_path, title=result["title"])
