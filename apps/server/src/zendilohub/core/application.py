import logging
from collections.abc import Sequence
from dataclasses import dataclass

from redis.asyncio import Redis

from .config import AppConfig
from .contracts import Contracts
from .database.database import Database
from .database.migrator import Migrator
from .domain.app_domain_error import AppDomainError
from .domain.clock import Clock
from .domain.http_fetch import PublicFetcher
from .domain.id_generator import IdGenerator
from .domain.jobs import JobQueue
from .domain.mailer import Mailer
from .events.event_bus import EventBus
from .http.http_kernel import HttpKernel
from .infrastructure.mailers import LogMailer, SmtpMailer
from .infrastructure.public_fetcher import AiohttpPublicFetcher
from .infrastructure.redis_rate_limiter import RedisRateLimiter
from .infrastructure.rq_jobs import RqJobQueue
from .infrastructure.secret_key import SecretKey
from .infrastructure.system_clock import system_clock
from .infrastructure.uuid_generator import uuid_generator
from .module import AppModule, CliCommand, CliOutput, ModuleContext, ModuleFactory, Role
from .scheduler import Scheduler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Application:
    """Wires modules together, runs migrations and drives the app's lifecycle."""

    config: AppConfig
    context: ModuleContext
    modules: Sequence[AppModule]

    @property
    def http(self) -> HttpKernel:
        return self.context.http

    @property
    def db(self) -> Database:
        return self.context.db

    @classmethod
    def create(
        cls,
        config: AppConfig,
        *,
        modules: Sequence[ModuleFactory],
        role: Role = 'web',
        db: Database | None = None,
        redis: Redis | None = None,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
        mailer: Mailer | None = None,
        jobs: JobQueue | None = None,
        fetcher: PublicFetcher | None = None,
    ) -> Application:
        """Builds every module without touching the database, so e.g. the OpenAPI schema needs no services."""
        redis = redis or Redis.from_url(config.redis_url)
        clock = clock or system_clock
        secret = SecretKey(config.secret_key, config.data_dir)
        context = ModuleContext(
            config=config,
            role=role,
            db=db or Database(config.database_url),
            redis=redis,
            http=HttpKernel(api_docs=config.api_docs, secret=lambda: secret.value),
            events=EventBus(),
            clock=clock,
            ids=ids or uuid_generator,
            rate_limiter=RedisRateLimiter(redis, clock),
            mailer=mailer or (SmtpMailer(config.mail) if config.mail.host else LogMailer()),
            jobs=jobs or RqJobQueue(config.redis_url),
            fetcher=fetcher or AiohttpPublicFetcher(),
            contracts=Contracts.empty(),
            scheduler=Scheduler(),
        )
        context.http.use_audit_sink(context.events.publish)
        built = [factory(context) for factory in modules]
        for module in built:
            for router in module.routers:
                context.http.routes(router)
            for router in module.root_routers:
                context.http.root_routes(router)
        context.http.add_health_check('database', context.db.ping)
        context.http.add_health_check('redis', lambda: _ping(context.redis))
        return cls(config, context, built)

    async def start(self, *, migrate: bool = True, schedule: bool = True) -> None:
        """Connects, migrates, boots every module and (for the web role) runs the periodic jobs and serves the web app.

        Tests pass `schedule=False` and run the jobs themselves.
        """
        await self.db.open()
        if migrate:
            await self.migrate()
        for module in self.modules:
            await module.boot()
        if self.context.role != 'web':
            return
        if schedule:
            self.context.scheduler.start()
        web_dir = self.config.web_dir
        if web_dir and not self.http.serve_web_app(web_dir):
            logger.warning('No web app build found, serving the API only', extra={'web_dir': str(web_dir)})

    async def migrate(self) -> list[str]:
        """Runs the pending migrations of all modules; returns their names."""
        return await Migrator(self.db).run([migration for module in self.modules for migration in module.migrations])

    async def run_command(self, argv: Sequence[str], output: CliOutput) -> int:
        """Runs a module's CLI command such as `make-admin someone@example.org` and returns the exit code."""
        commands = self._commands()
        name = argv[0] if argv else None
        command = commands.get(name) if name else None
        if command is None:
            output.error('No command given.' if name is None else f'Unknown command "{name}".')
            output.error('Available commands:')
            for registered in commands.values():
                output.error(f'  {registered.usage:<40} {registered.description}')
            return 1
        try:
            return await command.run(argv[1:], output)
        except AppDomainError as error:
            output.error(error.message)
            return 1

    async def run_task(self, name: str, *args: str) -> None:
        """Runs a module's background job (in a worker)."""
        for module in self.modules:
            task = module.tasks.get(name)
            if task is not None:
                await task(*args)
                return
        raise LookupError(f'No module has a task "{name}"')

    async def shutdown(self) -> None:
        await self.context.scheduler.stop()
        for module in reversed(self.modules):
            await module.shutdown()
        await self.db.close()
        await self.context.redis.aclose()

    def _commands(self) -> dict[str, CliCommand]:
        return {name: command for module in self.modules for name, command in module.commands.items()}


async def _ping(redis: Redis) -> bool:
    try:
        return bool(await redis.ping())
    except Exception:
        return False
