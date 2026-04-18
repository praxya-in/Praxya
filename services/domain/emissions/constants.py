"""
Re-export module for regulatory constants.

The canonical definitions live in ghg_calculator.py (alongside the calculation
methods that use them). This module re-exports them so that downstream code
can import from a dedicated constants module:

    from services.domain.emissions.constants import CEA_GRID_FACTOR_TCO2_PER_MWH
"""

from services.domain.emissions.ghg_calculator import (
    CEA_GRID_FACTOR_TCO2_PER_MWH,
    COAL_EF_TCO2_PER_GJ,
    DIESEL_CONSTANTS,
    BENCHMARK_SEC_GJ_PER_TONNE,
)

__all__ = [
    "CEA_GRID_FACTOR_TCO2_PER_MWH",
    "COAL_EF_TCO2_PER_GJ",
    "DIESEL_CONSTANTS",
    "BENCHMARK_SEC_GJ_PER_TONNE",
]
