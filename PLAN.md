# YT → MP3: plan aplikacji Flask

> Wytyczne do implementacji, uzgodnione na konsultacjach 2026-10-18. Kodowanie rusza na osobne polecenie.

## Kontekst
Prosta aplikacja webowa (Flask + yt_dlp), która z linków do filmów i playlist YouTube (albo z samych ID filmów) robi pliki mp3. ID przetworzonych filmów trafiają do bazy, żeby nie pobierać ich drugi raz. Frontend jest minimalny: bez JS, czysty HTML z odrobiną CSS. Całość działa w Dockerze z dwoma zamontowanymi katalogami: na pliki wyjściowe i na config (bazę).

## Ustalenia z konsultacji
| Temat | Decyzja |
|---|---|
| Tryb pracy | Jeden wątek w tle bierze zadania z kolejki trzymanej w SQLite; osobna strona statusu odświeża się przez meta refresh |
| Link na liście plików | Tylko link do filmu na YouTube |
| Nazwa pliku | `YYYY-MM-DD - Tytuł - Kanał.mp3` |
| Duplikaty | Liczone globalnie po ID filmu, niezależnie od ścieżki |
| Nadpisywanie (opcja) | Domyślnie NIE. Gdy TAK, pobieramy ponownie do nowej ścieżki, aktualizujemy wpis w bazie, a stary plik w innym katalogu **zostaje** |
| Jakości | CBR 64/96/128/192/256/320 kbps, domyślnie 64 |
| Metadane | Tylko tagi tekstowe ID3: tytuł, artysta = kanał, data, URL. Bez okładki |
| Baza | SQLite, plik w katalogu config |
| Dostęp | Bez autoryzacji (LAN) |
| `watch?v=X&list=Y` | Traktowany jako **pojedynczy film**: `list=` jest ignorowane, gdy jest też `v=` |
| Aktualizacja yt-dlp | Wersja przypięta w `requirements.txt`; aktualizacja to podbicie wersji i rebuild obrazu |

## Struktura projektu
```
yt_playlist_to_mp3/
  app/
    __init__.py      # create_app(): config, init bazy, start wątku workera
    config.py        # OUTPUT_ROOT, DB_PATH, QUALITIES, DEFAULT_QUALITY, DEFAULT_OUT_DIR (z env)
    db.py            # schemat, połączenia, zapytania
    links.py         # parsowanie linii wejściowych na (kind, yt_id)
    paths.py         # walidacja i rozwiązywanie względnej ścieżki wyjściowej
    downloader.py    # wrappery yt_dlp: expand_playlist(), download_video()
    worker.py        # pętla wątku w tle
    routes.py        # widoki Flask
    templates/       # base.html, index.html, jobs.html, files.html
  tests/             # test_links.py, test_paths.py (pytest)
  requirements.txt   # Flask, gunicorn, yt-dlp[default]==<przypięta>
  Dockerfile
  docker-compose.yml
  .dockerignore
  README.md
```

## Model danych (SQLite, tryb WAL)
- **videos**: ewidencja przetworzonych filmów, źródło prawdy dla deduplikacji.
  `video_id` (PK), `title`, `channel`, `upload_date`, `file_path` (względem OUTPUT_ROOT), `quality`, `processed_at` (UTC, ISO).
- **jobs**: jedno wysłanie formularza.
  `id`, `created_at`, `quality`, `out_dir`, `overwrite`.
- **job_items**: pozycje zlecenia.
  `id`, `job_id`, `parent_id` (filmy rozwinięte z playlisty wskazują na nią), `kind` (`video`/`playlist`), `yt_id`, `title`, `status` (`queued`/`running`/`done`/`skipped`/`error`), `message`, `updated_at`.

Każdy wątek ma własne połączenie: request przez `flask.g`, worker osobno.

## Parsowanie wejścia (`links.py`)
Każdą niepustą linię przycinamy z białych znaków, a powtórzenia w obrębie jednego zgłoszenia usuwamy.
- Samo `^[A-Za-z0-9_-]{11}$` to zawsze **film**.
- URL z hostem youtube.com, m./www./music.youtube.com, youtu.be lub youtube-nocookie.com:
  - parametr `v=` → film (`list=` ignorowane)
  - `youtu.be/<id>`, `/shorts/<id>`, `/live/<id>`, `/embed/<id>` → film
  - `/playlist?list=<id>` → playlista
  - każdy inny URL (np. kanał `/@nazwa`) → błąd linii.
- Jeśli którakolwiek linia jest błędna, formularz wraca z listą błędnych linii i zachowaną treścią pola, a do kolejki nic nie trafia.

## Ścieżka wyjściowa (`paths.py`)
- Puste pole oznacza `default`. Odrzucamy ścieżki absolutne, litery dysków i składowe `..`.
- Rozwiązana ścieżka musi leżeć wewnątrz `OUTPUT_ROOT` (`/data/output`). Katalogi tworzymy w razie potrzeby.

