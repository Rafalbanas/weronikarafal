# CI/CD i administracja

## Pierwsza migracja po scaleniu PR

Dotychczas serwer publikował stronę statyczną. Nowa wersja wymaga Flask,
Gunicorn, trwałego katalogu SQLite i reverse proxy Nginx. Sam PR nie zmienia
produkcji. **Nie scalaj i nie oczekuj, że dotychczasowy odbiornik ZIP uruchomi
backend:** odrzuci nową listę plików. Pierwszy job deploy może z tego powodu
zakończyć się błędem, pozostawiając dotychczasową stronę.

Po przeglądzie i scaleniu PR, z czystego checkoutu scalonego `main` na serwerze:

```sh
cd /var/www/weronikarafal
git switch main
git pull --ff-only origin main
sudo python3 -m deploy.install --apply
```

Instalator zakłada istniejące konto SSH CI/CD, certyfikaty domeny i układ
katalogów używany przez tę stronę. Wymaga Python 3 z venv/pip, Nginx i systemd.
Nie uruchamiaj go z niezrecenzowanej gałęzi.

Instalator zapisuje kopie konfiguracji i istniejącej bazy do prywatnego
`/var/backups/weronikarafal/app-migration-*`, tworzy dedykowanego użytkownika,
instaluje przypięte zależności w wersjonowanym venv i tworzy trwały sekret sesji.
Przygotowuje wydanie, uruchamia backend, sprawdza zdrowie i przełącza Nginx.
Błąd przywraca poprzednie konfiguracje i wydanie. Baza gości nie jest kasowana.

Po instalacji ponów nieudany job deploy albo uruchom workflow na `main`.
Pierwsza migracja jest jedynym krokiem wymagającym instalacji jako root.
Zmiana zależności lub schematu danych w przyszłości wymaga osobnej procedury
administracyjnej; odbiornik odrzuci wydanie z innym plikiem zależności.

## Układ serwera

- `/var/lib/weronikarafal/releases/` — wydania, kod root-owned.
- `/var/lib/weronikarafal/current` — aktywne wydanie.
- `/var/lib/weronikarafal/previous` — poprzednie udane wydanie aplikacji.
- `/var/lib/weronikarafal-data/` — prywatna baza i ustawienia, użytkownik
  `weronikarafal-web`, katalog 700, baza/ustawienia 600.
- `/var/lib/weronikarafal-data/uploads/` — pliki biblioteki mediów, ten sam
  użytkownik, katalog 700, pliki 600; poza Nginx, wydaniami i Git.
- `/etc/weronikarafal/web.env` — trwały sekret sesji i ścieżka danych, root 600.
- `/etc/weronikarafal/deploy.json` — stała konfiguracja odbiornika, root 600.
- `/opt/weronikarafal/venv` — symlink do wersji środowiska zależności.
- `weronikarafal-web.service` — Gunicorn jako nieuprzywilejowany użytkownik,
  dostęp wyłącznie przez `127.0.0.1:18083`, zapis tylko w katalogu danych.

Nginx publikuje tylko pliki z `public/assets/` i proxy aplikacji. Szablony,
Python, baza i ustawienia nie mają publicznej ścieżki. Endpoint `/healthz`
jest dostępny lokalnie, publicznie zwraca 404. Strony dynamiczne nie mogą być
cache'owane przez reguły Cloudflare: zachowaj `private, no-store` i nie stosuj
reguł „Cache Everything” do `/login`, `/guest`, `/rsvp` ani `/logout`.

## Dane ceremonii, wesela i kontakty

Przygotuj **poza repozytorium** kopię `deploy/details.example.json` z danymi:

```json
{
  "ceremony": {"name": "nazwa kościoła", "address": "adres publiczny"},
  "venue": {"name": "nazwa sali", "address": "adres tylko dla gości"},
  "contacts": [{"role": "Świadkowa", "name": "imię i nazwisko", "phone": "+48 000 000 000"}],
  "schedule": [{"time": "16:30", "title": "Przyjęcie", "description": "informacja dla gości"}]
}
```

Następnie, jako użytkownik aplikacji:

```sh
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py set-details /prywatna/sciezka/details.json
```

Dostosuj uprawnienia wejściowego pliku tak, aby ten użytkownik mógł go odczytać.
Nie używaj rzeczywistych danych w pliku śledzonym przez Git. Sekcja `ceremony`
jest celowo publiczna; pozostałe sekcje są renderowane wyłącznie po zalogowaniu.

## Zaproszenia i odpowiedzi

