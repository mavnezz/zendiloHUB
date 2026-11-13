from .core.module import ModuleFactory
from .modules.compliance.compliance_module import create_compliance_module
from .modules.identity.identity_module import create_identity_module
from .modules.tenancy.tenancy_module import create_tenancy_module

# All modules, in boot order (like Laravel's bootstrap/providers.php).
providers: list[ModuleFactory] = [
    create_identity_module,
    create_tenancy_module,
    create_compliance_module,
]
