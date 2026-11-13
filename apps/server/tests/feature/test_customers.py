import pytest

from support.app import AppUnderTest
from support.helpdesk import posted, queue, ticket
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of


async def test_manages_contacts_and_companies(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'

    acme = await posted(ada, f'{base}/companies', name=' Acme  Corp ', domain='@WWW.Acme.example', notes='Key account')
    assert (acme['name'], acme['domain'], acme['contact_count']) == ('Acme Corp', 'acme.example', 0)

    # An address of the company's domain joins it on its own.
    carl = await posted(ada, f'{base}/contacts', name='Carl', email=' Carl@ACME.example ', phone='+49 30 1234')
    assert (carl['email'], carl['company']) == ('carl@acme.example', {'id': acme['id'], 'name': 'Acme Corp'})
    dora = await posted(ada, f'{base}/contacts', email='dora@else.example')
    assert (dora['name'], dora['company']) == ('dora@else.example', None)
    phone_only = await posted(ada, f'{base}/contacts', phone='0171 555')
    assert phone_only['name'] == '0171 555'

    listed = (await ada.get(f'{base}/contacts', params={'q': 'acme'})).json()
    assert [each['id'] for each in listed['items']] == [carl['id']]
    assert (await ada.get(f'{base}/contacts', params={'company_id': acme['id']})).json()['total'] == 1
    assert (await ada.get(f'{base}/contacts')).json()['total'] == 3
    assert (await ada.get(f'{base}/companies', params={'q': 'acme'})).json()['items'][0]['contact_count'] == 1

    moved = await ada.patch(
        f'{base}/contacts/{dora["id"]}', json={'name': 'Dora', 'email': 'dora@else.example', 'company_id': acme['id']}
    )
    assert moved.json()['company']['name'] == 'Acme Corp'
    assert (await ada.get(f'{base}/contacts/{dora["id"]}')).json()['name'] == 'Dora'
    company = (await ada.get(f'{base}/companies/{acme["id"]}')).json()
    assert company['contact_count'] == 2
    renamed = await ada.patch(f'{base}/companies/{acme["id"]}', json={'name': 'Acme', 'domain': None})
    assert (renamed.json()['name'], renamed.json()['domain'], renamed.json()['contact_count']) == ('Acme', None, 2)

    # Deleting a company keeps its contacts.
    assert (await ada.delete(f'{base}/companies/{acme["id"]}')).status_code == 204
    assert (await ada.get(f'{base}/contacts/{carl["id"]}')).json()['company'] is None
    assert (await ada.delete(f'{base}/contacts/{dora["id"]}')).status_code == 204
    assert (await ada.get(f'{base}/contacts/{dora["id"]}')).json()['error'] == 'contact_not_found'

    log = {entry['action'] for entry in (await ada.get(f'{base}/audit-log')).json()['items']}
    assert {'contact.created', 'contact.updated', 'contact.deleted', 'company.created', 'company.deleted'} <= log


@pytest.mark.parametrize(
    ('path', 'body', 'error'),
    [
        ('contacts', {'email': 'nope'}, ('invalid_contact', 'email')),
        ('contacts', {'phone': 'call me'}, ('invalid_contact', 'phone')),
        ('contacts', {'name': ' '}, ('invalid_contact', 'name')),
        ('contacts', {'email': 'taken@example.org'}, ('contact_email_taken', None)),
        ('contacts', {'name': 'X', 'company_id': '0196f3c0-0000-7000-8000-000000000009'}, ('company_not_found', None)),
        ('companies', {'name': 'Taken'}, ('company_name_taken', None)),
        ('companies', {'name': 'Y', 'domain': 'taken.example'}, ('company_domain_taken', None)),
        ('companies', {'name': 'Z', 'domain': 'not a domain'}, ('invalid_company', 'domain')),
        ('companies', {'name': ' '}, ('invalid_company', 'name')),
    ],
)
async def test_checks_customers(
    app: AppUnderTest, path: str, body: dict[str, str], error: tuple[str, str | None]
) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    await posted(ada, f'{base}/contacts', email='taken@example.org')
    await posted(ada, f'{base}/companies', name='Taken', domain='taken.example')

    answer = (await ada.post(f'{base}/{path}', json=body)).json()

    assert (answer['error'], answer.get('params', {}).get('field')) == error


async def test_contacts_with_tickets_stay_and_strangers_see_nothing(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    created = await ticket(ada, tenant, await queue(ada, tenant))
    contact_id = created['customer']['id']

    refused = (await ada.delete(f'{base}/contacts/{contact_id}')).json()
    assert (refused['error'], refused['params']) == ('contact_has_tickets', {'count': 1})
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.patch(f'{base}/contacts/{missing}', json={'name': 'X'})).json()['error'] == 'contact_not_found'
    assert (await ada.delete(f'{base}/contacts/{missing}')).json()['error'] == 'contact_not_found'
    assert (await ada.patch(f'{base}/companies/{missing}', json={'name': 'X'})).json()['error'] == 'company_not_found'
    assert (await ada.delete(f'{base}/companies/{missing}')).json()['error'] == 'company_not_found'
    assert (await ada.get(f'{base}/companies/{missing}')).json()['error'] == 'company_not_found'

    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await agent.get(f'{base}/contacts')).status_code == 200
    stranger = await logged_in(app, 'eve@example.org')
    assert (await stranger.get(f'{base}/contacts')).status_code == 404


async def test_customers_go_with_their_organization(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    await posted(ada, f'{base}/companies', name='Acme', domain='acme.example')
    await posted(ada, f'{base}/contacts', email='carl@acme.example')

    assert (await ada.delete(base)).status_code == 204

    async with app.app.context.db.connection() as connection:
        row = await (await connection.execute('SELECT count(*) AS n FROM contacts')).fetchone()
    assert row is not None
    assert row['n'] == 0
