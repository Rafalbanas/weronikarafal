"""Optional local UI audit. Requires Playwright + Chromium, not runtime dependencies.

Run from the repo root with a Python environment providing Flask and Playwright.
Synthetic empty settings only; never opens a production database or account.
Screenshots and JSON evidence go to --output (outside the repository by default).
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app
from jinja2 import ChoiceLoader, DictLoader
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='/tmp/opencode/wedding-editorial-audit')
    parser.add_argument('--axe-path', type=Path, help='Optional existing local axe-core script')
    parser.add_argument('--baseline-ref', default='HEAD', help='Git revision used for the before screenshots')
    parser.add_argument('--browser', choices=('chromium', 'firefox', 'webkit'), default='chromium')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
        app = create_app({'TESTING': True, 'SECRET_KEY': 'browser-test-' + 'x' * 40,
                          'DATABASE': directory + '/db', 'DETAILS': directory + '/details.json',
                          'UPLOADS_DIR': directory + '/uploads'})
        client = app.test_client()
        pages = {lang: client.get('/?lang=' + lang, base_url='https://localhost')
                 for lang in ('pl', 'en')}
        baseline = subprocess.check_output(
            ['git', 'rev-parse', '--verify', '--end-of-options', args.baseline_ref + '^{commit}'],
            cwd=ROOT, text=True).strip()
        old = {name: subprocess.check_output(['git', 'show', baseline + ':' + name], cwd=ROOT)
               for name in ('index.html', 'templates/base.html', 'assets/site.css', 'assets/site.js')}
        app.jinja_loader = ChoiceLoader([DictLoader({name: data.decode() for name, data in old.items()
                                                    if name.endswith('.html')}), app.jinja_loader])
        app.jinja_env.cache.clear()
        before = client.get('/?lang=pl', base_url='https://localhost')
        browser = getattr(playwright, args.browser).launch(
            args=['--no-sandbox'] if args.browser == 'chromium' else [], timeout=60000)
        for mode in ('before', 'after'):
            context = browser.new_context()
            context.add_init_script("""const supported = typeof PerformanceObserver === 'function'
                  ? PerformanceObserver.supportedEntryTypes : [];
                window.editorialMetrics = {lcp: null, lcpEntries: [],
                  cls: supported.includes('layout-shift') ? 0 : null,
                  shifts: [], longTasks: [], supportedEntries: supported};
                if (supported.includes('largest-contentful-paint')) new PerformanceObserver(list => { for (const e of list.getEntries()) {
                  window.editorialMetrics.lcp = e.startTime;
                  window.editorialMetrics.lcpEntries.push({startTime: e.startTime,
                    renderTime: e.renderTime, loadTime: e.loadTime, size: e.size,
                    element: e.element ? e.element.tagName + '.' + e.element.className : null});
                  }
                }).observe({type: 'largest-contentful-paint', buffered: true});
                if (supported.includes('longtask')) new PerformanceObserver(list => {for (const e of list.getEntries())
                  window.editorialMetrics.longTasks.push({startTime: e.startTime, duration: e.duration});
                }).observe({type: 'longtask', buffered: true});
                if (supported.includes('layout-shift')) new PerformanceObserver(list => { for (const e of list.getEntries())
                  if (!e.hadRecentInput) {
                    window.editorialMetrics.cls += e.value;
                    window.editorialMetrics.shifts.push({value: e.value, sources:
                      e.sources.map(s => s.node ? s.node.tagName + '.' + s.node.className : null)});
                  }
                }).observe({type: 'layout-shift', buffered: true});""")

            def respond(route):
                url = urlsplit(route.request.url)
                if url.path.startswith('/assets/'):
                    name = url.path.rsplit('/', 1)[-1]
                    mime = 'text/css' if name.endswith('.css') else 'text/javascript' if name.endswith('.js') else 'image/svg+xml'
                    data = old.get('assets/' + name) if mode == 'before' else None
                    route.fulfill(body=data or (ROOT / 'assets' / name).read_bytes(), content_type=mime)
                else:
                    lang = parse_qs(url.query).get('lang', ['pl'])[0]
                    response = before if mode == 'before' else pages[lang]
                    route.fulfill(body=response.data, content_type='text/html; charset=utf-8',
                                  headers={'Content-Security-Policy': response.headers['Content-Security-Policy']})

            context.route('https://localhost/**', respond)
            context.route('https://www.google.com/**', lambda route: route.fulfill(body=''))
            page = context.new_page()
            page.set_default_navigation_timeout(120000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            widths = (390, 1440) if mode == 'before' else (320, 360, 390, 430, 600, 601, 768, 900, 1024, 1440)
            for width in widths:
                for lang in (('pl',) if mode == 'before' else ('pl', 'en')):
                    for theme in (('dark',) if mode == 'before' else ('dark', 'light')):
                        page.set_viewport_size({'width': width, 'height': 960})
                        page.goto('https://localhost/?lang=' + lang, wait_until='networkidle')
                        if theme == 'light':
                            page.locator('[data-theme-toggle]').click()
                        expect(page.locator('html')).to_have_attribute('data-theme', theme)
                        if page.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth'):
                            page.screenshot(path=str(output / 'overflow.png'), full_page=True, timeout=120000)
                            raise AssertionError((mode, width, lang, theme, page.evaluate("""[...document.querySelectorAll('body *')]
                                .filter(e => e.getBoundingClientRect().right > document.documentElement.clientWidth)
                                .map(e => [e.tagName, e.getAttribute('class'), e.getBoundingClientRect().right])""")))
                        accessibility = None
                        if mode == 'after' and args.axe_path and width in (320, 1440):
                            page.evaluate(args.axe_path.read_text())
                            accessibility = page.evaluate("""async () => {
                                const result = await axe.run(document, {runOnly: {
                                  type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}});
                                return {violations: result.violations.map(v => ({id: v.id,
                                  impact: v.impact, nodes: v.nodes.map(n => n.target)})),
                                  incomplete: result.incomplete.map(v => v.id)};
                            }""")
                            assert not accessibility['violations'], (width, lang, theme, accessibility)
                        if mode == 'after':
                            brand = page.locator('.brand').bounding_box()
                            theme_control = page.locator('[data-theme-toggle]').bounding_box()
                            overlaps = (
                                brand['x'] < theme_control['x'] + theme_control['width']
                                and theme_control['x'] < brand['x'] + brand['width']
                                and brand['y'] < theme_control['y'] + theme_control['height']
                                and theme_control['y'] < brand['y'] + brand['height']
                            )
                            assert not overlaps, (width, lang, theme, 'Brand overlaps theme control')
                            primary = page.locator('.hero-actions .button').first
                            expect(primary).to_have_attribute('href', '/login')
                            assert primary.evaluate('e => e.getBoundingClientRect().height >= 48')
                            expect(page.locator('.hero-utility a[href="#ceremonia"]')).to_be_visible()
                            expect(page.locator('.hero-utility a[href="#pytania"]')).to_be_visible()
                            expect(page.locator('.day-at-a-glance')).to_be_visible()
                            # A visible focus indicator and native accordion must work by keyboard.
                            summary = page.locator('.faq summary').first
                            page.keyboard.press('Tab')
                            summary.focus()
                            assert summary.evaluate("e => getComputedStyle(e).outlineStyle != 'none'")
                            page.keyboard.press('Enter')
                            expect(page.locator('.faq details').first).to_have_attribute('open', '')
                            page.keyboard.press('Enter')
                            expect(page.locator('.faq details').first).not_to_have_attribute('open', '')
                            assert page.locator('.countdown span').first.evaluate('e => parseFloat(getComputedStyle(e).fontSize) >= 11')
                            for secret in ('star', 'heart'):
                                button = page.locator('[data-surprise="' + secret + '-secret"]')
                                target = page.locator('#' + secret + '-secret')
                                poster_height = page.locator('.date-poster').evaluate('e => e.offsetHeight')
                                button.focus()
                                page.keyboard.press('Enter')
                                expect(target).to_be_visible()
                                expect(button).to_have_attribute('aria-expanded', 'true')
                                if secret == 'star':
                                    # The discovery replaces decorative copy, never the date/time.
                                    geometry = page.evaluate('''() => {
                                      const note = document.querySelector('.star-scene p').getBoundingClientRect();
                                      const date = document.querySelector('.poster-date').getBoundingClientRect();
                                      const footer = document.querySelector('.poster-bottom').getBoundingClientRect();
                                      return {noteTop: note.top, noteBottom: note.bottom,
                                        dateBottom: date.bottom, footerTop: footer.top,
                                        font: parseFloat(getComputedStyle(document.querySelector('.star-scene p')).fontSize)};
                                    }''')
                                    assert geometry['noteTop'] >= geometry['dateBottom'] - 1, geometry
                                    assert geometry['noteBottom'] <= geometry['footerTop'] + 1, geometry
                                    assert geometry['font'] >= 12, geometry
                                    assert page.locator('.date-poster').evaluate('e => e.offsetHeight') == poster_height, 'Star scene moved content'
                                else:
                                    assert target.evaluate('e => e.scrollHeight <= e.parentElement.clientHeight'), 'Clipped heart scene'
                                if width in (390, 1440) and lang == 'pl' and theme == 'dark':
                                    page.screenshot(path=str(output / f'{secret}-{width}.png'),
                                                    full_page=True, animations='disabled', timeout=120000)
                                page.keyboard.press('Space')
                                expect(target).to_be_hidden()
                            # Repeatability and no layout movement on activation.
                            button = page.locator('.secret-heart')
                            y = page.locator('.credit').evaluate('e => e.getBoundingClientRect().top + scrollY')
                            button.click()
                            assert abs(page.locator('.credit').evaluate('e => e.getBoundingClientRect().top + scrollY') - y) < 1
                            button.click()
                        if width in (390, 1440):
                            page.screenshot(path=str(output / f'{mode}-{width}-{lang}-{theme}.png'),
                                            full_page=True, timeout=120000)
                            if mode == 'after' and lang == 'pl':
                                page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                                page.screenshot(path=str(output / f'preview-{width}-{theme}.png'),
                                                animations='disabled', timeout=120000)
                        results.append({'mode': mode, 'browser': args.browser, 'baseline_revision': baseline,
                                        'width': width, 'language': lang,
                                        'theme': theme, 'overflow': False, 'axe': accessibility,
                                        'local_unthrottled_metrics': page.evaluate('window.editorialMetrics')})
                        # Clear the saved preference before the next combination.
                        page.evaluate('localStorage.clear()')
            assert not errors, errors
            context.close()
        for reduced, javascript in ((True, True), (False, False)):
            context = browser.new_context(java_script_enabled=javascript,
                                          reduced_motion='reduce' if reduced else 'no-preference',
                                          viewport={'width': 320, 'height': 960})
            context.route('https://localhost/**', respond)
            context.route('https://www.google.com/**', lambda route: route.fulfill(body=''))
            page = context.new_page()
            page.set_default_navigation_timeout(120000)
            page.goto('https://localhost/', wait_until='networkidle')
            expect(page.locator('h1')).to_be_visible()
            expect(page.locator('time.poster-date')).to_be_visible()
            expect(page.locator('#ceremonia')).to_be_visible()
            if not javascript:
                expect(page.locator('.secret-star')).to_be_hidden()
                expect(page.locator('.secret-heart')).to_be_hidden()
                page.locator('.faq summary').first.click()
                expect(page.locator('.faq details').first).to_have_attribute('open', '')
            else:
                assert page.locator('.name-first').evaluate('e => getComputedStyle(e).animationName') == 'none'
            context.close()
        browser.close()
    (output / 'results.json').write_text(json.dumps(results, indent=2))
    print(f'{len(results)} layout combinations OK; keyboard, repeat, no-JS and reduced-motion OK. Evidence: {output}')


if __name__ == '__main__':
    main()
