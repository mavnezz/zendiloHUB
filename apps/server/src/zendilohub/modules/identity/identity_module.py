import logging
from pathlib import Path

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.module import AppModule, ModuleContext

from .application.commands.change_password import ChangePassword, ChangePasswordHandler
from .application.commands.change_role import ChangeRole, ChangeRoleHandler, MakeAdmin, MakeAdminHandler
from .application.commands.complete_setup import CompleteSetup, CompleteSetupHandler
from .application.commands.confirm_registration import ConfirmRegistration, ConfirmRegistrationHandler
from .application.commands.create_initial_admin import CreateInitialAdmin, CreateInitialAdminHandler
from .application.commands.delete_account import (
    AccountRemover,
    DeleteAccount,
    DeleteAccountHandler,
    DeleteUser,
    DeleteUserHandler,
)
from .application.commands.login import Login, LoginHandler
from .application.commands.logout import Logout, LogoutHandler
from .application.commands.register import Register, RegisterHandler
from .application.commands.request_password_reset import RequestPasswordReset, RequestPasswordResetHandler
from .application.commands.resend_confirmation import ResendConfirmation, ResendConfirmationHandler
from .application.commands.reset_password import ResetPassword, ResetPasswordHandler
from .application.commands.update_account import UpdateAccount, UpdateAccountHandler
from .application.queries.authenticate_session import AuthenticateSession, AuthenticateSessionHandler
from .application.queries.setup_status import GetSetupStatus, GetSetupStatusHandler
from .application.queries.users import GetUser, GetUserHandler, SearchUsers, SearchUsersHandler
from .application.services.session_starter import SessionStarter
from .domain.ports.password_hasher import PasswordHasher
from .infrastructure.mail_notifier import MailAccountNotifier
from .infrastructure.postgres_users import (
    PostgresPasswordResetRepository,
    PostgresRegistrationRepository,
    PostgresSessionRepository,
    PostgresUserRepository,
)
from .infrastructure.security import Argon2PasswordHasher, SessionAuthGuard, Sha256TokenService
from .infrastructure.setup_token import FileSetupTokens
from .infrastructure.sign_up_policies import InvitedOnly, OpenSignUp
from .ui.api.routes import account_routes, admin_user_routes, auth_routes, setup_routes
from .ui.cli.make_admin import MakeAdminCommand

MIGRATIONS = Path(__file__).parent / 'infrastructure' / 'migrations'

logger = logging.getLogger(__name__)


def create_identity_module(context: ModuleContext, *, hasher: PasswordHasher | None = None) -> AppModule:
    """
    Accounts: the setup wizard of a self-hosted instance, sign-up with e-mail confirmation (self-hosted: invited
    people only), login sessions, password reset, roles, account deletion.
    """
    db, clock, ids, events, limiter = context.db, context.clock, context.ids, context.events, context.rate_limiter
    users = PostgresUserRepository(db)
    sessions = PostgresSessionRepository(db)
    registrations = PostgresRegistrationRepository(db)
    resets = PostgresPasswordResetRepository(db)
    hasher = hasher or Argon2PasswordHasher()
    tokens = Sha256TokenService()
    notifier = MailAccountNotifier(context.mailer)
    starter = SessionStarter(sessions, tokens, clock)
    remover = AccountRemover(users, db, events)
    self_hosted = not context.config.multi_tenant
    setup_tokens = FileSetupTokens(context.config.data_dir)
    policy = InvitedOnly(context.contracts) if self_hosted else OpenSignUp()

    bus = (
        CommandBus()
        .register(Register, RegisterHandler(users, registrations, hasher, tokens, notifier, limiter, clock, policy))
        .register(
            ConfirmRegistration,
            ConfirmRegistrationHandler(users, registrations, tokens, starter, db, events, ids, clock),
        )
        .register(
            ResendConfirmation,
            ResendConfirmationHandler(users, registrations, hasher, tokens, notifier, limiter, clock),
        )
        .register(Login, LoginHandler(users, registrations, hasher, starter, limiter, clock))
        .register(Logout, LogoutHandler(sessions, tokens))
        .register(RequestPasswordReset, RequestPasswordResetHandler(users, resets, tokens, notifier, limiter, clock))
        .register(ResetPassword, ResetPasswordHandler(users, resets, sessions, hasher, tokens, starter, db, clock))
        .register(ChangePassword, ChangePasswordHandler(users, sessions, hasher, clock))
        .register(UpdateAccount, UpdateAccountHandler(users, clock))
        .register(DeleteAccount, DeleteAccountHandler(users, hasher, remover))
        .register(DeleteUser, DeleteUserHandler(users, remover))
        .register(ChangeRole, ChangeRoleHandler(users, clock))
        .register(MakeAdmin, MakeAdminHandler(users, clock))
        .register(CreateInitialAdmin, CreateInitialAdminHandler(users, hasher, db, events, ids, clock))
        .register(
            CompleteSetup,
            CompleteSetupHandler(users, hasher, setup_tokens, starter, db, events, ids, clock, self_hosted=self_hosted),
        )
        .register(GetSetupStatus, GetSetupStatusHandler(users, self_hosted=self_hosted))
        .register(AuthenticateSession, AuthenticateSessionHandler(users, sessions, tokens, clock))
        .register(GetUser, GetUserHandler(users))
        .register(SearchUsers, SearchUsersHandler(users))
    )
    context.http.use_auth_guard(SessionAuthGuard(bus))

    async def boot() -> None:
        # Only the app: the workers and CLI commands start with the same environment.
        if context.role != 'web':
            return
        admin = context.config.initial_admin
        if admin is None:
            if await bus.query(GetSetupStatus()):
                logger.warning(
                    'zendiloHUB is not set up yet: open it in the browser and enter the setup code %s',
                    setup_tokens.issue(),
                )
            return
        outcome = await bus.execute(CreateInitialAdmin(admin.email, admin.password))
        if outcome == 'created':
            logger.info('Created the administrator from ZENDILOHUB_ADMIN_EMAIL', extra={'email': admin.email})
        elif outcome == 'promoted':
            logger.info(
                'Made the existing account of ZENDILOHUB_ADMIN_EMAIL an administrator; its password is unchanged',
                extra={'email': admin.email},
            )

    return AppModule(
        name='identity',
        migrations=sql_migrations(MIGRATIONS),
        routers=[
            auth_routes(bus, context.config),
            setup_routes(bus, context.config),
            account_routes(bus),
            admin_user_routes(bus),
        ],
        commands={'make-admin': MakeAdminCommand(bus)},
        boot=boot,
    )
