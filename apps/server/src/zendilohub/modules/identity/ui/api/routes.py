from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.config import AppConfig
from zendilohub.core.http.access import SESSION_COOKIE, CurrentAdmin, CurrentUser, OptionalUser, Public
from zendilohub.core.http.audit import Unaudited, audited, note_audit, path_param
from zendilohub.core.http.ids import Id

from ...application.commands.change_password import ChangePassword
from ...application.commands.change_role import ChangeRole
from ...application.commands.complete_setup import CompleteSetup
from ...application.commands.confirm_registration import ConfirmRegistration
from ...application.commands.delete_account import DeleteAccount, DeleteUser
from ...application.commands.login import Login
from ...application.commands.logout import Logout
from ...application.commands.register import Register
from ...application.commands.request_password_reset import RequestPasswordReset
from ...application.commands.resend_confirmation import ResendConfirmation
from ...application.commands.reset_password import ResetPassword
from ...application.commands.two_factor import (
    BeginTwoFactorSetup,
    CompleteTwoFactorLogin,
    DisableTwoFactor,
    EnableTwoFactor,
    GetTwoFactorStatus,
    RegenerateRecoveryCodes,
    ResetTwoFactor,
)
from ...application.commands.update_account import UpdateAccount
from ...application.queries.setup_status import GetSetupStatus
from ...application.queries.users import GetUser, SearchUsers
from ...application.services.session_starter import LoginResult
from .schemas import (
    ChangePasswordRequest,
    CredentialsRequest,
    EmailRequest,
    PasswordRequest,
    RecoveryCodesResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionResponse,
    SetupRequest,
    SetupStatusResponse,
    TokenRequest,
    TwoFactorCodeRequest,
    TwoFactorLoginRequest,
    TwoFactorSetupResponse,
    TwoFactorStatusResponse,
    UpdateAccountRequest,
    UpdateUserRequest,
    UserPageResponse,
    UserResponse,
)


def _client(request: Request) -> str:
    # The real address behind the reverse proxy: uvicorn applies X-Forwarded-For from trusted proxies.
    return request.client.host if request.client else 'unknown'


def _log_in(request: Request, response: Response, result: LoginResult) -> SessionResponse:
    if result.session is None:
        # Two-factor login: no cookie before the code.
        return SessionResponse(user=None, challenge=result.challenge)
    response.set_cookie(
        SESSION_COOKIE,
        result.session.token,
        expires=result.session.expires_at,
        path='/',
        httponly=True,
        samesite='lax',
        secure=request.url.scheme == 'https',
    )
    return SessionResponse(user=UserResponse.of(result.user))


def _log_out(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='lax')


