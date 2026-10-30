# Weronika i Rafał

Strona ślubna z trzema poziomami dostępu:

- **Publicznie:** data, odliczanie, godzina ceremonii i kościół po uzupełnieniu danych.
- **Panel pary młodej (`/admin`):** osobny login i hasło, zarządzanie gośćmi, pełne RSVP i reset kodów.
- **Po zalogowaniu kodem zaproszenia:** własne RSVP, lista zaproszeń ze statusami,
  miejsce przyjęcia, harmonogram oraz kontakt do świadków.

Dieta, nocleg, osoba towarzysząca i uwagi są widoczne tylko autorowi odpowiedzi
oraz organizatorom. Nie ma publicznej rejestracji. Kody, nazwiska gości,
odpowiedzi i rzeczywiste kontakty są przechowywane poza repozytorium.

Aplikacja korzysta z Flask, SQLite i lokalnych zasobów CSS/JS. Nowy kod zaproszenia
zawiera publiczny identyfikator oraz losowy sekret 128-bitowy; w bazie zapisujemy
wyłącznie hash scrypt z losową solą. Kod jest wyświetlany raz. Dostęp
wymaga sesji sprawdzanej przez serwer, a zapisy RSVP mają ochronę CSRF i limity.

## Uruchomienie lokalne

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export WEDDING_DATA_DIR=/tmp/wedding-dev
export WEDDING_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
.venv/bin/python manage.py invite 'Gość testowy'
```

Kod jest wyświetlany raz. Uruchom aplikację przez WSGI z lokalną konfiguracją
zaufanego hosta. Sesyjne cookies wymagają HTTPS również w podglądzie. Nie
uruchamiaj serwera developerskiego jako publicznego serwera produkcyjnego.

### Poprawianie nazwisk bez zmiany kodu

W panelu `/admin`, przy istniejącym zaproszeniu, wybierz „Edytuj dane — kod bez
zmian”, popraw imiona/nazwiska i użyj „Zapisz dane”. Ta operacja zachowuje
dotychczasowy kod zaproszenia i sesje gości. Wygenerowanie nowego kodu jest
osobną operacją — nie służy do poprawiania nazwisk.

## Biblioteka mediów (`/media`)

Po zalogowaniu kodem zaproszenia lub kontem pary młodej dostępna jest biblioteka
zdjęć i filmów. Plik jest zapisywany na dysku pod losową, wewnętrzną nazwą,
a metadane (oryginalna nazwa, typ, rozmiar, data i właściciel) trafiają do
SQLite. Wszyscy zalogowani goście i administratorzy widzą oraz pobierają
wszystkie pliki, także zbiorczo przyciskiem „Pobierz wszystkie (ZIP)”. Gość usuwa wyłącznie własne, a para młoda może usunąć każdy plik.
Usuwanie jest weryfikowane po stronie serwera na podstawie sesji,
nigdy na podstawie nazwy pliku przesłanej przez klienta.

Domyślny katalog to `/var/lib/weronikarafal-data/uploads` — obok bazy danych,
poza katalogiem publicznym i wydaniami. Konfiguracja:

| Zmienna | Domyślnie | Znaczenie |
| --- | --- | --- |
| `WEDDING_UPLOADS_DIR` | `<katalog danych>/uploads` | trwały katalog na pliki |
| `WEDDING_MAX_UPLOAD_BYTES` | `33554432` (32 MiB) | limit pliku i łącznego rozmiaru plików w żądaniu |
| `WEDDING_MAX_UPLOAD_FILES` | `5` | limit plików w jednym żądaniu |
| `WEDDING_MAX_UPLOADS_PER_USER` | `100` | limit plików na konto |

Formaty są rozpoznawane po zawartości przez systemowe `file`/libmagic, zamiast
zamkniętej listy rozszerzeń. Przyjmowane są rozpoznane typy `image/*` i `video/*`,
w tym HEIC/HEIF, AVIF, TIFF, RAW rozpoznawany przez libmagic, AVI i MKV.
Zakres rozpoznawania zależy od wersji systemowej bazy libmagic; nie jest to
obietnica obsługi każdego istniejącego formatu. HTML, archiwa i pliki wykonywalne
są odrzucane niezależnie od nazwy. SVG i formaty bez podglądu są pobierane jako
załącznik `application/octet-stream`; oryginalne bajty i nazwa są zachowane.
Podgląd lub odtwarzanie zależy od formatów i kodeków obsługiwanych przez przeglądarkę.
Wymagana jest komenda `file` (Debian/Ubuntu: `apt-get install file`).
Zwiększając limit pliku, podnieś też `client_max_body_size` w Nginx oraz
`--timeout` Gunicorna (patrz [deploy/README.md](deploy/README.md)).
Plików z biblioteki nie dodawaj do Git; katalog `uploads/` jest ignorowany.

## Testy

Node.js musi być dostępny na `PATH` również dla testów zachowania podglądu zdjęć.
Nie jest wymagany do uruchamiania aplikacji produkcyjnej.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_site.py  # Node.js na PATH
.venv/bin/python -m compileall -q app.py manage.py wedding scripts deploy tests
bash -n deploy/ssh-command.sh
```

## CI/CD i pierwsza migracja

GitHub Actions testuje push i PR. Po udanych testach zmiany na `main` wdrażają
sprawdzoną paczkę. Instalacja serwera aplikacji wymaga **jednorazowej migracji**
z opisanej wcześniej wersji statycznej; nie następuje przez samo wysłanie PR.

Instrukcje: [deploy/README.md](deploy/README.md).
Ochrona dostępu i granice prywatności: [docs/security.md](docs/security.md).

## Język

Przełącznik PL / EN w nagłówku tłumaczy publiczną stronę, strefę gości,
panel pary młodej i komunikaty formularzy. Wybór jest zapamiętywany w osobnym
bezpiecznym cookie przez rok, także po wylogowaniu. Domyślny język to polski;
link `/?lang=en` otwiera wersję angielską. Treści wpisane przez gości oraz dane
wydarzenia zachowują oryginalną treść.

## Wygląd i prywatne strony dnia

Przycisk „Ciemny motyw” w nagłówku pozwala przełączać jasny i ciemny wygląd.
Wybór jest zapamiętywany lokalnie w przeglądarce (`wedding-theme` w
`localStorage`), bez danych konta ani zaproszenia. Jeśli zapis ustawień jest
zablokowany, przełącznik nadal działa na bieżącej stronie. Bez JavaScript
pozostaje jasny wygląd i pełna obsługa zwykłych formularzy oraz nawigacji.

Po zalogowaniu kodem zaproszenia lub kontem pary młodej dostępne są:
- `/schedule` — osobna rozpiska godzinowa. Dopóki `schedule` w prywatnym
  `details.json` jest puste, wyświetla komunikat „pojawi się wkrótce”. Później
  można uzupełnić istniejącą konfigurację przez `manage.py set-details`.
- `/tables` — osobna strona rozmieszczenia stołów, na razie z komunikatem
  o późniejszym uzupełnieniu. Nie tworzy fikcyjnych miejsc ani przypisań gości;
  edytor i właściwy plan stołów będą osobnym etapem.

Obie strony wymagają aktywnej sesji na serwerze, mają `noindex` i `no-store`.
Korzystają z istniejącego szablonu strefy gości, więc nie zmieniają listy
plików paczki ani nie wymagają aktualizacji odbiornika wdrożeń.

## Kalendarz (`/ceremony.ics`)

Przycisk „Dodaj do kalendarza” w karcie ceremonii pobiera publiczny wpis ICS.
Zawiera wyłącznie `ceremony.name` i `ceremony.address` z danych publicznych
(puste pola nie generują `LOCATION`); miejsce przyjęcia, kontakty, harmonogram
oraz goście nigdy się w nim nie pojawiają, także po zalogowaniu. `UID` i `DTSTART` (`20270827T120000Z`, czyli 14:00 Europe/Warsaw),
oraz stałe `DTEND` (`20270827T130000Z`, czyli 15:00 Europe/Warsaw —
orientacyjna, godzinowa rezerwacja kalendarza, nie gwarantowany koniec
mszy) są stałe; `DTSTAMP` to bieżący czas UTC. Nie występuje `DURATION`. Wartości tekstowe są escapowane, a linie
zawijane do najwyżej 75 oktetów UTF-8 bez dzielenia sekwencji. Typ
zawartości to `text/calendar; charset=utf-8` ze stałą, czysto ASCII nazwą
załącznika. Sam endpoint ma nagłówek noindex; polityka indeksowania strony
głównej nie uległa zmianie.

## Przeglądanie biblioteki

Formularz filtrów działa również bez JavaScript. Parametry `/media`:
`kind=all|image|video`, `owner=all|mine`, `page=N` (domyślnie `all`, `all`, `1`).
Widok pokazuje do 24 plików na stronę, z liczbą wszystkich dopasowań.
Filtrowanie, zliczanie i stronicowanie odbywają się w SQL, w kolejności
od najnowszych, z ID jako rozstrzygnięciem przy tej samej dacie. Za wysoki
numer strony jest ograniczany do ostatniej; błędne i powielone parametry
filtrów oraz niepoprawny numer strony zwracają 400.

„Tylko przeze mnie” korzysta z tożsamości zalogowanego gościa lub administratora.
Nie zmienia uprawnień: gość może usuwać wyłącznie własne pliki, administrator
wszystkie. ZIP zawsze zawiera cały album, niezależnie od aktywnych filtrów
i wyświetlanej strony. Interfejs dostępny jest w PL i EN.

Podgląd zdjęć pozwala przechodzić między zdjęciami na bieżącej stronie
biblioteki przyciskami lub strzałkami klawiatury. Licznik wskazuje pozycję
wśród tych zdjęć; filmy i formaty bez podglądu są pomijane. Po ostatnim zdjęciu
nawigacja wraca do pierwszego. Escape, przycisk zamknięcia lub kliknięcie tła
zamyka podgląd i przywraca fokus do zdjęcia, z którego go otwarto.
Pobieranie oryginałów pozostaje dostępne bez JavaScript.
