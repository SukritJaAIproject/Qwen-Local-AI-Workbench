"""General-search reliability, filtering, and MCP error/read contracts.

External providers are deterministic fixtures; live coverage is recorded separately.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
import test_security_common as C

ws = C.import_websearch()
g = ws.general_search


def row(url='https://example.org/a', title='Example', body='A public search result'):
    return {'title': title, 'href': url, 'body': body}


class GeneralSearchTests(unittest.TestCase):
    def setUp(self):
        g._CACHE.clear()
        g._COOLDOWNS.clear()
        self.ready = patch.object(g, '_prepare_client').start()
        self.available = patch.object(g, '_available_engines', return_value={
            'yahoo': object(), 'duckduckgo': object(), 'brave': object(), 'google': object(), 'bing': object()}).start()
        self.addCleanup(patch.stopall)

    def test_fallback_retains_success_after_fast_rate_error(self):
        with patch.object(g, '_query_engine', side_effect=[RuntimeError('HTTP 429'), [row()]]) as query:
            hits, info = g.search({'backends': ['brave', 'yahoo']}, 'example', 1)
        self.assertEqual(hits[0][1], 'https://example.org/a')
        self.assertEqual([call.args[0] for call in query.call_args_list], ['brave', 'yahoo'])
        self.assertEqual(info['engines_failed'], ['brave'])

    def test_rate_limited_engine_is_skipped_for_next_query(self):
        with patch.object(g, '_query_engine', side_effect=[RuntimeError('HTTP 429'), [row()], [row()]]) as query:
            g.search({'backends': ['brave', 'yahoo']}, 'first', 1)
            g.search({'backends': ['brave', 'yahoo']}, 'second', 1)
        self.assertEqual([call.args[0] for call in query.call_args_list], ['brave', 'yahoo', 'yahoo'])

    def test_disabled_backend_never_falls_back_to_auto(self):
        self.available.return_value = {'yahoo': object()}
        with patch.object(g, '_query_engine') as query:
            with self.assertRaises(g.SearchUnavailable):
                g.search({'backends': ['bing']}, 'example', 1)
        query.assert_not_called()

    def test_auto_and_wikipedia_are_rejected(self):
        for backend in ('auto', 'wikipedia', 'grokipedia'):
            with self.subTest(backend=backend), self.assertRaises(ValueError):
                g.search({'backends': [backend]}, 'example', 1)

    def test_domain_filter_is_exact_or_subdomain_and_deduplicates(self):
        rows = [row('https://docs.python.org/a?utm_source=x#one'),
                row('https://docs.python.org/a#two'), row('https://docs.python.org.evil.test/a'),
                row('https://python.org/a'), row('javascript:alert(1)'),
                row('https://user:password@docs.python.org/a'), None]
        with patch.object(g, '_query_engine', return_value=rows):
            hits, _ = g.search({'backends': ['yahoo']}, 'TaskGroup', 4, domains=['docs.python.org'])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], 'https://docs.python.org/a#one')

    def test_engine_without_in_domain_hits_tries_next_engine(self):
        with patch.object(g, '_query_engine', side_effect=[
                [row('https://other.org/a')], [row('https://docs.python.org/a')]]) as query:
            hits, _ = g.search({'backends': ['yahoo', 'duckduckgo']}, 'TaskGroup', 1, domains=['docs.python.org'])
        self.assertEqual(len(hits), 1)
        self.assertEqual(query.call_count, 2)

    def test_all_failed_engines_are_real_errors(self):
        with patch.object(g, '_query_engine', side_effect=RuntimeError('network failed')):
            with self.assertRaises(g.SearchUnavailable):
                g.search({'backends': ['yahoo', 'duckduckgo']}, 'example', 1)

    def test_genuine_no_results_is_not_an_outage(self):
        with patch.object(g, '_query_engine', side_effect=RuntimeError('No results found.')):
            hits, _ = g.search({'backends': ['yahoo']}, 'nonexistent phrase', 1)
        self.assertEqual(hits, [])

    def test_cache_respects_scope_and_page(self):
        with patch.object(g, '_query_engine', return_value=[row()]) as query:
            g.search({'backends': ['yahoo']}, 'example', 1)
            g.search({'backends': ['yahoo']}, 'example', 1)
            g.search({'backends': ['yahoo']}, 'example', 1, page=2)
            g.search({'backends': ['yahoo']}, 'example', 1, region='th-th')
            g.search({'backends': ['yahoo']}, 'example', 1, recency_days=7)
            # The same effective site: query with a required domain must not
            # reuse unfiltered cached results from a raw user search string.
            g.search({'backends': ['yahoo']}, 'example site:docs.python.org', 1)
            restricted, _ = g.search({'backends': ['yahoo']}, 'example', 1, domains=['docs.python.org'])
        self.assertEqual(query.call_count, 6)
        self.assertEqual(restricted, [])

    def test_thai_region_and_coarse_freshness_are_explicit(self):
        info = g.scope('เทคโนโลยี', domains=['EXAMPLE.ORG'], recency_days=4)
        self.assertEqual(info['region'], 'th-th')
        self.assertEqual(info['timelimit'], 'w')
        self.assertEqual(info['window_days'], 7)
        self.assertEqual(info['query'], 'เทคโนโลยี site:example.org')

    def test_bad_domains_page_recency_and_region_are_rejected(self):
        bad = [{'domains': ['https://example.org/path']}, {'domains': ['x OR site:example.org']},
               {'domains': ['example.org'] * 6}, {'page': True}, {'page': 6},
               {'recency_days': True}, {'recency_days': 366}, {'region': 'th_TH'}]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                g.scope('example', **args)

    def test_news_has_separate_available_backends(self):
        with patch.object(g, '_query_engine', return_value=[row()]) as query:
            g.search({'backends': ['brave']}, 'news example', 1, search_type='news')
        self.assertEqual(query.call_args.args[0], 'bing')
        self.assertEqual(query.call_args.args[1]['search_type'], 'news')


class WebConfigurationTests(unittest.TestCase):
    def test_unusable_config_does_not_restore_restricted_search(self):
        import tempfile
        samples = (None, '{broken', '[]', 'null', '{}', '{"provider": ""}', '{"provider": null}')
        with tempfile.TemporaryDirectory() as folder:
            for index, raw in enumerate(samples):
                with self.subTest(config=raw):
                    config = Path(folder) / ('config-%d.json' % index)
                    if raw is not None:
                        config.write_text(raw, encoding='utf-8')
                    with patch.object(ws, 'CONFIG', config), \
                            patch.object(ws, '_brave_key_from_file') as key_file, \
                            patch.object(g, 'search', return_value=(
                                [('Example', 'https://example.org', 'General web result')],
                                g.scope('example'))) as search:
                        text = ws.web_search('example')
                        self.assertEqual(ws.load_config()['provider'], 'ddgs')
                    search.assert_called_once()
                    key_file.assert_not_called()
                    self.assertIn('Provider: ddgs', text)
                    self.assertNotIn('โหมด builtin', text)

    def test_bom_config_preserves_explicit_provider(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text('{"provider": "searxng", "url": "https://search.example.org"}',
                              encoding='utf-8-sig')
            with patch.object(ws, 'CONFIG', config):
                self.assertEqual(ws.load_config()['provider'], 'searxng')

    def test_explicit_builtin_remains_available_with_no_key_upgrade_hint(self):
        with patch.object(ws, 'load_config', return_value={'provider': 'builtin'}), \
                patch.dict(ws.PROVIDERS, builtin=lambda *args: []):
            text = ws.web_search('example')
        self.assertIn('โหมด builtin', text)
        self.assertIn('provider เป็น ddgs', text)
        self.assertIn('ไม่ต้องใช้ API key', text)


class WebMCPContractTests(unittest.TestCase):
    def call(self, tool, arguments):
        return ws.handle_rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': tool, 'arguments': arguments}})['result']

    def test_search_outage_is_tool_error(self):
        with patch.object(ws, 'load_config', return_value={'provider': 'ddgs'}), \
                patch.object(g, 'search', side_effect=g.SearchUnavailable('providers unavailable')):
            result = self.call('web_search', {'query': 'example'})
        self.assertTrue(result['isError'])

    def test_private_fetch_is_tool_error(self):
        result = self.call('fetch_url', {'url': 'http://127.0.0.1:8796/health'})
        self.assertTrue(result['isError'])
        self.assertIn('ปฏิเสธ:', result['content'][0]['text'])

    def test_find_reads_surrounding_text_and_offset_reads_next_section(self):
        body = '<html><body>' + 'A' * 1500 + 'TaskGroup' + 'B' * 2000 + '</body></html>'
        with patch.object(ws, 'guarded_get', return_value=('https://example.org/doc', body)):
            found = ws.fetch_url('https://example.org/doc', find='taskgroup', max_chars=800)
            next_part = ws.fetch_url('https://example.org/doc', start_char=2000, max_chars=600)
        self.assertIn('TaskGroup', found)
        self.assertIn('2000-2600', next_part)

    def test_research_parser_accepts_general_search_result_format(self):
        research = C.import_local('tools_research')
        text = ws._fmt([('Title', 'https://example.org/doc', 'Snippet')], 'example', 'Provider: ddgs')
        parsed, builtin = research.parse_search_text(text)
        self.assertEqual(parsed, [{'title': 'Title', 'url': 'https://example.org/doc', 'snippet': 'Snippet'}])
        self.assertFalse(builtin)

    def test_windows_dns_adapter_keeps_tls_verification_enabled(self):
        import ddgs.base
        with patch.object(g, '_CLIENT_READY', False), patch('primp.Client') as constructor, \
                patch.object(ddgs.base, 'HttpClient'):
            g._prepare_client()
            ddgs.base.HttpClient(verify=False)
        self.assertEqual(constructor.call_args.kwargs['dns_resolver'], 'system')
        self.assertIs(constructor.call_args.kwargs['verify'], True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
