# Bezpieczeństwo i prywatność

## Stan obecny

Strona i repozytorium GitHub są publiczne. Repozytorium może być klonowane,
więc późniejsze usunięcie danych nie usuwa istniejących kopii ani historii.
Daty, lokalizacje i dane kontaktowe
umieszczone w HTML są dostępne każdemu odwiedzającemu.

RSVP nie ma jeszcze skonfigurowanego zapisu. Poprzedni kod zawierał
przykładowy endpoint Formspree i symulował powodzenie. Formularz pozostaje
wyłączony do czasu uruchomienia i przetestowania chronionej obsługi po
stronie serwera. Wyłączenie kontrolek w HTML nie jest kontrolą dostępu.

Meta `noindex` prosi wyszukiwarki o nieindeksowanie strony; nie ukrywa
treści i nie usuwa natychmiast wcześniej zindeksowanych informacji.

## Decyzja o dostępie

Do uzgodnienia z właścicielem pozostaje zakres prywatności:

1. Cała strona dostępna tylko zaproszonym, po uwierzytelnieniu.
2. Publiczna strona i RSVP wymagające indywidualnego kodu zaproszenia.
3. Publiczna strona i RSVP z kontrolą antyspamową.

Udostępnienie wspólnego hasła pozwala każdemu jego posiadaczowi przekazać
dostęp dalej. Indywidualne zaproszenia można odwoływać osobno. CAPTCHA
utrudnia automatyzację, ale nie weryfikuje, czy ktoś jest zaproszony.

## Wymagania dla uruchomienia RSVP

- Weryfikacja zaproszenia lub antyspamowa po stronie serwera przed zapisem.
- W przypadku Turnstile: serwerowa weryfikacja tokena przez Siteverify,
  sprawdzenie hosta i akcji oraz odrzucanie tokenów wygasłych lub użytych.
- Limity prób i rozmiaru żądania, walidacja typów, długości i dozwolonych
  wartości oraz kontrola pochodzenia żądań. Limit w HTML nie wystarcza.
- Brak wielokrotnego dopisywania tej samej odpowiedzi: aktualizacja RSVP
  przypisanego do zaproszenia albo inna jawna obsługa duplikatów.
- Odpowiedzi i sekrety poza Git, logami i katalogiem publicznym Nginx.
- Dostęp do listy odpowiedzi wyłącznie dla uprawnionych organizatorów.
- Sukces w interfejsie dopiero po potwierdzeniu trwałego zapisu; błędy
  serwera nie mogą pokazywać podziękowania za zapis.
- Testy bezpośrednich żądań z pominięciem JavaScript, błędnych zaproszeń,
  powtórzeń, limitów i niedostępności usług weryfikujących.

Dokumentacja:
[Cloudflare: walidacja Turnstile na serwerze](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/),
[OWASP: zapobieganie przeciążeniom](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html).

## Praca nad zmianami

Zmiany bezpieczeństwa powstają na gałęzi `security/rsvp-protection` i w PR.
Push do tej gałęzi i PR uruchamiają testy bez wdrażania na produkcję.
Automatyczne wdrożenie następuje po scaleniu do `main`.

Gałąź `main` wymaga PR i poprawnego testu `test` z GitHub Actions dla
aktualnej podstawy gałęzi. Ochrona obejmuje administratorów; wymuszone
pushe i usuwanie gałęzi są wyłączone. Scalenie nie wymaga drugiego
recenzenta, aby właściciel mógł pracować samodzielnie.
