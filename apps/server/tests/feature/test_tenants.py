from support.app import AppUnderTest
from support.identity import PASSWORD, logged_in, make_admin
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of


async def test_creates_an_organization_with_the_creator_as_owner(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')

    response = await ada.post(TENANTS, json={'name': '  Acme   GmbH ', 'timezone': 'Europe/Vienna', 'locale': 'en'})

    assert response.status_code == 201, response.text
    tenant = response.json()
    assert tenant['name'] == 'Acme GmbH'
    assert tenant['timezone'] == 'Europe/Vienna'
    assert tenant['locale'] == 'en'
    assert tenant['status'] == 'active'
    assert tenant['role'] == 'owner'
    assert 'tenant.delete' in tenant['permissions']
    assert [own['name'] for own in (await ada.get(TENANTS)).json()] == ['Acme GmbH']
    shown = (await ada.get(f'{TENANTS}/{tenant["id"]}')).json()
    assert shown['role'] == 'owner'
    members = (await ada.get(f'{TENANTS}/{tenant["id"]}/members')).json()
    assert [(member['email'], member['role']) for member in members] == [('ada@example.org', 'owner')]


async def test_lists_the_organizations_of_the_caller_only(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    bob = await logged_in(app, 'bob@example.org')
    await create_tenant(ada, 'Zeta AG')
    await create_tenant(ada, 'alpha GmbH')
    await create_tenant(bob, 'Bob KG')

    assert [own['name'] for own in (await ada.get(TENANTS)).json()] == ['alpha GmbH', 'Zeta AG']
    assert [own['name'] for own in (await bob.get(TENANTS)).json()] == ['Bob KG']


async def test_validates_the_organization(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')

    blank = await ada.post(TENANTS, json={'name': '   '})
    assert blank.status_code == 422
    assert blank.json()['error'] == 'invalid_tenant_name'
    zone = await ada.post(TENANTS, json={'name': 'Acme', 'timezone': 'Mars/Olympus'})
    assert zone.json()['error'] == 'invalid_timezone'
    assert (await ada.post(TENANTS, json={'name': 'Acme', 'locale': 'fr'})).status_code == 422


async def test_requires_a_login(app: AppUnderTest) -> None:
    assert (await app.client.get(TENANTS)).status_code == 401
    assert (await app.client.post(TENANTS, json={'name': 'Acme'})).status_code == 401
    assert (await app.client.get(f'{TENANTS}/00000000-0000-7000-8000-000000000001')).status_code == 401


async def test_hides_other_organizations_completely(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    mallory = await logged_in(app, 'mallory@example.org')
    tenant = await create_tenant(ada)
    ada_id = await user_id_of(ada)
    await create_tenant(mallory, 'Mallory Ltd')

    # Every tenant route answers like for an organization that does not exist.
    for method, path, body in [
        ('GET', '', None),
        ('PATCH', '', {'name': 'Hacked'}),
        ('DELETE', '', None),
        ('GET', '/members', None),
        ('PATCH', f'/members/{ada_id}', {'role': 'agent'}),
        ('DELETE', f'/members/{ada_id}', None),
        ('GET', '/invitations', None),
        ('POST', '/invitations', {'email': 'mallory2@example.org'}),
    ]:
        response = await mallory.request(method, f'{TENANTS}/{tenant}{path}', json=body)
        assert response.status_code == 404, f'{method} {path}: {response.text}'
        assert response.json()['error'] == 'tenant_not_found'

    assert (await ada.get(f'{TENANTS}/{tenant}')).json()['name'] == 'Acme GmbH'
    assert (await mallory.get(f'{TENANTS}/not-a-uuid')).status_code == 422


async def test_updates_the_organization(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)

    response = await ada.patch(f'{TENANTS}/{tenant}', json={'name': 'Acme AG', 'locale': 'en'})

    assert response.status_code == 200, response.text
    assert response.json()['name'] == 'Acme AG'
    assert response.json()['locale'] == 'en'
    assert response.json()['timezone'] == 'Europe/Berlin'
    zone = await ada.patch(f'{TENANTS}/{tenant}', json={'timezone': 'America/New_York'})
    assert zone.json()['timezone'] == 'America/New_York'


async def test_lets_each_role_do_only_what_it_may(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    agent = await member_of(app, tenant, ada, 'agent@example.org', 'agent')
    admin = await member_of(app, tenant, ada, 'admin@example.org', 'admin')

    denied = await agent.patch(f'{TENANTS}/{tenant}', json={'name': 'Mine now'})
    assert denied.status_code == 403
    assert denied.json() == {
        'error': 'permission_denied',
        'message': 'You may not do this',
        'params': {'permission': 'tenant.manage'},
    }
    assert (await agent.get(f'{TENANTS}/{tenant}/members')).status_code == 200
    assert (await agent.get(f'{TENANTS}/{tenant}/invitations')).status_code == 403
    assert (await agent.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'x@example.org'})).status_code == 403
    assert (await admin.patch(f'{TENANTS}/{tenant}', json={'name': 'Acme AG'})).status_code == 200
    assert (await admin.delete(f'{TENANTS}/{tenant}')).status_code == 403
    assert (await agent.get(f'{TENANTS}/{tenant}')).json()['permissions'] == [
        'members.view',
    ]


async def test_invites_people_by_e_mail(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)

    response = await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': ' Bob@Example.org ', 'role': 'manager'})

    assert response.status_code == 201, response.text
    assert response.json()['email'] == 'bob@example.org'
    assert response.json()['role'] == 'manager'
    mail = app.mailer.to('bob@example.org')[-1]
    assert mail.subject == 'Einladung zu Acme GmbH bei zendiloHUB'
    assert 'ada@example.org lädt dich ein, Acme GmbH bei zendiloHUB als Manager beizutreten' in mail.text
    invitations = (await ada.get(f'{TENANTS}/{tenant}/invitations')).json()
    assert [invitation['email'] for invitation in invitations] == ['bob@example.org']

    token = app.mailer.last_token('bob@example.org')
    preview = await app.client.post('/api/v1/invitations/preview', json={'token': token})
    assert preview.status_code == 200
    assert preview.json()['tenant_name'] == 'Acme GmbH'
    assert preview.json()['role'] == 'manager'

    bob = await logged_in(app, 'bob@example.org')
    accepted = await bob.post('/api/v1/invitations/accept', json={'token': token})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['role'] == 'manager'
    assert [own['name'] for own in (await bob.get(TENANTS)).json()] == ['Acme GmbH']
    assert (await ada.get(f'{TENANTS}/{tenant}/invitations')).json() == []
    # Used up.
    again = await bob.post('/api/v1/invitations/accept', json={'token': token})
    assert again.json()['error'] == 'invalid_invitation'


async def test_sends_invitations_in_the_language_of_the_organization(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada, locale='en')

    await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'bob@example.org', 'role': 'admin'})

    mail = app.mailer.to('bob@example.org')[-1]
    assert mail.subject == 'Join Acme GmbH on zendiloHUB'
    assert 'ada@example.org invites you to join Acme GmbH on zendiloHUB as administrator' in mail.text


async def test_accepts_invitations_only_with_the_invited_address(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'bob@example.org'})
    token = app.mailer.last_token('bob@example.org')
    eve = await logged_in(app, 'eve@example.org')

    response = await eve.post('/api/v1/invitations/accept', json={'token': token})

    assert response.status_code == 403
    assert response.json()['error'] == 'invitation_for_other_email'
    assert response.json()['params'] == {'email': 'bob@example.org'}
    assert (await eve.get(TENANTS)).json() == []
    assert (await app.client.post('/api/v1/invitations/accept', json={'token': token})).status_code == 401


