# Storage i kopia na stacjonarkę

Konfiguracja administracyjna, instalowana ręcznie jako root. Zwykły deploy strony
nie instaluje tych plików. Nie zawierają kluczy SSH, danych gości ani kopii bazy.

## Storage

Docelowy katalog: `/storage/weronikarafal/uploads`. Baza i `details.json` pozostają
w `/var/lib/weronikarafal-data`. `/storage` musi być osobnym, zapisywalnym mountem.

1. Sprawdź `mountpoint /storage` i `df -h /storage`.
2. Utwórz `/storage/weronikarafal` i podkatalog `uploads`, właściciel
   `weronikarafal-web:weronikarafal-web`, tryb 700.
3. Zatrzymaj `weronikarafal-web`; skopiuj stare pliki przez
   `rsync -a /var/lib/weronikarafal-data/uploads/ /storage/weronikarafal/uploads/`.
4. Sprawdź zgodność przez `rsync -acni` z tymi samymi ścieżkami.
5. Ustaw w `/etc/weronikarafal/web.env`:
   `WEDDING_UPLOADS_DIR=/storage/weronikarafal/uploads`.
6. Zainstaluj `storage.conf` jako
   `/etc/systemd/system/weronikarafal-web.service.d/storage.conf`.
7. Wykonaj `systemctl daemon-reload`, uruchom aplikację i sprawdź lokalny
   `http://127.0.0.1:18083/healthz` oraz upload/pobieranie po zalogowaniu.

Drop-in dodaje zapis do katalogu mimo `ProtectSystem=strict` i blokuje start bez
zamontowanego storage. Nie usuwa starego katalogu. Rollback: zatrzymaj aplikację,
skopiuj również nowe pliki z powrotem, przywróć poprzedni env i usuń drop-in,
przeładuj systemd, uruchom aplikację. Nie cofaj ścieżki bez skopiowania nowych plików.

## Kopia SSH

Wymagania: Python 3 i rsync na obu maszynach, SSH z kluczem bez interakcji z konta
root serwera. Zweryfikuj klucz hosta i połączenie `ssh -o BatchMode=yes stacjonarka`.
Alias i klucze pozostają w prywatnej konfiguracji SSH, poza Git.

```sh
install -m 700 deploy/backup/backup.py /usr/local/sbin/weronikarafal-backup-stacjonarka
install -m 600 deploy/backup/backup.env.example /etc/weronikarafal/backup.env
# W backup.env ustaw rzeczywisty login i absolutną ścieżkę docelową.
install -m 644 deploy/backup/weronikarafal-backup.service /etc/systemd/system/
install -m 644 deploy/backup/weronikarafal-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start weronikarafal-backup.service
systemctl enable --now weronikarafal-backup.timer
```

Skrypt tworzy spójną kopię SQLite przez backup API, sprawdza `quick_check`,
kopiuje zdjęcia i filmy wskazane przez tę kopię, a następnie publikuje bazę,
ustawienia i znacznik czasu. Nie przesyła plików `.part`. Brak pliku wymaganego
przez bazę powoduje błąd, zamiast publikacji niepełnej kopii.

Układ na stacjonarce:

- `uploads/<id>`: oryginalne zdjęcia i filmy, bez propagowania usunięć;
- `database/RRRR-MM-DD/GG.sqlite3`: ostatnia udana wersja z danej godziny UTC;
- obok: `GG-details.json` (jeśli istnieje) i `GG-status.json`.

Rsync przesyła nowe media przyrostowo, z limitem 5120 KiB/s i prywatnym katalogiem
na częściowe transfery. Metadane publikuje przez `--delay-updates`. Katalogi mają
tryb 700, pliki 600. Konto docelowe może je odczytać. Snapshot bazy zawiera również
prywatne dane kont i sesji; nie udostępniaj katalogu backupów przez WWW.

Timer uruchamia kolejną kopię minutę po zakończeniu poprzedniej. Blokada zapobiega
nakładaniu przebiegów; awaria SSH jest ponawiana przy następnym uruchomieniu.
Nie ma automatycznego czyszczenia historii ani powiadomień o awarii: monitoruj
wolne miejsce i czas ostatniego sukcesu. Limit czasu przebiegu to 55 minut;
wyjątkowo duży pierwszy transfer może wymagać podniesienia limitów.

```sh
systemctl list-timers weronikarafal-backup.timer
systemctl show weronikarafal-backup.service -p Result -p ExecMainStatus
journalctl -u weronikarafal-backup.service -n 30 --no-pager
```

Przywracanie: zatrzymaj aplikację, zachowaj kopię jej obecnych danych, wybierz
snapshot bazy i odpowiadające ustawienia, sprawdź `PRAGMA integrity_check`,
skopiuj media wskazane w tabeli `uploads`, przywróć właściciela i tryby. Usunięcie
zdjęcia z albumu nie usuwa go z archiwum, ale najnowsza baza już go nie pokazuje;
do odzyskania historycznego albumu użyj odpowiedniej starszej bazy.
