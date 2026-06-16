from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


DOCS = Path(__file__).parent / 'docs'
BASE_URL = 'https://bewaarhet.nl'

EXPECTED_PATHS = [
    '/',
    '/bonnetjes-bewaren/',
    '/facturen-bewaren/',
    '/documenten-terugvinden/',
    '/administratie-zzp/',
    '/veilig-documenten-bewaren/',
    '/hoe-werkt-bewaarhet/',
]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ''
        self.h1_count = 0
        self.meta: dict[str, str] = {}
        self.properties: dict[str, str] = {}
        self.links: dict[str, list[str]] = {}
        self.scripts: list[dict[str, str]] = []
        self._in_title = False
        self._current_heading = ''

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or '' for key, value in attrs}
        if tag == 'title':
            self._in_title = True
        if tag == 'h1':
            self.h1_count += 1
        if tag == 'meta':
            if 'name' in attrs_dict:
                self.meta[attrs_dict['name']] = attrs_dict.get('content', '')
            if 'property' in attrs_dict:
                self.properties[attrs_dict['property']] = attrs_dict.get('content', '')
        if tag == 'link':
            rel = attrs_dict.get('rel', '')
            href = attrs_dict.get('href', '')
            if rel and href:
                self.links.setdefault(rel, []).append(href)
        if tag == 'script':
            self.scripts.append(attrs_dict)

    def handle_endtag(self, tag: str) -> None:
        if tag == 'title':
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def page_file(path: str) -> Path:
    if path == '/':
        return DOCS / 'index.html'
    return DOCS / path.strip('/') / 'index.html'


def parse_page(path: str) -> PageParser:
    parser = PageParser()
    parser.feed(page_file(path).read_text(encoding='utf-8'))
    return parser


class StaticSiteSeoTests(unittest.TestCase):
    def test_expected_pages_exist(self) -> None:
        for path in EXPECTED_PATHS:
            with self.subTest(path=path):
                self.assertTrue(page_file(path).exists())

    def test_pages_have_single_h1_title_description_and_canonical(self) -> None:
        for path in EXPECTED_PATHS:
            with self.subTest(path=path):
                parser = parse_page(path)
                canonical = f'{BASE_URL}{path}'
                self.assertEqual(parser.h1_count, 1)
                self.assertGreaterEqual(len(parser.title.strip()), 20)
                self.assertIn('Bewaarhet', parser.title)
                self.assertGreaterEqual(len(parser.meta.get('description', '').strip()), 70)
                self.assertEqual(parser.links.get('canonical', [''])[0], canonical)
                self.assertEqual(parser.properties.get('og:url'), canonical)
                self.assertIn('summary_large_image', parser.meta.get('twitter:card', ''))

    def test_homepage_has_required_copy_and_visible_faq_structured_data(self) -> None:
        html = page_file('/').read_text(encoding='utf-8')
        parser = parse_page('/')
        self.assertIn('Documenten bewaren via e-mail', html)
        self.assertIn('Een vaste plek voor documenten die anders verdwijnen.', html)
        self.assertIn('Geen nieuw portaal nodig', html)
        self.assertIn('Bewaarhet registratie', html)
        self.assertIn('Geen magie als productbelofte', html)
        self.assertIn('Bewaarhet is geen boekhoudpakket.', html)
        self.assertIn('Vraag toegang aan', html)
        self.assertNotIn('magic-inbox-hero-blend-v2.png', html)
        self.assertNotIn('infographic.png', html)
        self.assertNotIn('Wat kun je bewaren?', html)
        self.assertNotIn('Voor wie is Bewaarhet?', html)
        self.assertNotIn('Voorbeelden van zoekopdrachten', html)
        self.assertNotIn('Veelgestelde vragen', html)
        self.assertTrue(any(script.get('type') == 'application/ld+json' for script in parser.scripts))
        self.assertNotIn('"@type": "FAQPage"', html)

    def test_sitemap_contains_canonical_urls(self) -> None:
        sitemap = DOCS / 'sitemap.xml'
        tree = ET.parse(sitemap)
        namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [node.text for node in tree.findall('.//sm:loc', namespace)]
        self.assertEqual(urls, [f'{BASE_URL}{path}' for path in EXPECTED_PATHS])

    def test_robots_references_sitemap_and_does_not_block_site(self) -> None:
        robots = (DOCS / 'robots.txt').read_text(encoding='utf-8')
        self.assertIn('Sitemap: https://bewaarhet.nl/sitemap.xml', robots)
        self.assertNotRegex(robots, re.compile(r'(?im)^Disallow:\s*/'))

    def test_404_is_noindex(self) -> None:
        parser = PageParser()
        parser.feed((DOCS / '404.html').read_text(encoding='utf-8'))
        self.assertEqual(parser.h1_count, 1)
        self.assertIn('noindex', parser.meta.get('robots', ''))


if __name__ == '__main__':
    unittest.main()