async def test_rejects_unknown_and_expired_invitations(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'bob@example.org'})
    token = app.mailer.last_token('bob@example.org')
    bob = await logged_in(app, 'bob@example.org')

    unknown = await app.client.post('/api/v1/invitations/preview', json={'token': 'nope'})
    assert unknown.status_code == 422
    assert unknown.json()['error'] == 'invalid_invitation'
    app.clock.advance(days=8)
    assert (await app.client.post('/api/v1/invitations/preview', json={'token': token})).status_code == 422
    assert (await bob.post('/api/v1/invitations/accept', json={'token': token})).status_code == 422
    # Listing cleans up.
    assert (await ada.get(f'{TENANTS}/{tenant}/invitations')).json() == []


async def test_replaces_and_revokes_invitations(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'bob@example.org', 'role': 'agent'})
    first = app.mailer.last_token('bob@example.org')

    second = await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'bob@example.org', 'role': 'admin'})

    invitations = (await ada.get(f'{TENANTS}/{tenant}/invitations')).json()
    assert [(invitation['email'], invitation['role']) for invitation in invitations] == [('bob@example.org', 'admin')]
    assert (await app.client.post('/api/v1/invitations/preview', json={'token': first})).status_code == 422
    revoked = await ada.delete(f'{TENANTS}/{tenant}/invitations/{second.json()["id"]}')
    assert revoked.status_code == 204
    assert (await ada.get(f'{TENANTS}/{tenant}/invitations')).json() == []
    missing = await ada.delete(f'{TENANTS}/{tenant}/invitations/{second.json()["id"]}')
    assert missing.status_code == 404
    assert missing.json()['error'] == 'invitation_not_found'


