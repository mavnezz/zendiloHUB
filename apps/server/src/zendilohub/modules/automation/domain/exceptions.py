from zendilohub.core.domain.app_domain_error import NotFoundError, ValidationError


class InvalidRuleError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_rule', f'Please check the rule ({field})', {'field': field})


class RuleNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('rule_not_found', 'The macro, trigger or job does not exist')
