from datetime import UTC, datetime

from support.app import AppUnderTest
from support.helpdesk import grant, posted, queue, ticket
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of
from zendilohub.modules.service.domain.models.sla import Calendar

WORK = ['view', 'create', 'note', 'reply', 'edit']
WEEK = {day: [('08:00', '12:00'), ('13:00', '17:00')] for day in ('mon', 'tue', 'wed', 'thu', 'fri')}


def test_counts_business_hours() -> None:
    calendar = Calendar(
        id='c',
        tenant_id='t',
        name='Office',
        timezone='Europe/Berlin',
        hours=WEEK,
        holidays=('2026-10-26',),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    # Friday 16:00 in Berlin (14:00 UTC) + 2 hours: one hour on Friday, the next on Tuesday (Monday is a holiday).
    friday = datetime(2026, 10, 23, 14, 0, tzinfo=UTC)
    assert calendar.add(friday, 120) == datetime(2026, 10, 27, 8, 0, tzinfo=UTC)
    # Over the lunch break.
    morning = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)
    assert calendar.add(morning, 90) == datetime(2026, 10, 27, 12, 30, tzinfo=UTC)


async def test_service_levels_set_deadlines_and_report_misses(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = await user_id_of(bob)
    await grant(ada, tenant, support, [bob_id], WORK)

    office = await posted(
        ada,
        f'{base}/service-calendars',
        name='Office',
        hours={day: [list(each) for each in intervals] for day, intervals in WEEK.items()},
        holidays=['2026-12-24', '2026-12-24'],
    )
    assert office['holidays'] == ['2026-12-24']
    urgent = await posted(
        ada,
        f'{base}/service-policies',
        name='Urgent',
        priorities=['urgent'],
        first_response_minutes=30,
        solution_minutes=240,
    )
    await posted(
        ada,
        f'{base}/service-policies',
        name='Normal',
        queue_ids=[support],
        first_response_minutes=480,
        calendar_id=office['id'],
    )
    setup = (await ada.get(f'{base}/service-levels')).json()
    assert [each['name'] for each in setup['policies']] == ['Urgent', 'Normal']

    # Thursday, 22 October 2026, 12:00 UTC (14:00 in Berlin).
    fast = await ticket(ada, tenant, support, 'Server down', priority='urgent', owner_id=bob_id)
    slow = await ticket(ada, tenant, support, 'Question')
    clock = (await ada.get(f'{base}/tickets/{fast["id"]}/service-level')).json()
    assert (clock['policy_id'], clock['first_response_due'], clock['solution_due']) == (
        urgent['id'],
        '2026-10-22T12:30:00Z',
        '2026-10-22T16:00:00Z',
    )
    # Eight business hours from Thursday 14:00: Thursday until 17:00, then Friday 08:00 to 13:00 (with lunch).
    assert (await ada.get(f'{base}/tickets/{slow["id"]}/service-level')).json()['first_response_due'] == (
        '2026-10-23T12:00:00Z'
    )

    # Answering in time stops the first deadline; the solution one runs out and is reported.
    await posted(ada, f'{base}/tickets/{fast["id"]}/messages', kind='public', body='Looking into it')
    app.clock.advance(hours=5)
    await app.app.context.scheduler.run_all()
    clock = (await ada.get(f'{base}/tickets/{fast["id"]}/service-level')).json()
    assert (clock['first_responded_at'] is not None, clock['breached']) == (True, ['solution'])
    escalated = [each['ticket_id'] for each in (await ada.get(f'{base}/escalations')).json()]
    assert escalated == [fast['id']]
    inbox = (await bob.get(f'{base}/notifications')).json()
    assert [each['kind'] for each in inbox['items']][:1] == ['sla_breached']

    # A lower priority picks the other level; closing stops the clock.
    await ada.patch(f'{base}/tickets/{fast["id"]}', json={'priority': 'normal'})
    assert (await ada.get(f'{base}/tickets/{fast["id"]}/service-level')).json()['policy_id'] != urgent['id']
    await ada.patch(f'{base}/tickets/{slow["id"]}', json={'state': 'closed'})
    assert (await ada.get(f'{base}/tickets/{slow["id"]}/service-level')).json()['solved_at'] is not None

    for body, field in [
        ({'name': 'X'}, 'first_response_minutes'),
        ({'name': ' ', 'solution_minutes': 5}, 'name'),
        ({'name': 'X', 'solution_minutes': 5, 'calendar_id': urgent['id']}, 'calendar_id'),
    ]:
        answer = (await ada.post(f'{base}/service-policies', json=body)).json()
        assert (answer['error'], answer['params']) == ('invalid_service', {'field': field})
    for body, field in [
        ({'name': 'X', 'hours': {}}, 'hours'),
        ({'name': 'X', 'hours': {'mon': [['17:00', '08:00']]}}, 'hours'),
        ({'name': 'X', 'timezone': 'Mars/Base', 'hours': {'mon': [['08:00', '17:00']]}}, 'timezone'),
        ({'name': 'X', 'hours': {'mon': [['08:00', '17:00']]}, 'holidays': ['someday']}, 'holidays'),
    ]:
        answer = (await ada.post(f'{base}/service-calendars', json=body)).json()
        assert (answer['error'], answer['params']) == ('invalid_service', {'field': field})
    changed = await ada.patch(
        f'{base}/service-calendars/{office["id"]}',
        json={'name': 'Office hours', 'hours': {'mon': [['09:00', '17:00']]}},
    )
    assert changed.json()['name'] == 'Office hours'
    renamed = await ada.patch(f'{base}/service-policies/{urgent["id"]}', json={'name': 'P1', 'solution_minutes': 60})
    assert renamed.json()['name'] == 'P1'
    assert (await ada.delete(f'{base}/service-calendars/{office["id"]}')).status_code == 204
    assert (await ada.delete(f'{base}/service-policies/{urgent["id"]}')).status_code == 204
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.delete(f'{base}/service-policies/{missing}')).json()['error'] == 'service_not_found'
    assert (await ada.delete(f'{base}/service-calendars/{missing}')).json()['error'] == 'service_not_found'
    assert (
        await ada.patch(
            f'{base}/service-calendars/{missing}', json={'name': 'X', 'hours': {'mon': [['08:00', '17:00']]}}
        )
    ).json()['error'] == 'service_not_found'
    assert (await ada.patch(f'{base}/service-policies/{missing}', json={'name': 'X', 'solution_minutes': 1})).json()[
        'error'
    ] == 'service_not_found'
    assert (await bob.post(f'{base}/service-policies', json={'name': 'X', 'solution_minutes': 1})).status_code == 403
    assert (await ada.get(f'{base}/tickets/{missing}/service-level')).json() is None


