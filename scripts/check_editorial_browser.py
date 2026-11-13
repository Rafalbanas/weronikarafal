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
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
        app = create_app({'TESTING': True, 'SECRET_KEY': 'browser-test-' + 'x' * 40,
                          'DATABASE': directory + '/db', 'DETAILS': directory + '/details.json'})
        client = app.test_client()
        pages = {lang: client.get('/?lang=' + lang, base_url='https://localhost')
                 for lang in ('pl', 'en')}
        old = {name: subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT)
               for name in ('index.html', 'templates/base.html', 'assets/site.css', 'assets/site.js')}
        app.jinja_loader = ChoiceLoader([DictLoader({name: data.decode() for name, data in old.items()
                                                    if name.endswith('.html')}), app.jinja_loader])
        app.jinja_env.cache.clear()
        before = client.get('/?lang=pl', base_url='https://localhost')
        browser = playwright.chromium.launch(args=['--no-sandbox'], timeout=60000)
        for mode in ('before', 'after'):
            context = browser.new_context()
            context.add_init_script("""window.editorialMetrics = {lcp: null, lcpEntries: [], cls: 0, shifts: [], longTasks: []};
                new PerformanceObserver(list => { for (const e of list.getEntries()) {
                  window.editorialMetrics.lcp = e.startTime;
                  window.editorialMetrics.lcpEntries.push({startTime: e.startTime,
                    renderTime: e.renderTime, loadTime: e.loadTime, size: e.size,
                    element: e.element ? e.element.tagName + '.' + e.element.className : null});
                  }
                }).observe({type: 'largest-contentful-paint', buffered: true});
                new PerformanceObserver(list => {for (const e of list.getEntries())
                  window.editorialMetrics.longTasks.push({startTime: e.startTime, duration: e.duration});
                }).observe({type: 'longtask', buffered: true});
                new PerformanceObserver(list => { for (const e of list.getEntries())
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
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            widths = (390, 1440) if mode == 'before' else (320, 360, 390, 430, 600, 768, 1024, 1440)
            for width in widths:
                for lang in (('pl',) if mode == 'before' else ('pl', 'en')):
                    for theme in (('dark',) if mode == 'before' else ('dark', 'light')):
                        page.set_viewport_size({'width': width, 'height': 960})
                        page.goto('https://localhost/?lang=' + lang, wait_until='networkidle')
                        if theme == 'light':
                            page.locator('[data-theme-toggle]').click()
                        expect(page.locator('html')).to_have_attribute('data-theme', theme)
                        if page.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth'):
                            page.screenshot(path=str(output / 'overflow.png'), full_page=True)
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
                                                    full_page=True, animations='disabled')
                                page.keyboard.press('Space')
                                expect(target).to_be_hidden()
                            # Repeatability and no layout movement on activation.
                            button = page.locator('.secret-heart')
                            y = page.locator('.credit').evaluate('e => e.getBoundingClientRect().top + scrollY')
                            button.click()
                            assert abs(page.locator('.credit').evaluate('e => e.getBoundingClientRect().top + scrollY') - y) < 1
                            button.click()
                        if width in (390, 1440):
                            page.screenshot(path=str(output / f'{mode}-{width}-{lang}-{theme}.png'), full_page=True)
                        results.append({'mode': mode, 'width': width, 'language': lang,
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
