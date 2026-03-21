from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hello_service.core_modules.hello import HelloModule
import landing_gear.loader as loader_mod
from hello_service.domain import HelloRepository
from landing_gear.loader import ModuleManager
from landing_gear.modules import CoreModule, ModuleInfo
from landing_gear.requests import ensure_identifier_value, get_query_pagination
from landing_gear.service_shape import build_service_shape


class DummyRequest:
    def __init__(self, query=None):
        self.query = DummyQuery(query or {})


class DummyQuery(dict):
    def getall(self, name, default=None):
        if name in self:
            value = self[name]
            if isinstance(value, list):
                return value
            return [value]
        return [] if default is None else default


class FakeCtx:
    def __init__(self):
        self.service_name = 'hello-service'
        self._repo = HelloRepository(service_name=self.service_name)

    async def read_json(self, request):
        return {'name': 'Erica'}

    def reject_unknown_fields(self, payload, *, allowed):
        return None

    def require_fields(self, payload, *names):
        return None

    def ensure_identifier_value(self, value, *, field='value', max_len=128):
        return ensure_identifier_value(value, field=field, max_len=max_len)

    def get_repository(self, name):
        assert name == 'hello'
        return self._repo

    def json_created(self, payload, request=None):
        return payload

    def get_query_pagination(self, request, default_limit=10, max_limit=25):
        return get_query_pagination(request, default_limit=default_limit, max_limit=max_limit)

    def json_collection(self, items, request=None, total=0, limit=0, offset=0):
        return {'items': items, 'total': total, 'limit': limit, 'offset': offset}


class LoaderCtx:
    def __init__(self):
        self.events = []
        self.event_payloads = []
        self.state = {}
        self.service_name = 'hello-service'
        self.calls = SimpleNamespace(calls={})
        self.loaded_modules = []

    def claim_config_section(self, *args, **kwargs):
        return None

    def record_module_state(self, *args, **kwargs):
        return None

    def record_lifecycle_event(self, name, **kwargs):
        self.events.append(name)
        self.event_payloads.append((name, kwargs))

    async def emit_hook(self, *args, **kwargs):
        return []

    class _Tasks:
        async def run_startup(self):
            return {}

        async def run_shutdown(self):
            return {}

    tasks = _Tasks()


class StartFailModule:
    INFO = type('Info', (), {'id': 'mod.start', 'kind': 'core'})

    async def start(self):
        raise RuntimeError('boom')


class StopFailModule:
    INFO = type('Info', (), {'id': 'mod.stop', 'kind': 'core'})

    async def stop(self):
        raise RuntimeError('boom')


class SetupFailModule(CoreModule):
    INFO = ModuleInfo(id='mod.setup', name='setup-fail', version='0.1.0', description='fails in setup', kind='core')

    async def setup(self):
        raise RuntimeError('boom during setup')


class StarterRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_hello_post_uses_identifier_value_correctly(self):
        module = HelloModule(FakeCtx())
        result = await module.hello_post(object())
        self.assertEqual(result['message'], 'Hello, Erica!')
        self.assertEqual(result['request_number'], 1)

    async def test_hello_history_uses_pagination_values_not_dict_keys(self):
        ctx = FakeCtx()
        module = HelloModule(ctx)
        for name in ['one', 'two', 'three']:
            ctx._repo.greet(name)
        result = await module.hello_history(DummyRequest({'limit': '2', 'offset': '1'}))
        self.assertEqual(result['limit'], 2)
        self.assertEqual(result['offset'], 1)
        self.assertEqual([item['name'] for item in result['items']], ['two', 'one'])

    async def test_loader_uses_correct_failure_event_names(self):
        ctx = LoaderCtx()
        manager = ModuleManager(ctx)
        manager.modules = [StartFailModule()]
        with self.assertRaises(RuntimeError):
            await manager.start_all()
        self.assertIn('module.start_failed', ctx.events)

        ctx = LoaderCtx()
        manager = ModuleManager(ctx)
        manager.modules = [StopFailModule()]
        with self.assertRaises(RuntimeError):
            await manager.stop_all()
        self.assertIn('module.stop_failed', ctx.events)

    async def test_loader_setup_failure_uses_instance_info_in_exception_path(self):
        ctx = LoaderCtx()
        manager = ModuleManager(ctx)
        spec = SimpleNamespace(
            name='setup_fail',
            depends_on=[],
            import_path='fake.module',
            class_name='SetupFailModule',
            config={},
            manifest_path=None,
            compatible_services=['hello-service'],
        )
        fake_module = SimpleNamespace(SetupFailModule=SetupFailModule, __file__=__file__)
        fake_manifest = SimpleNamespace(
            module_id='mod.setup',
            name='setup-fail',
            version='0.1.0',
            kind='core',
            compatible_services=['hello-service'],
            required_calls=[],
            required_scopes=[],
            tags=[],
        )
        with patch.object(loader_mod.importlib, 'import_module', return_value=fake_module):
            with patch.object(loader_mod, 'resolve_manifest', return_value=fake_manifest):
                with patch.object(loader_mod, 'validate_manifest', return_value=None):
                    with self.assertRaisesRegex(RuntimeError, 'boom during setup'):
                        await manager.load([spec], kind='core_module')
        self.assertIn('module.start_failed', ctx.events)
        failure_events = [payload for name, payload in ctx.event_payloads if name == 'module.start_failed']
        self.assertTrue(failure_events)
        self.assertEqual(failure_events[-1]['module_id'], 'mod.setup')

    def test_runtime_views_do_not_advertise_phantom_routes(self):
        from landing_gear.context import ServiceContext

        ctx = object.__new__(ServiceContext)
        runtime_views = ServiceContext.runtime_views(ctx)

        self.assertEqual(runtime_views['generic_service_runtime'], '/status')
        self.assertEqual(runtime_views['service_runtime'], '/api/service/runtime')
        self.assertNotIn('broker_runtime', runtime_views)
        self.assertNotIn('diagnostics', runtime_views)

    def test_component_groups_use_service_domain_name(self):
        from landing_gear.context import ServiceContext

        ctx = object.__new__(ServiceContext)
        ctx.components = {'repo': object(), 'runtime': object()}
        ctx.component_metadata = {
            'repo': {'kind': 'service_domain'},
            'runtime': {'kind': 'service_runtime'},
        }
        ctx.component_owners = {}

        groups = ServiceContext.component_groups(ctx)

        self.assertIn('service_domain', groups)
        self.assertEqual(groups['service_domain'], ['repo'])
        self.assertNotIn('broker_domain', groups)

    def test_hello_repository_history_is_trimmed_in_place(self):
        repo = HelloRepository(service_name='hello-service')
        original = repo.history
        for idx in range(30):
            repo.greet(f'name-{idx}')
        self.assertIs(repo.history, original)
        self.assertEqual(len(repo.history), 25)


class StaticRegressionTests(unittest.TestCase):
    def test_service_shape_defaults_domain_package_to_domain(self):
        shape = build_service_shape({'service': {'name': 'demo', 'package_root': 'demo_service'}})
        self.assertEqual(shape.domain_package, 'domain')


if __name__ == '__main__':
    unittest.main()
