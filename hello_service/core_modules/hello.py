from __future__ import annotations

from landing_gear.decorators import allow_anonymous, health_check, route, startup_task
from landing_gear.modules import CoreModule, ModuleInfo

from hello_service.domain import HelloRepository


class HelloModule(CoreModule):
    INFO = ModuleInfo(
        id='hello.core',
        name='hello_core',
        version='0.1.0',
        description='Basic hello-world API surface for a Landing Gear service starter.',
        kind='core',
    )

    async def setup(self) -> None:
        repo = HelloRepository(service_name=self.ctx.service_name)
        self.set_repository('hello', repo)
        self.set_component(
            'hello.runtime',
            {'message': 'Hello service runtime ready'},
            kind='service_runtime',
            role='service_scaffolding',
            note='basic runtime marker for the example service',
        )
        self.claim_config_section('core_modules.hello', note='hello module config')

    def register(self) -> None:
        self.ctx.auto_register(self)

    @startup_task('hello.startup')
    async def on_startup(self) -> dict[str, object]:
        repo = self.ctx.get_repository('hello')
        return {'ok': True, 'requests_seen': repo.request_count}

    @health_check('hello.repository')
    async def hello_repository_health(self) -> dict[str, object]:
        repo = self.ctx.get_repository('hello')
        return await repo.health()

    @route('GET', '/api/hello', tags=('hello',))
    @allow_anonymous()
    async def hello(self, request):
        name = self.ctx.get_query_str(request, 'name', default='world', max_len=64)
        repo = self.ctx.get_repository('hello')
        event = repo.greet(name)
        return self.ctx.json_response(
            {
                'message': event['message'],
                'service': self.ctx.service_name,
                'request_number': event['request_number'],
            },
            request=request,
        )

    @route('POST', '/api/hello', tags=('hello',))
    @allow_anonymous()
    async def hello_post(self, request):
        body = await self.ctx.read_json(request)
        self.ctx.reject_unknown_fields(body, allowed=('name',))
        self.ctx.require_fields(body, 'name')
        name = self.ctx.ensure_identifier_value(body['name'], field='name', max_len=64)
        repo = self.ctx.get_repository('hello')
        event = repo.greet(name)
        return self.ctx.json_created(
            {
                'message': event['message'],
                'request_number': event['request_number'],
            },
            request=request,
        )

    @route('GET', '/api/hello/history', tags=('hello',))
    @allow_anonymous()
    async def hello_history(self, request):
        pagination = self.ctx.get_query_pagination(request, default_limit=10, max_limit=25)
        limit = pagination['limit']
        offset = pagination['offset']
        repo = self.ctx.get_repository('hello')
        items = list(reversed(repo.history))
        page = items[offset:offset + limit]
        return self.ctx.json_collection(
            page,
            request=request,
            total=len(items),
            limit=limit,
            offset=offset,
        )

    @route('GET', '/api/service/runtime', tags=('service',))
    @allow_anonymous()
    async def service_runtime(self, request):
        repo = self.ctx.get_repository('hello')
        return self.ctx.json_response(
            {
                'service_shape': self.ctx.service_shape(),
                'service_contract': self.ctx.service_contract(),
                'config_profile': self.ctx.config_profile(),
                'readiness': self.ctx.readiness_snapshot(),
                'repositories': self.ctx.repository_snapshot(),
                'components': self.ctx.component_snapshot(),
                'lifecycle': self.ctx.lifecycle_snapshot(),
                'hello_summary': repo.summary(),
            },
            request=request,
        )
