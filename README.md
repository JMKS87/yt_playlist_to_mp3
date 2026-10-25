# YT → MP3

Prosta aplikacja webowa (Flask + yt-dlp), która z linków do filmów i playlist YouTube (albo z samych ID filmów)
robi pliki mp3. ID przetworzonych filmów trafiają do bazy SQLite, więc ten sam film nie pobierze się drugi raz.

- **Nowe** (`/`): wklejasz linki lub ID (jeden na linię), wybierasz jakość (CBR 64–320 kbps, domyślnie 64),
  katalog względny (domyślnie `default`) i opcję „nadpisuj”.
- **Status** (`/jobs`): ostatnie zlecenia z postępem. Strona odświeża się sama, dopóki coś jest w kolejce.
- **Pliki** (`/files`): wszystkie przetworzone filmy.

Pliki nazywają się `YYYY-MM-DD - Tytuł - Kanał.mp3` i dostają tagi ID3: tytuł, artysta (kanał), data i URL.

Obsługiwane wejście: `watch?v=`, `youtu.be/`, `/shorts/`, `/live/`, `/embed/`, `/playlist?list=` oraz gołe
11-znakowe ID. Link `watch?v=X&list=Y` to pojedynczy film. Linki do kanałów nie są obsługiwane.

Bez autoryzacji: aplikacja jest przeznaczona do sieci lokalnej.

## Uruchomienie (Docker)

```sh
mkdir -p output config
docker compose up -d --build
```

Aplikacja działa pod `http://localhost:5000`. Pliki mp3 trafiają do `./output/<katalog>` (lub do `OUTPUT_DIR`, patrz niżej), a baza
leży zawsze w `./config/app.db` (katalog obok `Dockerfile`, niekonfigurowalny).

Ustawienia dla compose trzymaj w pliku `.env` obok `docker-compose.yml` (wzór: `.env.example`):

```sh
cp .env.example .env
```

- `HOST_PORT` – port na hoście (domyślnie `5000`).
- `OUTPUT_DIR` – folder na hoście na pliki mp3 (domyślnie `./output`).
  Może być ścieżką bezwzględną, np. `/mnt/muzyka/yt2mp3`.
- `UID` / `GID` – użytkownik, jako który działa kontener (domyślnie `1000:1000`). Ustaw na wynik
  `id -u` / `id -g`, żeby pliki na dysku miały właściwego właściciela.

Katalogi `OUTPUT_DIR` i `./config` utwórz przed pierwszym startem. Jeśli utworzy je Docker, będą należały do roota
i kontener nie będzie mógł w nich pisać.

Gunicorn musi mieć **jeden** worker (`-w 1`), bo wątek pobierający żyje w procesie aplikacji.
Kolejka jest w bazie, więc po restarcie kontenera przerwane pozycje wracają do kolejki i są dokończone.

## Aktualizacja yt-dlp

YouTube często się zmienia, więc yt-dlp trzeba co jakiś czas aktualizować. Wersja jest przypięta
w `requirements.txt`:

1. Podbij wersję `yt-dlp[default]==...` w `requirements.txt` (najnowsza: https://pypi.org/project/yt-dlp/).
2. `docker compose build && docker compose up -d`

yt-dlp potrzebuje do YouTube zewnętrznego runtime'u JS (Deno, min. 2.3.0) oraz pakietu `yt-dlp-ejs`.
Pakiet przychodzi z `yt-dlp[default]`, a Deno jest kopiowany do obrazu z `denoland/deno:bin-<wersja>`
(patrz `Dockerfile`). Przy większych aktualizacjach yt-dlp warto sprawdzić https://github.com/yt-dlp/yt-dlp/wiki/EJS.

## Lokalny dev (Windows)

Wymaga Pythona 3.12 oraz `ffmpeg`, `ffprobe` i `deno` w `PATH`
(np. `winget install Gyan.FFmpeg DenoLand.Deno`).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt pytest
flask --app app run
```

Bez ustawionych zmiennych `OUTPUT_ROOT` i `DB_PATH` aplikacja używa `./output` i `./config/app.db`.
Z `--debug` worker startuje tylko w procesie potomnym reloadera, więc nie uruchomi się dwa razy.

Testy:

```powershell
pytest
```

## Konfiguracja (zmienne środowiskowe)

| Zmienna           | Domyślnie (Docker)    | Opis                                            |
|-------------------|-----------------------|-------------------------------------------------|
| `OUTPUT_ROOT`     | `/data/output`        | Katalog główny plików mp3                       |
| `DB_PATH`         | `/data/config/app.db` | Plik bazy SQLite                                |
| `TEMP_DIR`        | `/tmp/yt2mp3`         | Katalog roboczy yt-dlp, czyszczony przy starcie |
| `DEFAULT_QUALITY` | `64`                  | Domyślna jakość w formularzu (kbps)             |
| `DEFAULT_OUT_DIR` | `default`             | Katalog używany, gdy pole ścieżki jest puste    |
| `TZ`              | `Europe/Warsaw`       | Strefa czasowa, w której wyświetlane są godziny |

## Zachowanie

- **Duplikaty** są liczone globalnie po ID filmu. Film, który jest już w bazie, dostaje status „pominięte”,
  nawet jeśli plik zniknął z dysku.
- **Nadpisuj**: film jest pobierany ponownie do wskazanego katalogu, a wpis w bazie jest aktualizowany.
  Stary plik w innym katalogu zostaje na dysku.
- Gdy mp3 już leży na dysku, ale nie ma go w bazie (a „nadpisuj” jest wyłączone), nic nie jest pobierane:
  plik jest tylko rejestrowany w bazie.
- Film, którego nie udało się pobrać, nie trafia do bazy, więc ponowne zgłoszenie spróbuje jeszcze raz.
- Prywatne i usunięte filmy z playlist dostają status „błąd”.
