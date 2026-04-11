from pydantic import BaseModel, Field
from typing import Literal, Optional
from decimal import Decimal


class EmissionFactor(BaseModel):
    id: str
    process_id: str
    factor_value: Decimal
    unit: str
    source: str
    confidence: Literal['HIGH', 'MEDIUM', 'LOW']
    factor_type: Literal['direct_ghg', 'energy_intensity'] = 'direct_ghg'
    # direct_ghg   → unit is tCO2e/tonne_product → use in calculate_scope1_process
    # energy_intensity → unit is GJ/tonne_product → use in calculate_from_sec_benchmark


class Scope1ProcessInput(BaseModel):
    production_volume_tonnes: Decimal = Field(gt=0)
    emission_factor: EmissionFactor


class Scope1CombustionInput(BaseModel):
    fuel_type: Literal['diesel', 'petrol', 'lpg', 'png', 'furnace_oil']
    fuel_consumed_litres: Decimal = Field(gt=0)


class Scope2Input(BaseModel):
    kwh_consumed: Decimal = Field(gt=0)


class EmissionResult(BaseModel):
    value_tco2e: Decimal
    scope: Literal['scope1_process', 'scope1_combustion', 'scope2']
    calculation_method: str
    requires_human_review: bool
    factor_id: Optional[str] = None


class KPI3EnergyResult(BaseModel):
    total_energy_GJ: Decimal
    energy_intensity_GJ_per_tonne: Optional[Decimal] = None
    calculation_method: str