async def test_does_not_invite_members_or_invalid_addresses(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)

    member = await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'ADA@example.org'})
    assert member.status_code == 409
    assert member.json()['error'] == 'already_member'
    invalid = await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'not an address'})
    assert invalid.status_code == 422
    assert invalid.json()['error'] == 'invalid_email'


async def test_limits_invitations_per_organization(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    for number in range(50):
        response = await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': f'person{number}@example.org'})
        assert response.status_code == 201

    limited = await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'one-more@example.org'})

    assert limited.status_code == 429
    assert limited.json()['error'] == 'too_many_requests'


async def test_joining_twice_keeps_one_membership(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = await user_id_of(bob)
    # Invited again under another address that is changed to Bob's later is impossible; but an invitation sent
    # before Bob joined (a second one to the same address is replaced), accepted after, must not duplicate.
    await ada.delete(f'{TENANTS}/{tenant}/members/{bob_id}')
    await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'bob@example.org', 'role': 'agent'})
    token = app.mailer.last_token('bob@example.org')
    await bob.post('/api/v1/invitations/accept', json={'token': token})

    members = (await ada.get(f'{TENANTS}/{tenant}/members')).json()
    assert [member['email'] for member in members] == ['ada@example.org', 'bob@example.org']


async def test_only_owners_make_owners(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    ada_id = await user_id_of(ada)
    admin = await member_of(app, tenant, ada, 'admin@example.org', 'admin')
    agent = await member_of(app, tenant, ada, 'agent@example.org', 'agent')
    agent_id = await user_id_of(agent)

    to_owner = await admin.patch(f'{TENANTS}/{tenant}/members/{agent_id}', json={'role': 'owner'})
    assert to_owner.status_code == 403
    assert to_owner.json()['params'] == {'permission': 'members.assign_owner'}
    demote_owner = await admin.patch(f'{TENANTS}/{tenant}/members/{ada_id}', json={'role': 'agent'})
    assert demote_owner.status_code == 403
    invite_owner = await admin.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'x@example.org', 'role': 'owner'})
    assert invite_owner.status_code == 403
    assert (await admin.delete(f'{TENANTS}/{tenant}/members/{ada_id}')).status_code == 403

    promoted = await admin.patch(f'{TENANTS}/{tenant}/members/{agent_id}', json={'role': 'manager'})
    assert promoted.status_code == 200
    assert promoted.json()['role'] == 'manager'
    owner = await ada.patch(f'{TENANTS}/{tenant}/members/{agent_id}', json={'role': 'owner'})
    assert owner.json()['role'] == 'owner'


