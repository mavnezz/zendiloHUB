from .core.module import ModuleFactory
from .modules.access.access_module import create_access_module
from .modules.automation.automation_module import create_automation_module
from .modules.channels.channels_module import create_channels_module
from .modules.compliance.compliance_module import create_compliance_module
from .modules.customers.customers_module import create_customers_module
from .modules.identity.identity_module import create_identity_module
from .modules.integrations.integrations_module import create_integrations_module
from .modules.knowledge.knowledge_module import create_knowledge_module
from .modules.notifications.notifications_module import create_notifications_module
from .modules.reporting.reporting_module import create_reporting_module
from .modules.service.service_module import create_service_module
from .modules.tenancy.tenancy_module import create_tenancy_module
from .modules.tickets.tickets_module import create_tickets_module

# All modules, in boot order (like Laravel's bootstrap/providers.php).
providers: list[ModuleFactory] = [
    create_identity_module,
    create_tenancy_module,
    create_access_module,
    create_customers_module,
    create_tickets_module,
    create_channels_module,
    create_automation_module,
    create_knowledge_module,
    create_service_module,
    create_notifications_module,
    create_integrations_module,
    create_reporting_module,
    create_compliance_module,
]
