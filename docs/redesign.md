# Botanical editorial — publiczna strona zaproszenia

## Zakres i kierunek

Zamiast neonowego, geometrycznego plakatu: ciepły papier / atramentowa zieleń,
szeryfowy tytuł, łukowy plakat, rysunek roślinny SVG, charakterystyczny monogram W/R.
Data identyfikacji: **27 · 08 · 27**. Nie zmienia to pełnego roku w `<time>`,
SEO, opisach ceremonii, ICS ani celu odliczania:
`2027-08-27T14:00:00+02:00` (Europe/Warsaw).

Nie zmieniono uwierzytelniania, RSVP, mediów, uprawnień, SQLite, CSRF, URL,
listy plików wydania ani CI/CD. Nie jest wymagana migracja lub nowa zależność
produkcyjna. Nie wykonano wdrożenia, merge ani push.

## Interakcje i dostępność

- `star-secret`: istniejąca szczęśliwa gwiazda zachowuje wiadomość, dodaje
  kota wychylającego się zza plakatu, mrugnięcie, ruch ogona i żart PL/EN.
- `heart-secret`: zachowany tekst o parach; dwie sylwetki zbliżają się,
  ogony rysują serce, dopisek PL/EN o wspólnym parapecie.
- Natywne przyciski obsługują Enter/Spację, `aria-controls`, `aria-expanded`.
  Nie przechwytują skrótów, nie odtwarzają dźwięku i nie zapisują danych.
  Ponowne otwarcie odtwarza krótką animację. Sceny mają absolutne/fiksowane
  miejsce w układzie; otwarcie nie przesuwa kolejnych elementów.
- Bez JS przyciski i sceny są ukryte przez HTML `hidden`; formularze, linki,
  data, ceremonia i natywne FAQ pozostają użyteczne.
- `prefers-reduced-motion` wyłącza animacje i transformacje hover.
  Efekt plakatu reaguje tylko na precyzyjny wskaźnik z hover.
- Reveal nie stosuje początkowego ukrywania sekcji. Observer obsługuje tylko
  sekcje początkowo poniżej ekranu i odłącza je po pierwszym wejściu.
- Odliczanie ma `role="timer"`, `aria-live="off"`, cyfry tabularne; aktualizacje
  są wstrzymywane w ukrytej karcie i synchronizowane po powrocie.
- Przełącznik motywu ma zarezerwowane miejsce również przed uruchomieniem JS;
  jego pojawienie się nie zmienia wysokości mobilnego nagłówka.

## Audyt SEO i prywatność

Wcześniej homepage miał title i description, ale nie miał canonical, linków
hreflang w head ani Open Graph. Dodano wyłącznie na homepage:

- stabilny canonical HTTPS dla faktycznie renderowanego języka (`?lang=pl/en`),
  niezależny od Host i dodatkowych parametrów żądania;
- wzajemne alternate hreflang PL/EN oraz x-default wskazujący jawnie PL;
- OG website, title, description, url, locale i Twitter summary;
- pełne 2027 w tytule/opisie i brak prywatnych danych w metadanych.

Istniejące robots.txt dopuszcza homepage i wyklucza prywatne ścieżki.
Pozostawiono noindex/noarchive/no-store prywatnych widoków i błędów, a także
restrykcyjne CSP. Nie dodano publicznej sitemap: jedynym indeksowanym widokiem
jest homepage w dwóch językach, powiązanych hreflang. Nie dodano Event JSON-LD:
to prywatne zaproszenie, nie publiczne wydarzenie z ofertą biletów. Nie tworzono
fikcyjnego miejsca, obrazka OG ani danych organizatora. Nie opublikowano
przyjęcia, kontaktów, gości, RSVP, mediów ani panelu.

## Wydajność i weryfikacja

Bez fontów sieciowych, obrazów rastrowych i bibliotek animacyjnych. SVG inline
nie generują dodatkowych żądań. CSS animuje opacity/transform, cache-busting
zasobów pozostaje oparty na treści. Mapa nadal korzysta z istniejącego lazy iframe.
Świadomie zachowano zabezpieczenie no-store aplikacji zamiast osłabiać je dla cache.

Standardowe sprawdzenia:

```sh
python -m unittest discover -s tests -v
python scripts/check_site.py
python -m compileall -q app.py manage.py wedding scripts deploy tests
bash -n deploy/ssh-command.sh
git diff --check
```

Opcjonalnie, z Flask i Playwright/Chromium w lokalnym środowisku testowym
(nie dodawać ich do zależności serwera):

```sh
python scripts/check_editorial_browser.py --axe-path /ścieżka/do/axe.min.js
```

Skrypt renderuje syntetyczne dane bez produkcyjnej bazy, stosuje CSP aplikacji,
blokuje pobieranie mapy i porównuje HEAD (przed) z roboczymi zmianami (po).
Sprawdza PL/EN, dark/light, szerokości 320, 360, 390, 430, 600, 768, 1024,
1440 px, klawiaturę, powtórzenia scen, brak przesuwania stopki po otwarciu,
brak JS i reduced motion. Zapisuje desktop/mobile PNG i JSON poza repozytorium.
Opcjonalny lokalny axe sprawdza reguły WCAG A/AA; nie zastępuje ręcznego audytu
czytnikiem ekranu. Metryki LCP/CLS dotyczą lokalnego, nietrottlowanego renderu
z przechwyconą siecią — **nie dowodzą spełnienia Core Web Vitals na produkcji**.
INP i 75. percentyl rzeczywistych użytkowników wymagają osobnych pomiarów RUM/CrUX.
Safari, Firefox, fizyczne telefony i zachowanie czytników ekranu wymagają weryfikacji.

### Wynik lokalny (13 listopada 2026)

- Pełny zestaw: **158 testów, OK** (log poza repo:
  `/tmp/opencode/wedding-editorial-tests-final.log`).
- Chromium: 32 warianty po zmianach + 2 zrzuty bazowe, brak poziomego overflow,
  klawiatura, ponowne otwarcie, brak JS i reduced motion — OK.
- Axe: 8 kontroli homepage (320/1440, PL/EN, dark/light), **0 naruszeń**
  wybranych reguł A/AA; pozostały przypadki `incomplete` do oceny ręcznej
  (`aria-prohibited-attr`, `color-contrast`). Nie jest to certyfikacja WCAG.
- Dodatkowy smoke test: `/login`, `/guest`, `/media`, `/schedule`, `/tables`,
  `/admin` z syntetycznymi kontami, PL/EN przy 320 px — bez overflow.
- Ostatnia próba: lokalny LCP **120–2764 ms**, maksymalny CLS **0** po zarezerwowaniu
  miejsca na przełącznik (wcześniej mobilny CLS dochodził do 0,184).
  To nietrottlowane próby z przechwyconą siecią na obciążonym hoście, nie RUM.
  Cel LCP nie został potwierdzony; INP i produkcyjnego p75 nie zmierzono.
- Renderowanie, składnia JS/Python/Bash, pakowanie i `git diff --check` — OK.

Zrzuty przed/po i obie otwarte sceny oraz szczegółowy JSON:
`/tmp/opencode/wedding-editorial-audit/`. Mapa jest celowo pusta w audycie,
bo żądania do Google są przechwytywane. Pliki audytu nie są częścią wydania.

Dogrywka: działający podgląd HTTPS, porównania 1440/390 px, wąskie korekty
czytelności i osobne powtórzenia LCP opisuje [visual-review.md](visual-review.md).
