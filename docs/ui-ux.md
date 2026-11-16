# Nowoczesne zaproszenie, prostsza droga do RSVP

Wyniki późniejszego, rozszerzonego przeglądu i poprawki:
[audyt przed publikacją](audit.md). Poniższy zapis wyników dotyczy pierwszego
etapu redesignu.

## Inspiracje, nie kopia

Przejrzane materiały:

- [Riley & Grey — wedding website examples](https://www.rileygrey.com/wedding-website-examples):
  duża typografia, oszczędna kompozycja i dobrze widoczny przycisk RSVP.
- [Joy — wedding websites](https://withjoy.com/wedding-website):
  nacisk na mobilność i praktyczne informacje w jednym miejscu.
- [Joy — online RSVP](https://withjoy.com/online-rsvp):
  prosta ścieżka odpowiedzi, niezależna od dekoracyjnej części zaproszenia.

Nie pobierano cudzych zdjęć, ilustracji, fontów ani kodu. Zachowano autorski
monogram, lokalne SVG, szeryfową typografię i dwa kocie detale. Inspiracja
dotyczy hierarchii informacji i wzorców użyteczności, nie odtwarzania szablonów.

## Co się zmienia

### Najważniejsza akcja od razu

Główny przycisk na pierwszym ekranie prowadzi anonimowego gościa do logowania
kodem. Zalogowany gość trafia bezpośrednio do swojego RSVP, a administrator
do panelu — nie musi ponownie szukać właściwego wejścia. Linki do ceremonii
i pytań pozostają obok, jako spokojniejsza nawigacja pomocnicza.

Data ślubu, godzina ceremonii ze strefą czasową i termin odpowiedzi mają
oddzielny, semantyczny blok `<dl>`. Pozwala to szybko przeskanować stronę
bez czytania całego zaproszenia. Data ceremonii pozostaje **27 sierpnia 2027,
14:00 Europe/Warsaw**; termin RSVP: **1 lipca 2027**.

### Spójny wygląd, także po zalogowaniu

- Szampańska karta daty, spokojny ciemny atrament i ciepły jasny wariant.
- Większy tekst, wyraźniejsza hierarchia i mniej agresywna rotacja plakatu.
- Spójne zaokrąglenia, czytelniejsze kroki, FAQ i karta strefy gości.
- Formularze, przyciski, komunikaty i karty albumu korzystają z tej samej
  palety. Pola mają tekst 16 px, co ogranicza automatyczne powiększanie
  formularzy na telefonach.
- Nagłówek może zawijać nawigację. Nie dodano wymagającego JavaScript menu
  mobilnego, które odcinałoby dostęp do funkcji przy awarii skryptu.
- Na telefonie przełącznik motywu ma kompaktowy symbol z zachowaną nazwą
  dla czytników ekranu. Nie nachodzi na nazwę pary; miejsce jest zarezerwowane
  również przed uruchomieniem JavaScript.

### Mniej tarcia przy logowaniu

Pole kodu zaproszenia ma przycisk „Pokaż kod / Ukryj kod” z istniejącego,
lokalnego mechanizmu podglądu hasła. Kontrolka ma `type="button"`,
`aria-controls` i `aria-pressed`. Nie wysyła formularza, nie zmienia kodu
ani nie zapisuje jego wartości. Bez JavaScript pozostaje ukryta, a logowanie działa.

## Granice zmian

Nie zmieniono modelu uprawnień, schematu bazy, CSRF, endpointów, limitów,
zawartości kalendarza, listy plików wydania ani procedury wdrożenia.
Prywatne informacje nie trafiają do publicznego podsumowania lub metadanych.
Nie dodano analityki, reklam, fontów sieciowych ani bibliotek interfejsu.
Mapa zachowuje istniejący zewnętrzny iframe ładowany leniwie.

Domyślny motyw pozostaje ciemny, zapisany wybór jasnego jest respektowany.
Natywne formularze i FAQ działają bez JS; `prefers-reduced-motion` wyłącza ruch.

## Jak powtórzyć sprawdzenia

Standardowe testy:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_site.py
.venv/bin/python -m compileall -q app.py manage.py wedding scripts deploy tests
bash -n deploy/ssh-command.sh
git diff --check
```

Opcjonalne audyty przeglądarkowe wymagają dodatkowego, **lokalnego** Playwright
i Chromium; nie są zależnościami produkcyjnymi:

```sh
.venv/bin/pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/check_editorial_browser.py
.venv/bin/python scripts/check_guest_browser.py
```

Do ponownego porównania po commicie można wskazać bazę PR:
`scripts/check_editorial_browser.py --baseline-ref origin/main`.
Oba skrypty przyjmują `--browser chromium|firefox|webkit` (domyślnie Chromium).
Pozostałe silniki wymagają pobrania odpowiednich przeglądarek Playwright
i ich bibliotek systemowych na hoście testowym. Niedostępne typy pomiarów
PerformanceObserver nie są przedstawiane jako zmierzone zero.

`check_editorial_browser.py` porównuje `HEAD` z katalogiem roboczym i sprawdza
40 wariantów nowej strony: PL/EN, dark/light, szerokości
320, 360, 390, 430, 600, 601, 768, 900, 1024 i 1440 px.
Sprawdza także FAQ klawiaturą, koty, brak JS i ograniczenie ruchu.
Opcjonalny `--axe-path /lokalna/sciezka/axe.min.js` uruchamia wybrane reguły
WCAG A/AA, ale nie stanowi certyfikacji dostępności.

`check_guest_browser.py` używa wyłącznie syntetycznych kont i tymczasowej bazy.
Sprawdza rzeczywiste formularze logowania, podgląd kodu, zapis RSVP i wylogowanie,
96 układów publicznych/prywatnych oraz odpowiedź bez JS. Uruchamia tymczasowy
serwer HTTPS wyłącznie na loopbacku, z certyfikatem testowym wygenerowanym
przez OpenSSL. Sprawdza rzeczywiste cookies przeglądarki, blokuje żądania
zewnętrzne i nie loguje się do produkcji.

Artefakty trafiają poza repozytorium do `/tmp/opencode/`. Zrzut w README
przedstawia wyłącznie publiczną część strony. Żadne konta, kody zaproszeń
ani odpowiedzi nie są materiałami promocyjnymi.

Wyniki lokalne nie zastępują testu na fizycznym telefonie, Safari/Firefox,
czytniku ekranu ani pomiarów rzeczywistych użytkowników. Lokalny LCP/CLS
z przechwyconą siecią nie jest dowodem spełnienia produkcyjnych Core Web Vitals.

## Wynik lokalnej walidacji — 16 listopada 2026

- **159 dotychczasowych testów regresji + 3 nowe testy UX — OK.**
  Po ostatniej korekcie nagłówka powtórzono także trzy testy motywu i niespodzianek.
- **40 nowych wariantów publicznej strony + 2 porównawcze — OK**:
  bez poziomego overflow i bez kolizji marki z przełącznikiem.
- **96 wariantów zalogowanych/publicznych — OK** oraz rzeczywiste logowanie
  przez lokalny HTTPS, podgląd kodu, zapis RSVP, wylogowanie i odpowiedź bez JS.
- **8 kontroli axe — 0 naruszeń** wybranych reguł A/AA. Pozostały przypadki
  `incomplete` dla `aria-prohibited-attr` i `color-contrast`, wymagające oceny
  ręcznej; nie jest to deklaracja pełnej zgodności WCAG.
- Schematy Dependabota i obu formularzy GitHub — OK; tekst MIT porównany ze SPDX.
- Renderowanie, lokalne linki i zasoby, składnia Python/JS/Bash, pakowanie
  i kontrola białych znaków — OK.

Końcowe dowody poza repozytorium:
`/tmp/opencode/wedding-refresh-verified/`,
`/tmp/opencode/wedding-refresh-guest-verified.log`,
`/tmp/opencode/wedding-refresh-tests.log`.
README zawiera zrzuty publicznego widoku przy 1440 i 390 px.
Na tym pierwszym etapie nie wykonano push ani wdrożenia; późniejsza publikacja
podlega odrębnemu audytowi i kontrolom CI.
