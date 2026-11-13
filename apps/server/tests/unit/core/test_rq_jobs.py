from redis import Redis as SyncRedis
from redis.asyncio import Redis
from rq import Queue

from support.services import Services
from zendilohub.core.infrastructure.rq_jobs import RqJobQueue


async def test_puts_jobs_into_redis_for_the_workers(services: Services, redis: Redis) -> None:
    await RqJobQueue(services.redis_url).enqueue('agents.summarize', 'conversation-1')

    jobs = Queue('default', connection=SyncRedis.from_url(services.redis_url)).jobs
    assert [(job.func_name, job.args) for job in jobs] == [
        ('zendilohub.worker.run_task', ('agents.summarize', 'conversation-1'))
    ]
    assert jobs[0].retries_left == 3


async def test_puts_delayed_jobs_into_the_schedule(services: Services, redis: Redis) -> None:
    await RqJobQueue(services.redis_url).enqueue('integrations.deliver', 'delivery-1', delay=60)

    queue = Queue('default', connection=SyncRedis.from_url(services.redis_url))
    assert queue.jobs == []
    [job_id] = queue.scheduled_job_registry.get_job_ids()
    job = queue.fetch_job(job_id)
    assert job is not None
    assert job.args == ('integrations.deliver', 'delivery-1')
