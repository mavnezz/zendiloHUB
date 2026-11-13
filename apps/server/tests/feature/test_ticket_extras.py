from support.app import AppUnderTest
from support.helpdesk import grant, posted, queue, ticket
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of


async def test_own_fields_on_tickets(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)

    product = await posted(
        ada,
        f'{base}/ticket-fields',
        key='product',
        label=' Product ',
        kind='select',
        options=['Printer', 'Scanner', ''],
    )
    assert (product['label'], product['options'], product['position']) == ('Product', ['Printer', 'Scanner'], 1)
    await posted(ada, f'{base}/ticket-fields', key='warranty', label='Warranty', kind='checkbox')
    await posted(ada, f'{base}/ticket-fields', key='bought', label='Bought on', kind='date')
    await posted(ada, f'{base}/ticket-fields', key='amount', label='Amount', kind='number')
    await posted(ada, f'{base}/ticket-fields', key='contract', label='Contract')
    assert [each['key'] for each in (await ada.get(f'{base}/ticket-fields')).json()] == [
        'product',
        'warranty',
        'bought',
        'amount',
        'contract',
    ]

    created = await ticket(ada, tenant, support)
    path = f'{base}/tickets/{created["id"]}'
    changed = await ada.patch(
        path,
        json={
            'fields': {
                'product': 'Printer',
                'warranty': True,
                'bought': '2026-01-31',
                'amount': 12,
                'contract': ' C-1 ',
            }
        },
    )
    assert changed.json()['fields'] == {
        'product': 'Printer',
        'warranty': True,
        'bought': '2026-01-31',
        'amount': 12.0,
        'contract': 'C-1',
    }
    assert (await ada.patch(path, json={'fields': {'contract': None}})).json()['fields'].get('contract') is None
    history = (await ada.get(f'{path}/history')).json()
    assert {'field': 'fields.product', 'old': None, 'new': 'Printer'}.items() <= next(
        entry for entry in history if entry['field'] == 'fields.product'
    ).items()

    for fields, key in [
        ({'product': 'Phone'}, 'product'),
        ({'warranty': 'yes'}, 'warranty'),
        ({'bought': 'tomorrow'}, 'bought'),
        ({'amount': True}, 'amount'),
        ({'nope': 'x'}, 'nope'),
        ({'contract': 'x' * 501}, 'contract'),
    ]:
        answer = (await ada.patch(path, json={'fields': fields})).json()
        assert (answer['error'], answer['params']) == ('invalid_field', {'field': key})

    renamed = await ada.patch(
        f'{base}/ticket-fields/{product["id"]}',
        json={'key': 'ignored', 'label': 'Device', 'kind': 'text', 'options': ['Printer']},
    )
    assert (renamed.json()['key'], renamed.json()['kind'], renamed.json()['label']) == ('product', 'select', 'Device')
    for body, error in [
        ({'key': 'product', 'label': 'Again'}, 'field_key_taken'),
        ({'key': 'Bad Key', 'label': 'X'}, 'invalid_field'),
        ({'key': 'choice', 'label': 'X', 'kind': 'select'}, 'invalid_field'),
        ({'key': 'empty', 'label': ' '}, 'invalid_field'),
    ]:
        assert (await ada.post(f'{base}/ticket-fields', json=body)).json()['error'] == error

    assert (await ada.delete(f'{base}/ticket-fields/{product["id"]}')).status_code == 204
    assert 'product' not in (await ada.get(path)).json()['fields']
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.delete(f'{base}/ticket-fields/{missing}')).json()['error'] == 'field_not_found'
    update = await ada.patch(f'{base}/ticket-fields/{missing}', json={'key': 'x', 'label': 'X'})
    assert update.json()['error'] == 'field_not_found'

    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await agent.get(f'{base}/ticket-fields')).status_code == 200
    assert (await agent.post(f'{base}/ticket-fields', json={'key': 'x', 'label': 'X'})).status_code == 403


async def test_checklists_and_who_looks_at_a_ticket(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id, ada_id = await user_id_of(bob), await user_id_of(ada)
    await grant(ada, tenant, support, [bob_id], ['view'])
    created = await ticket(ada, tenant, support)
    path = f'{base}/tickets/{created["id"]}'

    first = await posted(ada, f'{path}/checklist', text=' Check  toner ')
    second = await posted(ada, f'{path}/checklist', text='Order part')
    assert (first['text'], first['done'], second['position']) == ('Check toner', False, 2)
    done = await ada.patch(f'{path}/checklist/{first["id"]}', json={'done': True, 'text': 'Checked toner'})
    assert (done.json()['done'], done.json()['text']) == (True, 'Checked toner')
    assert (await ada.delete(f'{path}/checklist/{second["id"]}')).status_code == 204
    assert [each['text'] for each in (await bob.get(f'{path}/checklist')).json()] == ['Checked toner']
    assert (await bob.post(f'{path}/checklist', json={'text': 'X'})).json()['error'] == 'queue_right_missing'
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.patch(f'{path}/checklist/{missing}', json={'done': True})).json()['error'] == (
        'checklist_item_not_found'
    )
    assert (await ada.post(f'{path}/checklist', json={'text': ' '})).json()['error'] == 'invalid_field'

    assert (await ada.put(f'{path}/presence', json={})).json() == []
    assert (await bob.put(f'{path}/presence', json={'writing': True})).json() == [{'user_id': ada_id, 'writing': False}]
    assert (await ada.put(f'{path}/presence', json={})).json() == [{'user_id': bob_id, 'writing': True}]
    app.clock.advance(seconds=31)
    assert (await ada.put(f'{path}/presence', json={})).json() == []