async def test_members_hear_about_their_tickets(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    cleo = await member_of(app, tenant, ada, 'cleo@example.org', 'agent')
    bob_id, cleo_id = await user_id_of(bob), await user_id_of(cleo)
    await grant(ada, tenant, support, [bob_id, cleo_id], WORK)
    created = await ticket(ada, tenant, support)
    path = f'{base}/tickets/{created["id"]}'

    await ada.patch(path, json={'owner_id': bob_id})
    await posted(ada, f'{path}/messages', kind='internal', body='@cleo see this', mentions=[cleo_id])
    await posted(ada, f'{path}/messages', kind='public', direction='in', body='Any news?')
    # Taking a ticket oneself is no news.
    await cleo.patch(path, json={'owner_id': cleo_id})

    bobs = (await bob.get(f'{base}/notifications')).json()
    assert [(each['kind'], each['actor']) for each in bobs['items']] == [
        ('message', 'carl@customer.example'),
        ('message', 'ada@example.org'),
        ('assigned', 'ada@example.org'),
    ]
    assert bobs['unread'] == 3
    cleos = (await cleo.get(f'{base}/notifications')).json()
    assert [each['kind'] for each in cleos['items']] == ['message', 'mentioned']

    first = bobs['items'][0]['id']
    after = (await bob.post(f'{base}/notifications/read', json={'ids': [first]})).json()
    assert after['unread'] == 2
    assert [
        each['id'] for each in (await bob.get(f'{base}/notifications', params={'unread': True})).json()['items']
    ] == [each['id'] for each in bobs['items'][1:]]
    assert (await bob.post(f'{base}/notifications/read', json={})).json()['unread'] == 0

    # By e-mail too, for whoever wants it.
    assert (await cleo.put(f'{base}/me/notification-settings', json={'email': True})).json() == {'email': True}
    assert (await cleo.get(f'{base}/me/notification-settings')).json() == {'email': True}
    await posted(ada, f'{path}/messages', kind='internal', body='Done?')
    mail = app.mailer.to('cleo@example.org')[-1]
    assert mail.subject == f'[#{created["number"]}] Printer broken: new message'
    assert f'/t/{tenant}/tickets/{created["id"]}' in mail.text
    assert app.mailer.to('bob@example.org') == [] or all(
        'new message' not in each.subject for each in app.mailer.to('bob@example.org')
    )

    # Who leaves loses their notifications.
    await ada.delete(f'{base}/members/{cleo_id}')
    async with app.app.context.db.connection() as connection:
        row = await (
            await connection.execute('SELECT count(*) AS n FROM notifications WHERE user_id = %s', (cleo_id,))
        ).fetchone()
    assert row is not None
    assert row['n'] == 0