def auth_routes(bus: CommandBus, config: AppConfig) -> APIRouter:
    router = APIRouter(prefix='/auth', tags=['auth'], dependencies=[Public])

    def link_base(request: Request) -> str:
        return config.public_url or str(request.base_url).rstrip('/')

    @router.get('/session')
    async def session(principal: OptionalUser) -> SessionResponse:
        """The logged-in user, or null."""
        if principal is None:
            return SessionResponse(user=None)
        return SessionResponse(user=UserResponse.of(await bus.query(GetUser(principal.user_id))))

    @router.post('/register', status_code=204, response_class=Response, dependencies=[Unaudited])
    async def register(body: RegisterRequest, request: Request) -> None:
        """Sends a confirmation link; answers the same whether the address already has an account or not."""
        await bus.execute(
            Register(
                email=body.email,
                password=body.password,
                locale=body.locale,
                client=_client(request),
                link_base=link_base(request),
            )
        )

    @router.post('/confirm', dependencies=[audited('auth.registration_confirmed')])
    async def confirm(body: TokenRequest, request: Request, response: Response) -> SessionResponse:
        """Confirms a sign-up (the token from the e-mail), creates the account and logs in."""
        result = await bus.execute(ConfirmRegistration(body.token))
        note_audit(request, actor_id=result.user.id, actor_email=result.user.email)
        return _log_in(request, response, result)

    @router.post('/resend-confirmation', status_code=204, response_class=Response, dependencies=[Unaudited])
    async def resend(body: CredentialsRequest, request: Request) -> None:
        await bus.execute(
            ResendConfirmation(
                email=body.email, password=body.password, client=_client(request), link_base=link_base(request)
            )
        )

    @router.post('/login', dependencies=[audited('auth.login')])
    async def login(body: CredentialsRequest, request: Request, response: Response) -> SessionResponse:
        # Also failed attempts name the address they tried.
        note_audit(request, actor_email=body.email.strip().lower()[:254])
        result = await bus.execute(Login(email=body.email, password=body.password, client=_client(request)))
        note_audit(request, actor_id=result.user.id)
        return _log_in(request, response, result)

    @router.post('/login/two-factor', dependencies=[audited('auth.login_two_factor')])
    async def login_two_factor(body: TwoFactorLoginRequest, request: Request, response: Response) -> SessionResponse:
        """The second step of a two-factor login: the challenge from /auth/login and a code."""
        result = await bus.execute(CompleteTwoFactorLogin(challenge=body.challenge, code=body.code))
        note_audit(request, actor_id=result.user.id, actor_email=result.user.email)
        return _log_in(request, response, result)

    @router.post('/logout', status_code=204, response_class=Response, dependencies=[audited('auth.logout')])
    async def logout(request: Request, response: Response, _principal: OptionalUser) -> None:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            await bus.execute(Logout(token))
        _log_out(response)

    @router.post('/forgot-password', status_code=204, response_class=Response, dependencies=[Unaudited])
    async def forgot_password(body: EmailRequest, request: Request) -> None:
        """Sends a reset link if the address has an account; answers the same either way."""
        await bus.execute(RequestPasswordReset(email=body.email, client=_client(request), link_base=link_base(request)))

    @router.post('/reset-password', dependencies=[audited('auth.password_reset')])
    async def reset_password(body: ResetPasswordRequest, request: Request, response: Response) -> SessionResponse:
        """Sets a new password (the token from the e-mail), ends all sessions and logs in."""
        result = await bus.execute(ResetPassword(body.token, body.password))
        note_audit(request, actor_id=result.user.id, actor_email=result.user.email)
        return _log_in(request, response, result)

    return router


def setup_routes(bus: CommandBus, config: AppConfig) -> APIRouter:
    router = APIRouter(prefix='/setup', tags=['setup'], dependencies=[Public])

    @router.get('', dependencies=[Unaudited])
    async def status() -> SetupStatusResponse:
        """Whether the setup wizard is open (a self-hosted instance without an administrator)."""
        return SetupStatusResponse(open=await bus.query(GetSetupStatus()), self_hosted=not config.multi_tenant)

    @router.post('', dependencies=[audited('setup.completed')])
    async def complete(body: SetupRequest, request: Request, response: Response) -> SessionResponse:
        """Creates the first administrator and the organization, then logs in. Needs the code from the server log."""
        result = await bus.execute(
            CompleteSetup(
                token=body.token,
                email=body.email,
                password=body.password,
                organization_name=body.organization_name,
                timezone=body.timezone,
                locale=body.locale,
            )
        )
        note_audit(request, actor_id=result.user.id, actor_email=result.user.email)
        return _log_in(request, response, result)

    return router


