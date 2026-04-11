# services.domain.emissions package
from services.domain.emissions.ghg_calculator import GHGCalculator
from services.domain.emissions.models import (
    EmissionFactor,
    Scope1ProcessInput,
    Scope1CombustionInput,
    Scope2Input,
    EmissionResult,
    KPI3EnergyResult,
)
from services.domain.emissions.exceptions import (
    FactorNotFoundError,
    CalculationInputError,
)

__all__ = [
    "GHGCalculator",
    "EmissionFactor",
    "Scope1ProcessInput",
    "Scope1CombustionInput",
    "Scope2Input",
    "EmissionResult",
    "KPI3EnergyResult",
    "FactorNotFoundError",
    "CalculationInputError",
]
