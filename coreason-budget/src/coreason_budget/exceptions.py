class BudgetError(Exception):
    """Base exception for budget-related errors."""
    pass

class BudgetExceededError(BudgetError):
    """Raised when a budget limit is exceeded."""
    pass
