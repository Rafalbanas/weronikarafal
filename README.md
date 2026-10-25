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

## Biblioteka mediów (`/media`)

Po zalogowaniu kodem zaproszenia lub kontem pary młodej dostępna jest biblioteka
zdjęć i filmów. Plik jest zapisywany na dysku pod losową, wewnętrzną nazwą,
a metadane (oryginalna nazwa, typ, rozmiar, data i właściciel) trafiają do
SQLite. Domyślnie pliki są prywatne: właściciel widzi własne, a administratorzy
wszystkie. Usuwanie jest weryfikowane po stronie serwera na podstawie sesji,
nigdy na podstawie nazwy pliku przesłanej przez klienta.

Domyślny katalog to `/var/lib/weronikarafal-data/uploads` — obok bazy danych,
poza katalogiem publicznym i wydaniami. Konfiguracja:

| Zmienna | Domyślnie | Znaczenie |
| --- | --- | --- |
| `WEDDING_UPLOADS_DIR` | `<katalog danych>/uploads` | trwały katalog na pliki |
| `WEDDING_MAX_UPLOAD_BYTES` | `33554432` (32 MiB) | limit jednego pliku |
| `WEDDING_MAX_UPLOAD_FILES` | `5` | limit plików w jednym żądaniu |
| `WEDDING_MAX_UPLOADS_PER_USER` | `100` | limit plików na konto |

Dozwolone formaty: JPEG, PNG, GIF, WEBP, MP4, WEBM i MOV. Rozszerzenie, typ MIME
i sygnatura pliku muszą się zgadzać; SVG, HTML i inne formaty są odrzucane.
Zwiększając limit pliku, podnieś też `client_max_body_size` w Nginx oraz
`--timeout` Gunicorna (patrz [deploy/README.md](deploy/README.md)).
Plików z biblioteki nie dodawaj do Git; katalog `uploads/` jest ignorowany.

## Testy

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
