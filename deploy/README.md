# Wdrażanie weronikarafal.com

Model odpowiada CI/CD `Rafalbanas/banasdev`: sprawdzona paczka ZIP,
ograniczony klucz SSH, przypięty klucz serwera, środowisko `production`
dopuszczające wyłącznie `main`, kolejka wdrożeń i blokada po stronie VPS.

## Pipeline

Każdy push i PR uruchamia walidację HTML, lokalnych plików i kotwic,
składni skryptów oraz testy wdrożeń, błędnych archiwów i rollbacku.
Artefakt jest przechowywany przez 7 dni. Tylko poprawne wykonanie na `main`
może uruchomić wdrożenie. Przed wdrożeniem aktualna wersja musi być przodkiem
wdrażanego commita, co chroni przed nadpisaniem strony starszym workflow.

Paczka zawiera wyłącznie `public/index.html` i `public/revision.txt`.
Odbiornik sprawdza SHA-256, SHA commita, limit 16 MiB i dokładną listę plików.
Nie uruchamia kodu z archiwum. Dodanie nowych lokalnych zasobów wymaga
rozszerzenia `scripts/package.py` oraz listy `FILES` w `deploy/deploy.py`,
przetestowania i zainstalowania nowego odbiornika na serwerze.

## Serwer

- `/var/lib/weronikarafal/releases/`: niezmienne wydania.
- `/var/lib/weronikarafal/current`: atomowo przełączany symlink.
- `/var/lib/weronikarafal/previous`: poprzednie poprawne wydanie.
- `/etc/weronikarafal/deploy.json`: konfiguracja z `deploy.example.json`, root, 600.
- `/usr/local/sbin/weronikarafal-deploy`: `deploy.py`, root, 755.
- `/usr/local/bin/weronikarafal-cd-ssh`: `ssh-command.sh`, root, 755.
- `/etc/nginx/conf.d/weronikarafal-health.conf`: `nginx-loopback.conf`.

Nginx dla obu nazw domeny używa `root /var/lib/weronikarafal/current/public;`.
Listener kontrolny `127.0.0.1:18082` używa tego samego katalogu. Odbiornik
porównuje SHA wersji i sumę HTML przez HTTP; nieudana kontrola przywraca
poprzedni symlink i sprawdza poprzednią wersję. Przed pierwszym wdrożeniem
`current` wskazuje kopię pierwotnej strony z SHA początkowego commita.

Konto `weronikarafal-deploy` ma zablokowane hasło i osobny klucz Actions.
`authorized_keys` dopuszcza tylko wymuszone polecenie:

```text
restrict,command="/usr/local/bin/weronikarafal-cd-ssh" ssh-ed25519 PUBLIC_KEY
```

Reguła `/etc/sudoers.d/weronikarafal-cd` (root, 440):

```text
weronikarafal-deploy ALL=(root) NOPASSWD: /usr/local/sbin/weronikarafal-deploy
```

Klucz obsługuje tylko `status` i `deploy REVISION ARCHIVE_SHA256`.
Klucze i sekrety nie wchodzą do repozytorium ani katalogu publicznego.
Skrypty odbiornika są instalowane osobno przez administratora; wydanie
witryny nie może ich zmienić.

## GitHub

Sekrety repozytorium: `VPS_HOST` (adres origin), `VPS_PORT`,
`VPS_USER=weronikarafal-deploy`, `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS`.
Klucz hosta pochodzi z `/etc/ssh/ssh_host_ed25519_key.pub`, nie z zaufania
do niezweryfikowanego skanu sieci. Środowisko `production` dopuszcza `main`.

## Odzyskiwanie

Normalnie wykonaj `git revert` na `main` i wypchnij zmianę: przejdzie testy
i automatycznie odtworzy wcześniejszą treść. Zachowuje to kolejność commitów.
W awarii administrator może atomowo przełączyć `current` na katalog podany
w `previous`, potem sprawdzić `http://127.0.0.1:18082/revision.txt` i stronę.
Nie usuwaj katalogów wskazywanych przez `current` ani `previous`.

## Walidacja lokalna

```sh
python3 scripts/check_site.py  # wymaga Node.js
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts deploy tests
bash -n deploy/ssh-command.sh
```
