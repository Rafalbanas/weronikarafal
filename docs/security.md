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
skryptów i stylów, blokadę ramek oraz noindex. Działanie formularza nie wymaga
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
