from __future__ import annotations

import json
import unittest
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase

from service import build_app


class HelloServiceHttpTests(AioHTTPTestCase):
    async def get_application(self):
        return await build_app(Path(__file__).resolve().parents[1] / 'conf.toml')

    async def test_status_endpoint_returns_expected_runtime_surface(self):
        resp = await self.client.request('GET', '/status')
        self.assertEqual(resp.status, 200)
        payload = await resp.json()
        result = payload['result']

        self.assertTrue(payload['ok'])
        self.assertEqual(result['service'], 'hello-service')
        self.assertIn('service_shape', result)
        self.assertEqual(result['service_views']['service_runtime'], '/api/service/runtime')
        self.assertNotIn('diagnostics', result['service_views'])
        self.assertNotIn('broker_runtime', result['service_views'])

    async def test_service_runtime_endpoint_returns_repository_and_component_state(self):
        resp = await self.client.request('GET', '/api/service/runtime')
        self.assertEqual(resp.status, 200)
        payload = await resp.json()
        result = payload['result']

        self.assertTrue(payload['ok'])
        self.assertIn('repositories', result)
        self.assertIn('components', result)
        self.assertIn('hello_summary', result)
        self.assertEqual(result['hello_summary']['request_count'], 0)

    async def test_post_hello_creates_greeting(self):
        resp = await self.client.request(
            'POST',
            '/api/hello',
            data=json.dumps({'name': 'Erica'}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(resp.status, 201)
        payload = await resp.json()
        result = payload['result']
        self.assertEqual(result['message'], 'Hello, Erica!')
        self.assertEqual(result['request_number'], 1)

    async def test_hello_history_paginates_with_integer_values(self):
        for name in ['one', 'two', 'three']:
            await self.client.request(
                'POST',
                '/api/hello',
                data=json.dumps({'name': name}),
                headers={'Content-Type': 'application/json'},
            )

        resp = await self.client.request('GET', '/api/hello/history?limit=2&offset=1')
        self.assertEqual(resp.status, 200)
        payload = await resp.json()
        result = payload['result']
        pagination = payload['meta']['pagination']
        self.assertEqual(pagination['limit'], 2)
        self.assertEqual(pagination['offset'], 1)
        self.assertEqual([item['name'] for item in result['items']], ['two', 'one'])

    async def test_invalid_json_returns_bad_request(self):
        resp = await self.client.request(
            'POST',
            '/api/hello',
            data='{bad json',
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(resp.status, 400)
        payload = await resp.json()
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['code'], 'invalid_json')

    async def test_post_hello_rejects_unknown_fields(self):
        resp = await self.client.request(
            'POST',
            '/api/hello',
            data=json.dumps({'name': 'Erica', 'extra': 'nope'}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(resp.status, 400)
        payload = await resp.json()
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['code'], 'unknown_fields')

    async def test_hello_history_rejects_non_integer_limit(self):
        resp = await self.client.request('GET', '/api/hello/history?limit=nope')
        self.assertEqual(resp.status, 400)
        payload = await resp.json()
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['code'], 'invalid_query_parameter')


if __name__ == '__main__':
    unittest.main()
