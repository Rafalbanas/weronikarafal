# Raport z audytu technicznego (16.11.2026)

## 1. Zakres audytu
Audyt przeprowadzony w dniu 16.11.2026 obejmuje następujące obszary:
- Interfejs użytkownika (UI) i wielojęzyczność (PL/EN)
- Konfiguracje motywów wizualnych
- Pliki README oraz dokumentację GitHub
- Mechanizmy autoryzacji, zabezpieczenia CSRF i zarządzanie sesjami
- Obsługa mediów i integracja z bazą SQLite
- Procesy pakowania i techniki wdrożeniowe

## 2. Poprawione problemy techniczne
W trakcie prac zidentyfikowano i naprawiono następujące błędy:

1.  **Izolacja ścieżek uploadu**: Dziedziczenie `WEDDING_UPLOADS_DIR` przez skrypty i fixture'y mogło prowadzić do usuwania starych `*.part` spoza testowej bazy. Wprowadzono jawne, tymczasowe katalogi uploadów oraz dodano 2 nowe testy regresyjne.
2.  **Zarządzanie strumieniami**: Funkcja `check_site` nie zamykała strumieni assetów. Zastosowano konteksty (with) dla zapewnienia poprawnego zwalniania zasobów.
3.  **Dostępność (A11Y)**: Nieobsługiwane `aria-label` na elemencie `time`. Pełna data jest tekstem `sr-only`, a skrót wizualny ma `aria-hidden`.
4.  **Interakcja z inputami**: Niewidoczny fokus ukrytego pola typu file w braku JS. Zastosowano `focus-within` na etykiecie (label).
5.  **Kontrast kolorystyczny**: Placeholder `#757575` posiadał współczynniki 3.77:1 (dark) / 4.28:1 (light). Zastosowanie `--muted` oraz `opacity 1` daje wartości 9.79:1 i 5.49:1.
6.  **Obsługa dialogów**: Brak `showModal` blokował standardowe usuwanie. Wprowadzono detekcję obsługi funkcji oraz test Node.js uruchamiany z zestawu unittest.
7.  **Licencjonowanie**: Brak licencji przy artefakcie. Dodano plik `LICENSE` obok `release.zip` bez modyfikacji zamkniętej paczki i odbiornika.

## 3. Status walidacji i bezpieczeństwa
- **Testy jednostkowe/integracyjne**: 162 dotychczasowych testów zakończonych sukcesem.
- **Testy ukierunkowane**: 8 testów (UX: 4, JS: 2, izolacja: 2) zakończone sukcesem.
- **Automatyczny audyt DOM (axe)**: 64 warianty przeanalizowane przed poprawkami wykazały 0 automatycznych naruszeń. Wyniki niekompletne wymagały manualnej oceny; wykryto w ten sposób błędną nazwę ARIA daty i zbadano kontrast podpowiedzi.
- **Bezpieczeństwo zależności**: 10 przypiętych pakietów zweryfikowanych w API PyPI – brak zgłoszonych ostrzeżeń (advisories).
- **Workflow**: Zweryfikowano poprawność schematów JSON dla workflow, konfiguracji Dependabota oraz formularzy issue.

Przypadki `incomplete` z axe sprawdzono osobno: pełną datę poprawiono
semantycznie, a kolory placeholderów zmierzono w trzech silnikach.
Kontrast tekstu na najjaśniejszym końcu ciemnego gradientu uploadu wynosi
6,96:1, tekstu plakatu 9,58:1, a złotych symboli na jasnym tle 5,18:1.
Strzałki dekoracyjne mają `aria-hidden`; symbole przycisków mają osobne
nazwy dostępne. Nie utożsamiano braku automatycznych naruszeń z pełnym
potwierdzeniem dostępności.

## 4. Uwagi i wymagania przed wdrożeniem
- **Ograniczenia**: Raport nie stanowi pełnego pentestu, certyfikacji WCAG ani gwarancji idealności systemu.
- **Wymogi przed merge**: Wymagane są zielone testy i standardowy Pull Request. Zabrania się omijania ochrony gałęzi `main`.
- **CI/CD**: Po scaleniu PR do `main` uruchomi się istniejący workflow wdrożenia. Nie dodano automatycznego scalania PR-ów.
- **Status publikacji**: Raport sporządzono przed publikacją. Wynik wymaganego checka i wdrożenia jest dostępny w historii GitHub Actions.

## 5. Końcowa walidacja
- [x] Testy pełne (166 testów): **OK**, 16.11.2026.
- [x] Kontrast placeholderów: **12 kontroli w Chromium, Firefox i WebKit — OK**, minimum 4,5:1.
- [x] Chromium, Firefox i WebKit: **408 wariantów bieżącego UI + 6 porównawczych — OK**.
- [x] **24 kontrole axe strony głównej — 0 automatycznych naruszeń** wybranych reguł A/AA.
- [x] W każdym silniku: logowanie, potwierdzenie i aktualizacja RSVP, faktyczne wylogowanie,
  upload przez HTTPS, dekodowanie zdjęcia, podgląd i Escape/fokus, anulowanie/potwierdzenie
  usunięcia, a także fokus, upload i pobranie niezmienionych bajtów bez JS — **OK**.
- [x] Renderowanie, składnia Python/JS/Bash, pakowanie i kontrola diff — **OK**.

Rozszerzone audyty przyjmują `--browser chromium|firefox|webkit`.
Porównanie po commicie można powtórzyć z `--baseline-ref origin/main`.
Eksport pełnostronicowego PNG w Firefox wymagał wydłużenia limitu czasu na
obciążonym hoście; końcowy eksport i wszystkie asercje przeszły. Test zmiany
ról jawnie czeka na odpowiedź POST wylogowania oraz sprawdza rzeczywisty
brak dostępu po wylogowaniu, zamiast polegać na samym kliknięciu.

WebKit na Linuksie nie jest testem fizycznego Safari/VoiceOver.
Firefox używał bibliotek testowych rozpakowanych wyłącznie w
`/tmp/opencode/`; nie instalowano pakietów systemowych na serwerze.
Wyniki i syntetyczne zrzuty przechowywano poza repozytorium pod prefiksem
`/tmp/opencode/wedding-audit-`.