def account_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/account', tags=['account'])

    @router.get('')
    async def show(principal: CurrentUser) -> UserResponse:
        return UserResponse.of(await bus.query(GetUser(principal.user_id)))

    @router.patch('', dependencies=[audited('account.updated')])
    async def update(body: UpdateAccountRequest, principal: CurrentUser) -> UserResponse:
        return UserResponse.of(await bus.execute(UpdateAccount(user_id=principal.user_id, locale=body.locale)))

    @router.post(
        '/password', status_code=204, response_class=Response, dependencies=[audited('account.password_changed')]
    )
    async def change_password(body: ChangePasswordRequest, principal: CurrentUser) -> None:
        """Changes the password; other sessions are logged out."""
        await bus.execute(
            ChangePassword(
                user_id=principal.user_id,
                session_id=principal.session_id,
                current_password=body.current_password,
                new_password=body.new_password,
            )
        )

    @router.get('/two-factor')
    async def two_factor(principal: CurrentUser) -> TwoFactorStatusResponse:
        status = await bus.query(GetTwoFactorStatus(principal.user_id))
        return TwoFactorStatusResponse(enabled=status.enabled, recovery_codes_left=status.recovery_codes_left)

    @router.post('/two-factor/setup', dependencies=[audited('account.two_factor_setup_started')])
    async def two_factor_setup(body: PasswordRequest, principal: CurrentUser) -> TwoFactorSetupResponse:
        """A new secret for the authenticator app; two-factor login is on once a code confirms it."""
        setup = await bus.execute(BeginTwoFactorSetup(user_id=principal.user_id, password=body.password))
        return TwoFactorSetupResponse(secret=setup.secret, uri=setup.uri)

    @router.post('/two-factor/enable', dependencies=[audited('account.two_factor_enabled')])
    async def two_factor_enable(body: TwoFactorCodeRequest, principal: CurrentUser) -> RecoveryCodesResponse:
        """Turns two-factor login on; other sessions are logged out. The recovery codes are shown only now."""
        codes = await bus.execute(
            EnableTwoFactor(user_id=principal.user_id, session_id=principal.session_id, code=body.code)
        )
        return RecoveryCodesResponse(recovery_codes=list(codes))

    @router.post('/two-factor/recovery-codes', dependencies=[audited('account.recovery_codes_renewed')])
    async def recovery_codes(body: PasswordRequest, principal: CurrentUser) -> RecoveryCodesResponse:
        """New recovery codes; the old ones stop working."""
        codes = await bus.execute(RegenerateRecoveryCodes(user_id=principal.user_id, password=body.password))
        return RecoveryCodesResponse(recovery_codes=list(codes))

    @router.post(
        '/two-factor/disable',
        status_code=204,
        response_class=Response,
        dependencies=[audited('account.two_factor_disabled')],
    )
    async def two_factor_disable(body: PasswordRequest, principal: CurrentUser) -> None:
        await bus.execute(DisableTwoFactor(user_id=principal.user_id, password=body.password))

    @router.post('/delete', status_code=204, response_class=Response, dependencies=[audited('account.deleted')])
    async def delete(body: PasswordRequest, request: Request, principal: CurrentUser, response: Response) -> None:
        """Deletes the account and all its data."""
        await bus.execute(DeleteAccount(user_id=principal.user_id, password=body.password))
        # The account is gone: its address must not come back through this very entry.
        note_audit(request, forget_actor_email=True)
        _log_out(response)

    return router


def admin_user_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/admin/users', tags=['admin'])

    @router.get('')
    async def index(
        _admin: CurrentAdmin,
        q: Annotated[str, Query(max_length=254)] = '',
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        ids: Annotated[list[Id] | None, Query(max_length=200)] = None,
    ) -> UserPageResponse:
        """Users, newest first; `q` searches the addresses, `ids` picks certain users."""
        query = SearchUsers(query=q, offset=offset, limit=limit, ids=tuple(ids or ()))
        return UserPageResponse.of(await bus.query(query))

    @router.patch('/{user_id}', dependencies=[audited('admin.user_role_changed', target=path_param('user_id'))])
    async def update(user_id: Id, body: UpdateUserRequest, admin: CurrentAdmin) -> UserResponse:
        return UserResponse.of(await bus.execute(ChangeRole(actor_id=admin.user_id, user_id=user_id, role=body.role)))

    @router.delete(
        '/{user_id}/two-factor',
        status_code=204,
        response_class=Response,
        dependencies=[audited('admin.user_two_factor_reset', target=path_param('user_id'))],
    )
    async def reset_two_factor(user_id: Id, admin: CurrentAdmin) -> None:
        """Turns off the two-factor login of someone who lost the phone and the recovery codes."""
        await bus.execute(ResetTwoFactor(actor_id=admin.user_id, user_id=user_id))

    @router.delete(
        '/{user_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('admin.user_deleted', target=path_param('user_id'))],
    )
    async def destroy(user_id: Id, admin: CurrentAdmin) -> None:
        await bus.execute(DeleteUser(actor_id=admin.user_id, user_id=user_id))

    return router