## Worker (`worker.py`)
- Jeden wątek daemon startuje w `create_app()`. W trybie debug pilnujemy, żeby reloader nie uruchomił go drugi raz.
- W pętli bierze najstarszą pozycję `queued`. Jest budzony przez `threading.Event` po wysłaniu formularza, a dodatkowo sprawdza kolejkę co kilka sekund.
- **Playlista**: `expand_playlist()` (yt_dlp, `extract_flat`) wstawia pozycje `video` z `parent_id` i zapisuje tytuł playlisty. Prywatne lub usunięte filmy dostają status `error` z komunikatem.
- **Film**:
  - jest w `videos` i `overwrite=False` → status `skipped` (nawet jeśli pliku już nie ma na dysku, bo baza jest źródłem prawdy)
  - w pozostałych przypadkach wywołujemy `download_video()`, robimy upsert do `videos` i ustawiamy `done`
  - wyjątek → `error` z treścią błędu. Film nie trafia wtedy do `videos`, więc ponowne zgłoszenie spróbuje go pobrać jeszcze raz.
- Filmy przetwarzamy po kolei, dzięki czemu ten sam film w dwóch playlistach jednego zlecenia pobiera się tylko raz.
- Po restarcie pozycje `running` wracają do `queued`. Kolejka żyje w bazie, więc nic się nie gubi.

## Pobieranie (`downloader.py`), opcje yt_dlp
- `format: bestaudio/best`, `noplaylist: True`, `quiet: True`
- `outtmpl`: `<dir>/%(upload_date>%Y-%m-%d)s - %(title).150B - %(channel,uploader)s.%(ext)s` (z wartością zastępczą, gdy brakuje daty)
- `windowsfilenames: True`, żeby nazwy były bezpieczne także przy dostępie przez SMB lub z Windows
- postprocesory:
  - `FFmpegExtractAudio` (`mp3`, `preferredquality=<kbps>`)
  - `MetadataParser`: `%(channel)s` → `meta_artist`
  - `FFmpegMetadata` (bez opisu i okładki)
- `overwrites` = wartość opcji z formularza. Gdy `False`, a mp3 już leży na dysku bez wpisu w bazie, yt-dlp pomija pobranie, a my tylko rejestrujemy plik w bazie.
- Ścieżkę końcową bierzemy z `info["requested_downloads"][0]["filepath"]` i zapisujemy względem OUTPUT_ROOT.

## Frontend (Jinja, bez JS)
`base.html` zawiera nawigację (Nowe / Status / Pliki) i kilka linijek inline CSS.
1. **`GET/POST /`**: formularz z polem `textarea` na linki/ID, listą jakości (64 domyślnie), polem ścieżki względnej (`default`) i checkboxem „nadpisuj” (domyślnie odznaczony). POST tworzy job i przekierowuje na `/jobs`.
2. **`GET /jobs`**: ostatnie ~20 zleceń z pozycjami, statusami i komunikatami błędów; filmy z playlisty są wcięte pod nią. `<meta refresh=5>` dodajemy tylko wtedy, gdy coś jest `queued` lub `running`.
3. **`GET /files`**: tabela `videos` od najnowszych. Kolumny: data przetworzenia (w czasie lokalnym z TZ), tytuł jako link `https://www.youtube.com/watch?v=<id>`, kanał, data publikacji, ścieżka pliku, jakość.

## Docker
- **Dockerfile**: `python:3.12-slim` + `apt-get install ffmpeg` + binarka Deno (`COPY --from=denoland/deno:bin-<wersja> /deno /usr/local/bin/deno`). Obecny yt-dlp potrzebuje zewnętrznego runtime'u JS (oraz `yt-dlp-ejs`, który przychodzi z `yt-dlp[default]`) do pełnej obsługi YouTube; przy implementacji trzeba to sprawdzić z aktualną dokumentacją yt-dlp. Dalej: `pip install -r requirements.txt`, użytkownik bez roota, `EXPOSE 5000`.
- **CMD**: `gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 "app:create_app()"`. Musi być **jeden** worker gunicorna, bo wątek pobierający żyje w procesie.
- **docker-compose.yml**: port `5000:5000`, wolumeny `./data/output:/data/output` i `./data/config:/data/config`, zmienne `TZ=Europe/Warsaw`, `OUTPUT_ROOT`, `DB_PATH=/data/config/app.db`, ustawienie `user: "${UID:-1000}:${GID:-1000}"`, `restart: unless-stopped`.
- **README**: uruchomienie, aktualizacja yt-dlp (podbić wersję w `requirements.txt`, potem `docker compose build && docker compose up -d`), lokalny dev na Windows (wymaga ffmpeg i deno w PATH, start przez `flask --app app run`).

## Poza zakresem (świadomie)
Autoryzacja, cookies dla filmów z ograniczeniem wieku, okładki, usuwanie wpisów z UI, równoległe pobieranie, linki do kanałów.

## Weryfikacja
1. `pytest`: testy parsowania linków (ID, watch z list=, youtu.be, shorts, playlist, kanał jako błąd) i walidacji ścieżek (`..`, ścieżka absolutna, puste pole).
2. `docker compose up --build`, potem w przeglądarce `http://localhost:5000`:
   - wklejenie samego ID krótkiego filmu daje plik `default/YYYY-MM-DD - Tytuł - Kanał.mp3` z bitrate 64 kbps i tagami (sprawdzić `ffprobe`)
   - krótka playlista do ścieżki `test/sub`: pliki trafiają do tego podkatalogu, a status pokazuje postęp
   - ponowne wysłanie tych samych linków: pozycje `skipped`
   - ponowne wysłanie z „nadpisuj” i inną ścieżką: nowy plik jest w nowym miejscu, stary zostaje, wpis w `/files` jest zaktualizowany
   - błędny link: formularz wraca z błędem i zachowaną treścią
   - restart kontenera w trakcie pracy: kolejka zostaje dokończona, a baza przetrwała w `./data/config`.
