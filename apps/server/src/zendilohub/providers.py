from .core.module import ModuleFactory
from .modules.access.access_module import create_access_module
from .modules.compliance.compliance_module import create_compliance_module
from .modules.customers.customers_module import create_customers_module
from .modules.identity.identity_module import create_identity_module
from .modules.tenancy.tenancy_module import create_tenancy_module
from .modules.tickets.tickets_module import create_tickets_module

# All modules, in boot order (like Laravel's bootstrap/providers.php).
providers: list[ModuleFactory] = [
    create_identity_module,
    create_tenancy_module,
    create_access_module,
    create_customers_module,
    create_tickets_module,
    create_compliance_module,
]
