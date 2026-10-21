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
sudo python3 deploy/install.py --apply
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