Komendy administracyjne wykonuj jako `weronikarafal-web`, z Python venv
oraz `manage.py` z aktywnego wydania:

```sh
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py invite 'Imię i nazwisko' --companion
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py list
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py revoke ID_ZAPROSZENIA
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py rotate ID_ZAPROSZENIA
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py export-rsvp /var/lib/weronikarafal-data/odpowiedzi.csv
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py backup /var/lib/weronikarafal-data/kopia.sqlite3
```

Kod jest wyświetlany tylko podczas dodania lub rotacji. Przekaż go adresatom
prywatnie. Para może mieć jedno wspólne zaproszenie i formularz; `--companion`
pozwala podać osobę towarzyszącą. `revoke` i `rotate` unieważniają sesje.
Eksport zawiera dane prywatne, nie przesyłaj go do Git ani do publicznego katalogu.
Archiwizuj również `details.json` w prywatnej kopii. Przywracanie bazy wykonuj
po zatrzymaniu usługi i z zachowaniem właściciela plików.

## Kolejne wydania

GitHub Actions testuje każdą gałąź i PR: autoryzację, RSVP, sesje, CSRF,
limity, walidację HTML/JS, pakowanie i rollback. Tylko poprawne `main`
wdraża artefakt. Wydanie zawiera zamkniętą listę kodu, szablonów i zasobów;
nie zawiera danych, sekretów ani kodów zaproszeń. Artefakty żyją 7 dni.