async def test_keeps_at_least_one_owner(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    ada_id = await user_id_of(ada)

    demoted = await ada.patch(f'{TENANTS}/{tenant}/members/{ada_id}', json={'role': 'admin'})
    assert demoted.status_code == 409
    assert demoted.json()['error'] == 'last_owner'
    left = await ada.delete(f'{TENANTS}/{tenant}/members/{ada_id}')
    assert left.status_code == 409

    bob = await member_of(app, tenant, ada, 'bob@example.org', 'owner')
    assert (await ada.patch(f'{TENANTS}/{tenant}/members/{ada_id}', json={'role': 'admin'})).status_code == 200
    assert (await bob.get(f'{TENANTS}/{tenant}')).json()['role'] == 'owner'


async def test_removes_members_and_lets_members_leave(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    carol = await member_of(app, tenant, ada, 'carol@example.org', 'agent')
    bob_id = await user_id_of(bob)
    carol_id = await user_id_of(carol)

    assert (await bob.delete(f'{TENANTS}/{tenant}/members/{carol_id}')).status_code == 403
    assert (await bob.delete(f'{TENANTS}/{tenant}/members/{bob_id}')).status_code == 204
    assert (await bob.get(f'{TENANTS}/{tenant}')).status_code == 404
    assert (await ada.delete(f'{TENANTS}/{tenant}/members/{carol_id}')).status_code == 204
    gone = await ada.delete(f'{TENANTS}/{tenant}/members/{carol_id}')
    assert gone.status_code == 404
    assert gone.json()['error'] == 'member_not_found'
    unknown = await ada.patch(f'{TENANTS}/{tenant}/members/{carol_id}', json={'role': 'admin'})
    assert unknown.status_code == 404
    assert [member['email'] for member in (await ada.get(f'{TENANTS}/{tenant}/members')).json()] == ['ada@example.org']


async def test_owners_delete_the_organization(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)

    assert (await ada.delete(f'{TENANTS}/{tenant}')).status_code == 204

    assert (await ada.get(f'{TENANTS}/{tenant}')).status_code == 404
    assert (await ada.get(TENANTS)).json() == []


async def test_shows_the_role_matrix(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')

    matrix = (await ada.get('/api/v1/roles')).json()

    assert matrix['roles'] == ['owner', 'admin', 'manager', 'agent']
    assert matrix['permissions']['tenant.delete'] == ['owner']
    assert matrix['permissions']['audit.view'] == ['owner', 'admin']
    assert (await app.client.get('/api/v1/roles')).status_code == 401


async def test_platform_administrators_suspend_organizations(app: AppUnderTest) -> None:
    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    await create_tenant(ada, 'Other GmbH')

    page = (await root.get('/api/v1/admin/tenants')).json()
    assert page['total'] == 2
    assert [(item['name'], item['member_count']) for item in page['items']] == [('Other GmbH', 1), ('Acme GmbH', 1)]
    found = (await root.get('/api/v1/admin/tenants', params={'q': 'acme'})).json()
    assert [item['name'] for item in found['items']] == ['Acme GmbH']
    beyond = (await root.get('/api/v1/admin/tenants', params={'offset': 10})).json()
    assert beyond == {'items': [], 'total': 2}

    suspended = await root.patch(f'/api/v1/admin/tenants/{tenant}', json={'status': 'suspended'})
    assert suspended.status_code == 200
    assert suspended.json()['status'] == 'suspended'
    assert (await ada.get(f'{TENANTS}/{tenant}')).status_code == 404
    assert [own['status'] for own in (await ada.get(TENANTS)).json()] == ['suspended', 'active']

    await root.patch(f'/api/v1/admin/tenants/{tenant}', json={'status': 'active'})
    assert (await ada.get(f'{TENANTS}/{tenant}')).status_code == 200
    missing = await root.patch('/api/v1/admin/tenants/00000000-0000-7000-8000-00000000ffff', json={'status': 'active'})
    assert missing.status_code == 404
    assert (await ada.get('/api/v1/admin/tenants')).status_code == 403


async def test_invitations_to_suspended_organizations_cannot_be_used(app: AppUnderTest) -> None:
    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    await ada.post(f'{TENANTS}/{tenant}/invitations', json={'email': 'bob@example.org'})
    token = app.mailer.last_token('bob@example.org')
    bob = await logged_in(app, 'bob@example.org')

    await root.patch(f'/api/v1/admin/tenants/{tenant}', json={'status': 'suspended'})

    assert (await app.client.post('/api/v1/invitations/preview', json={'token': token})).status_code == 422
    assert (await bob.post('/api/v1/invitations/accept', json={'token': token})).status_code == 422


async def test_a_deleted_account_leaves_its_organizations(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    alone = await create_tenant(ada, 'Only Ada')
    shared = await create_tenant(ada, 'Shared')
    await member_of(app, shared, ada, 'agent@example.org', 'agent')
    manager = await member_of(app, shared, ada, 'manager@example.org', 'manager')

    response = await ada.post('/api/v1/account/delete', json={'password': PASSWORD})

    assert response.status_code == 204, response.text
    # The organization Ada was alone in is gone; in the other one, the most senior member took over.
    assert [own['name'] for own in (await manager.get(TENANTS)).json()] == ['Shared']
    members = (await manager.get(f'{TENANTS}/{shared}/members')).json()
    assert sorted((member['email'], member['role']) for member in members) == [
        ('agent@example.org', 'agent'),
        ('manager@example.org', 'owner'),
    ]
    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')
    names = [item['name'] for item in (await root.get('/api/v1/admin/tenants')).json()['items']]
    assert names == ['Shared']
    assert alone not in names
