"""
agents package — exposes each agent's single entry point.

Phase 5's demo imports run_finance_agent / run_procurement_agent from
here rather than reaching into each agent module's internals.
"""
from .finance_agent import run_finance_agent  # noqa: F401
from .procurement_agent import run_procurement_agent  # noqa: F401
from .corporate_agent import run_corporate_agent  # noqa: F401
from .it_agent import run_it_agent  # noqa: F401