Ograniczone konto SSH, osobny klucz, przypięta tożsamość hosta i sekrety
`VPS_HOST`, `VPS_PORT`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS`
pozostają takie jak w poprzednim CI/CD. Produkcja dopuszcza tylko `main`.
Odbiornik sprawdza SHA-256, nazwy, rozmiary, SHA commita i zgodność zależności.
Kod aplikacji nie jest uruchamiany jako root. Stała, root-owned konfiguracja
zezwala wyłącznie na restart `weronikarafal-web.service`.

Po atomowym przełączeniu `current` odbiornik restartuje usługę i porównuje
rewizję technicznego endpointu Nginx z `/healthz` aplikacji oraz sumą szablonu.
Błąd przywraca poprzedni symlink, restartuje poprzednią wersję i ponownie ją
sprawdza. SQLite znajduje się poza wydaniami. Nie usuwaj bieżącego ani
poprzedniego wydania. Normalne cofnięcie zmian rób przez `git revert` i PR.
Aktualizuj zaufane sieci Cloudflare w `nginx-cloudflare-realip.conf` ze źródeł
Cloudflare; nie ufaj nagłówkom IP przychodzącym od dowolnego klienta.


## Panel pary młodej

Panel `/admin` ma osobne konta, niezależne od kodów zaproszeń. Pierwsze konto
utwórz lokalnie (hasło wprowadzane przez ukryty prompt, minimum 16 znaków):

```sh
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py admin LOGIN
```

Można utworzyć osobne konta dla każdej osoby. Każde widzi wszystkie RSVP,
zarządza zaproszeniami i zmienia własne hasło. Kody pokazują się tylko raz;
reset w panelu unieważnia poprzedni kod i sesje gościa, zachowując RSVP.
Przechowujemy wyłącznie hashe scrypt z losową solą, nigdy jawne kody/hasła.

Wydanie panelu rozszerza listę plików o trzy szablony administratora. Przed
pierwszym deployem tego wydania zaktualizuj root-owned odbiornik z przejrzanego
commita (`deploy/deploy.py` → `/usr/local/sbin/weronikarafal-deploy`, tryb 755),
zachowując kopię starego odbiornika. Wykonaj prywatną kopię bazy przed migracją.
Nowe tabele i kolumna `code_id` są dodawane automatycznie, bez usuwania danych.
Stare kody zachowują ważność i otrzymują hash z solą przy poprawnym logowaniu.
Zależności, sekret sesji i konfiguracja Nginx pozostają zgodne z backendem.


## Odzyskiwanie hasła administratora

Na `/admin/login` jest odnośnik do `/admin/recover`. Reset wymaga loginu,
jednorazowego kodu odzyskiwania i nowego hasła (16–256 znaków). Po użyciu
kod jest atomowo zastępowany nowym i wyświetlany tylko raz. Stare hasło oraz
wszystkie sesje konta tracą ważność. Kod można odnowić w sekcji Wasze konto,
potwierdzając obecne hasło. Nie ma resetu na podstawie samego loginu.

Pierwszy kod lub kod awaryjny wydaje administrator serwera:

```sh
sudo -u weronikarafal-web /opt/weronikarafal/venv/bin/python /var/lib/weronikarafal/current/manage.py admin-recovery LOGIN
```

Wydanie kolejnego kodu unieważnia poprzedni. Zachowaj go poza repozytorium.
Kody przechowywane są wyłącznie jako hashe scrypt z losową solą, w nowej
addytywnej tabeli `admin_recovery`. Lokalny reset hasła przez `manage.py admin`
unieważnia także istniejący kod odzyskiwania. Przed wdrożeniem wykonaj kopię bazy.


## Pary i dzieci na zaproszeniu

Formularz administratora obsługuje jedną osobę, parę z dwoma nazwiskami lub
osobę z bezimienną osobą towarzyszącą. W ostatnim wariancie pole drugiej osoby
jest ukrywane i ignorowane na serwerze. Dzieci dodaje się przyciskami +/−;
imiona są opcjonalne, limit to 20 dzieci na zaproszenie. Bez JavaScript działa
numeryczna liczba dzieci, a imiona można później uzupełnić w edycji.

Każda rodzina ma jeden kod i jedno RSVP obejmujące całe zaproszenie. Dane
pary i dzieci można edytować bez zmiany kodu. Rotacja zachowuje skład rodziny
oraz zapisane RSVP. Imiona dzieci są widoczne tylko właścicielom zaproszenia
i administratorom; wspólna lista gości pokazuje tylko dorosłych.

Migracja dodaje kolumny guests.partner_name oraz guests.children (JSON),
z pustymi wartościami dla istniejących zaproszeń. Inicjalizacja WAL i schematu
jest chroniona prywatnym plikiem guests.sqlite3.init.lock, aby równoległy start
workerów nie powodował SQLITE_BUSY. Wdrożenie wymaga kopii bazy, nie wymaga
zmiany zależności ani odbiornika ZIP.


## Biblioteka mediów

Wydanie z biblioteką mediów dodaje szablon `templates/media.html`, tabelę
`uploads` i endpointy `/media`. Tabela powstaje automatycznie jako addytywna
migracja w `wedding/store.py`; istniejące dane pozostają nietknięte. Przed
pierwszym wdrożeniem:

1. Wykonaj prywatną kopię bazy (`manage.py backup`) oraz katalogu
   `/var/lib/weronikarafal-data/` (razem z `details.json`).
2. Zaktualizuj root-owned odbiornik z przejrzanego commita
   (`deploy/deploy.py` → `/usr/local/sbin/weronikarafal-deploy`, tryb 755).
   Nowa wersja odbiornika akceptuje dodatkowy plik `templates/media.html`;
   stara odrzuci wydanie jako „Unexpected archive entries”.
3. Zaktualizuj konfigurację Nginx z `deploy/nginx-site.conf`
   (`client_max_body_size 34m`) i jednostkę systemd z
   `deploy/weronikarafal-web.service` (`--timeout 120`). Bez tego Nginx
   odrzuci większe przesłania (413), a Gunicorn może przerwać wolne
   przesyłanie. Nie zmieniaj innych serwerów wirtualnych ani konfiguracji
   systemowej.
4. Upewnij się, że `/var/lib/weronikarafal-data/uploads/` należy do
   `weronikarafal-web:weronikarafal-web` i ma tryb 700. Katalog powstaje
   automatycznie przy starcie aplikacji; usługa ma już zapis do całego
   `/var/lib/weronikarafal-data`.

Konfiguracja limitów (opcjonalna, w `/etc/weronikarafal/web.env`):

```sh
WEDDING_MAX_UPLOAD_BYTES=33554432   # 32 MiB na plik
WEDDING_MAX_UPLOAD_FILES=5          # plików w jednym żądaniu
WEDDING_MAX_UPLOADS_PER_USER=100    # plików na konto
# WEDDING_UPLOADS_DIR=/var/lib/weronikarafal-data/uploads
```

Jeśli podnosisz `WEDDING_MAX_UPLOAD_BYTES`, podnieś też `client_max_body_size`
w Nginx (do rozmiaru pliku plus ok. 1 MiB narzutu) i pozostaw `--timeout`
wystarczający na wolne łącze. Nie zezwalaj na nieograniczone przesyłanie.

Kopie zapasowe: `manage.py backup` obejmuje tylko SQLite. Pliki kopiuj osobno
(np. `tar` lub `rsync` całego katalogu `uploads/`) i przechowuj razem z bazą.
Przywracanie rób przy zatrzymanej usłudze, zachowując właściciela i tryby.
Nie dodawaj katalogu `uploads/` do repozytorium.
