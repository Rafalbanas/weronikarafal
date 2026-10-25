# Dostęp i prywatność

## Trzy poziomy

Publiczna strona zawiera wyłącznie datę, godzinę, odliczanie i informacje
ceremonii z sekcji `ceremony` prywatnego pliku ustawień. Widok `/guest` jest
renderowany na serwerze dopiero po uwierzytelnieniu. Lista gości, kontakty
i adres wesela nie są dołączane do publicznego HTML, CSS ani JavaScript.

Kod zaproszenia identyfikuje osobę lub parę. Jest generowany przez organizatora
z losowych 24 bajtów: 8 bajtów publicznego identyfikatora i 16 bajtów sekretu
(128 bitów), nie z nazwiska ani numeru telefonu. Serwer przechowuje identyfikator
i hash scrypt z losową solą (Werkzeug), bez odwracalnej kopii kodu. Stare kody
SHA-256 są akceptowane i przy poprawnym logowaniu otrzymują hash scrypt; rotacja
zastępuje je nowym formatem. Kod pozostaje wielokrotnego użytku do czasu
odwołania lub rotacji. Osoba mająca kod może go udostępnić — to sekret, który
należy przekazywać tylko adresatom zaproszenia. Publiczna rejestracja nie istnieje.

Zalogowani goście widzą nazwę zaproszenia i status obecności innych zaproszeń.
Nie widzą cudzych diet, noclegów, uwag, nazwiska osoby towarzyszącej ani kodów.
Własne RSVP jest przypisywane z sesji na serwerze; klient nie wskazuje ID gościa.
Ponowny zapis aktualizuje jedną odpowiedź zamiast tworzyć duplikaty.

## Sesje i żądania

Sesja ma losowy identyfikator przechowywany w podpisanym cookie; w bazie
przechowywany jest jego skrót. Cookie `__Host-wedding` ma `Secure`, `HttpOnly`,
`SameSite=Lax`, ścieżkę `/` i nie ma atrybutu Domain. Sesja wygasa po 8 godzinach.
Wylogowanie usuwa sesję z bazy. Odwołanie lub rotacja zaproszenia unieważniają
jego sesje; każda odsłona panelu ponownie sprawdza uprawnienia i aktywność konta.

Flask-WTF weryfikuje CSRF dla wszystkich POST, także logowania i wylogowania.
Sprawdzany jest również Origin, gdy przeglądarka go podaje. HTTPS i zaufany Host
są wymagane w produkcji. Tylko Nginx na loopback może przekazywać zaufane nagłówki
proxy; nadpisuje X-Forwarded-For i X-Forwarded-Proto. CF-Connecting-IP jest
honorowany wyłącznie od aktualnie zaufanych sieci Cloudflare.

Limity zapisane w SQLite działają wspólnie dla procesów WSGI: 12 nieudanych prób logowania
na IP w 15 minut, 1200 globalnie na godzinę, 10 aktualizacji RSVP na zaproszenie
na minutę i 60 na IP na minutę. Reset cookie nie resetuje limitu IP. IP jest
przechowywane jako HMAC, nie jawnie. Limity ograniczają nadużycia; warstwa
Cloudflare nadal odpowiada za ochronę przed dużym ruchem sieciowym. Baza sama
usuwa wygasłe kubełki limitów i wygasłe sesje przy logowaniu.

Wszystkie odpowiedzi aplikacji mają `private, no-store`, CSP bez zewnętrznych
skryptów i stylów oraz blokadę ramek. Publiczna strona ceremonii może być
indeksowana; pozostałe strony i błędy mają nagłówek noindex, a robots.txt
wyklucza ścieżki logowania, gości i administracji. Działanie formularza nie wymaga
JavaScript. Błędy zapisu nigdy nie są przedstawiane jako sukces. Teksty gości
są escapowane przez Jinja. Backend sprawdza wartości, długości, duplikaty pól
oraz uprawnienia do osoby towarzyszącej. Maksymalne żądanie ma 16 KiB.

## Dane i administracja

Baza, plik `details.json`, pliki SQLite WAL/SHM oraz kopie zapasowe znajdują się
poza katalogiem Nginx, wydaniami i Git. Użytkownik aplikacji ma prawo zapisu
wyłącznie do prywatnego katalogu danych. Aktualizacje aplikacji nie kasują bazy.
Sekret podpisujący sesje pochodzi z pliku systemowego i nie zmienia się przy
kolejnych wdrożeniach. Należy tworzyć prywatne kopie bazy i ustawień oraz ustalić
z organizatorami termin usunięcia odpowiedzi po wydarzeniu.

Organizator korzysta z `/admin`: osobne logowanie hasłem, serwerowe sesje
i autoryzacja administratora na każdym odczycie i zapisie. Gość nie ma dostępu
do panelu nawet z poprawnym kodem. Hasła mają hash scrypt z losową solą;
pierwsze konto tworzy administrator serwera poleceniem `manage.py admin LOGIN`,
bez publicznej rejestracji. Hasło można zmienić w panelu (minimum 16 znaków),
co unieważnia wszystkie sesje danego konta. Logowanie ma limit 5 prób na IP
w 15 minut i 100 globalnie. Panel pokazuje pełne RSVP i umożliwia dodawanie,
edytowanie, odwoływanie oraz resetowanie zaproszeń. Nowy kod jest zwracany
wyłącznie w odpowiedzi na autoryzowany POST, raz, bez zapisu w cookie, logach
ani bazie. Zwykły widok panelu nie zawiera kodów. Reset unieważnia poprzedni kod
i sesje gościa, zachowując RSVP. Eksport odpowiedzi pozostaje lokalny. Eksport zabezpiecza komórki przed formułami arkuszy.
Nie dodawaj rzeczywistych danych ani wygenerowanych kodów do repozytorium,
komentarzy PR, workflow i zrzutów z testów. Repozytorium jest publiczne; zmiana
nazwiska w nowym commicie nie usuwa go ze starej historii lub istniejących kopii.

Nazwy i kontakty w poprzedniej wersji strony były oznaczone jako przykładowe.
Nowa wersja nie traktuje ich jako prawdziwych danych i wymaga uzupełnienia ustawień.

## Proces i weryfikacja

Zmiany powstają w PR. `main` wymaga PR i poprawnego testu `test`, także od
administratora. Gałąź funkcjonalna nie wdraża się na produkcję. Pierwsza migracja
na backend jest osobnym, jawnym krokiem opisanym w instrukcji wdrożenia.

Testy sprawdzają anonimowy dostęp, brak danych w publicznym widoku, własność
RSVP, izolację cudzych odpowiedzi, CSRF, limity, uprawnienia do osoby
towarzyszącej, wygasanie i odwoływanie sesji, XSS, błędny Host oraz rollback.

Źródła:
[Flask — web security](https://flask.palletsprojects.com/en/stable/web-security/),
[Flask-WTF — CSRF](https://flask-wtf.readthedocs.io/en/1.2.x/csrf/),
[OWASP — ograniczanie nadużyć](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html).


## Odzyskiwanie konta pary młodej

Reset hasła wymaga osobnego, losowego 128-bitowego kodu odzyskiwania.
Przechowujemy wyłącznie hash scrypt z losową solą, bez jawnego kodu w bazie,
sesji lub URL. Kod jest przekazywany w POST chronionym przez CSRF i Origin;
endpoint ma limity 5 prób na IP i 100 globalnie w 15 minut. Poprawny reset
wymaga dwukrotnego podania hasła o długości 16–256 znaków, unieważnia wszystkie
sesje konta oraz poprzedni kod. Atomowe compare-and-swap uniemożliwia dwukrotne
użycie kodu przy równoległych żądaniach. Odpowiedź wyświetla nowy kod raz,
z nagłówkami no-store i bez umieszczania go w cookie. Po udanym resecie usuwamy
blokadę nieudanych logowań dla bieżącego IP, aby właściciel mógł użyć nowego hasła.
Generowanie kodu w zalogowanym panelu wymaga ponownego podania obecnego hasła.
Hasła pozostają wrażliwe na wielkość liter; podgląd pola zmienia jedynie jego
lokalny typ i nie zapisuje wartości.


## Biblioteka mediów

`/media` jest dostępne wyłącznie po zalogowaniu — kodem zaproszenia albo kontem
administratora. Gość widzi i usuwa tylko własne pliki; administrator widzi
i usuwa wszystkie. Właściciel jest brany z sesji serwerowej (identyfikator
zaproszenia lub login konta administratora), a nie z danych formularza. Każde
żądanie pobrania i usunięcia sprawdza uprawnienie do konkretnego rekordu, więc
zmiana identyfikatora w adresie nie daje dostępu do cudzego pliku (ochrona IDOR).

Pliki są zapisywane w prywatnym katalogu poza katalogiem publicznym pod nazwą
złożoną z 128 losowych bitów, z uprawnieniami `0600`. Oryginalna nazwa jest
wyłącznie metadanymi i jest escapowana w HTML. Ścieżka pliku nigdy nie powstaje
z nazwy przesłanej przez klienta, dlatego próby typu `../` nie mogą wyjść poza
katalog danych. Nazwy zawierające separatory ścieżek są odrzucane.

Serwer przyjmuje wyłącznie jawną listę formatów (JPEG, PNG, GIF, WEBP, MP4,
WEBM, MOV). Zgłoszony typ MIME musi zgadzać się z rozszerzeniem, a pierwsze
bajty pliku muszą odpowiadać sygnaturze formatu. SVG, HTML i inne formaty są
odrzucane, aby nie renderować niezaufanej treści jako aktywnej. Pliki są
przesyłane strumieniowo do pliku tymczasowego; nie trafiają w całości do pamięci.
Nieudane lub odrzucone przesłania są usuwane, a rekord w bazie powstaje dopiero
po zapisaniu pliku.

Endpoint przesłania ma podniesiony limit rozmiaru żądania tylko dla tej trasy;
pozostałe formularze zachowują limit 16 KiB. Obowiązują limity liczby plików
w żądaniu, liczby plików na konto, rozmiaru pojedynczego pliku oraz limity
częstotliwości. Usuwanie i przesyłanie wymagają CSRF i tego samego Origin.
Odpowiedzi z plikami mają `Cache-Control: private, no-store`, `nosniff`
i `Content-Disposition: inline` bez nazwy pochodzącej od klienta. Obsługiwane są
zakresy bajtów (`Range`), aby bezpiecznie odtwarzać filmy. Pliki nie są
publicznie dostępne pod zgadywalnym adresem — wymagają aktywnej sesji.

Kopie zapasowe muszą obejmować jednocześnie bazę SQLite i katalog `uploads/`;
przywracanie tylko jednej z tych części pozostawi osierocone rekordy lub pliki.
Limit rozmiaru w aplikacji trzeba zsynchronizować z `client_max_body_size`
w Nginx i limitem czasu pracy Gunicorna.
