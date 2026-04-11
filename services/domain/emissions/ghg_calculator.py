from decimal import Decimal
from typing import Optional, Literal
from services.domain.emissions.models import (
    Scope1ProcessInput, Scope1CombustionInput, Scope2Input,
    EmissionResult, KPI3EnergyResult
)
from services.domain.emissions.exceptions import FactorNotFoundError, CalculationInputError

# ── Module-level regulatory constants ─────────────────────────────────────────
# Do NOT make these configurable via env vars.
# They are regulatory constants with citable sources.
# Update process: file a new migration with updated value + source citation.

# CEA Grid Emission Factor — India FY2023-24
# Source: CEA/TPP/EE/2024 Table 2
# TODO: Update annually from https://cea.nic.in/grid-emission-factor/
CEA_GRID_FACTOR_TCO2_PER_MWH = Decimal("0.716")

# IPCC coal factor — Indian sub-bituminous coal
# Source: IPCC 2006 Guidelines Vol 2 Table 2.2 — 96,100 kgCO2/TJ = 0.0961 tCO2/GJ
# Confirmed by BRSR GHG Emission Factor Research Report, Section 5.3 (2025)
COAL_EF_TCO2_PER_GJ = Decimal("0.0961")

# ⚠ KNOWN GAP: N2O emissions from azo dye diazotization are NOT calculated here.
# GWP = 273 (IPCC AR6). N2O off-gassing during suboptimal diazotization is a real
# Scope 1 process emission but currently lacks a standardized IPCC quantification
# methodology for dye synthesis.
# Source: BRSR GHG Emission Factor Research Report, Section 2.1 (2025).
# Action required: engage ETAD or GDMA for a process-specific measurement protocol
# before any azo dye facility's BRSR report is submitted to SEBI.

# SEC plausibility benchmarks for ±30% deviation check (used by Prompt 6 API layer)
# Source: BEE/TERI Sectoral Roadmap for MSME Chemical Industries (2022)
#         DyStar Integrated Sustainability Report 2024-2025
BENCHMARK_SEC_GJ_PER_TONNE: dict = {
    'dyes_pigments_manufacturing_ankleshwar_average': Decimal('6.0'),
    'reactive_dye_manufacturing_corporate_average':   Decimal('9.67'),
    'dye_intermediate_manufacturing_ankleshwar_proxy': Decimal('16.0'),
}


# ── Diesel combustion constants ────────────────────────────────────────────────
DIESEL_CONSTANTS = {
    "density_kg_per_litre": Decimal("0.832"),
    "ncv_GJ_per_tonne":     Decimal("43.0"),
    "ef_tCO2_per_TJ":       Decimal("74.1"),
    "source":               "IPCC 2006 Vol 2 Table 2.2 + Table 2.3"
}
# ⚠ HUMAN DECISION: petrol, lpg, png, furnace_oil constants not defined.
# Do NOT add placeholder values. Raise CalculationInputError until a human
# provides IPCC 2006 Vol 2 Ch 2 constants for each fuel type.


class GHGCalculator:

    # ── Scope 1 Process (stoichiometric) ──────────────────────────────────────
    @staticmethod
    def calculate_scope1_process(input: Scope1ProcessInput) -> EmissionResult:
        """
        Stoichiometric mass-balance: emissions = production_volume × emission_factor
        Source: IPCC 2006 Guidelines Vol 3, process-specific chapters

        IMPORTANT: Only accepts factors with factor_type = 'direct_ghg'
        (unit: tCO2e/tonne_product).
        Energy intensity factors (GJ/tonne) must go through calculate_from_sec_benchmark.
        """
        if not input.emission_factor.id:
            raise FactorNotFoundError(process_id="unknown")

        factor = input.emission_factor

        # Guard against misuse of energy_intensity factors
        if factor.factor_type != 'direct_ghg':
            raise CalculationInputError(
                f"Factor '{factor.process_id}' has factor_type='{factor.factor_type}' "
                f"(unit: {factor.unit}). "
                "Cannot use energy_intensity factors directly in stoichiometric calculation. "
                "Use calculate_from_sec_benchmark() with elec/thermal split from plant."
            )

        if not (factor.unit.endswith('/tonne_product') or 'tCO2e/tonne' in factor.unit):
            raise CalculationInputError(
                f"Unexpected emission factor unit '{factor.unit}'. "
                "Expected unit containing '/tonne_product' or 'tCO2e/tonne'."
            )

        requires_review = (
            factor.confidence == 'LOW' or
            (factor.confidence == 'MEDIUM' and
             input.production_volume_tonnes > Decimal('500'))
        )

        value = input.production_volume_tonnes * factor.factor_value

        return EmissionResult(
            value_tco2e=value,
            scope='scope1_process',
            calculation_method=(
                f"scope1_process: {input.production_volume_tonnes}t × "
                f"{factor.factor_value} {factor.unit} "
                f"(source: {factor.source})"
            ),
            requires_human_review=requires_review,
            factor_id=factor.id
        )

    # ── Scope 1 Combustion — Liquid Fuel (diesel only for MVP) ────────────────
    @staticmethod
    def calculate_scope1_combustion(input: Scope1CombustionInput) -> EmissionResult:
        """
        Liquid fuel combustion via IPCC mass-balance chain.
        Diesel only for MVP.
        Source: IPCC 2006 Vol 2 Table 2.2 + Table 2.3
        """
        if input.fuel_type != 'diesel':
            raise CalculationInputError(
                f"Fuel type '{input.fuel_type}' is not yet supported. "
                "Human must provide IPCC 2006 Vol 2 Ch 2 constants (density, NCV, EF) "
                "before this fuel type can be used in calculations."
            )

        c = DIESEL_CONSTANTS
        step1 = input.fuel_consumed_litres * c["density_kg_per_litre"]  # kg
        step2 = step1 / Decimal("1000")                                  # tonnes
        step3 = step2 * c["ncv_GJ_per_tonne"]                           # GJ
        step4 = step3 / Decimal("1000")                                  # TJ
        step5 = step4 * c["ef_tCO2_per_TJ"]                             # tCO2e

        return EmissionResult(
            value_tco2e=step5,
            scope='scope1_combustion',
            calculation_method=(
                f"scope1_combustion_diesel: {input.fuel_consumed_litres}L × "
                f"{c['density_kg_per_litre']}kg/L ÷1000 × "
                f"{c['ncv_GJ_per_tonne']}GJ/t ÷1000 × "
                f"{c['ef_tCO2_per_TJ']}tCO2/TJ = {step5}tCO2e "
                f"({c['source']})"
            ),
            requires_human_review=False
        )

    # ── Scope 1 Combustion — Thermal Coal (PRIMARY Gujarat path) ──────────────
    @staticmethod
    def calculate_scope1_thermal_coal(thermal_energy_GJ: Decimal) -> EmissionResult:
        """
        Scope 1 combustion from coal-fired steam boilers / thermopacks.
        This is the PRIMARY Scope 1 path for Gujarat chemical MSMEs.
        Used when a plant reports thermal energy consumption in GJ directly
        (from energy audit records or BEE PAT scheme data).

        Formula: emissions = thermal_energy_GJ × 0.0961
        Source: IPCC 2006 Guidelines Vol 2 Table 2.2
                Indian sub-bituminous coal: 96,100 kgCO2/TJ = 0.0961 tCO2/GJ
                Confirmed: BRSR GHG Research Report Section 5.3 (2025)
        """
        if thermal_energy_GJ <= Decimal("0"):
            raise CalculationInputError("thermal_energy_GJ must be positive")

        value = thermal_energy_GJ * COAL_EF_TCO2_PER_GJ

        return EmissionResult(
            value_tco2e=value,
            scope='scope1_combustion',
            calculation_method=(
                f"scope1_thermal_coal: {thermal_energy_GJ} GJ × "
                f"{COAL_EF_TCO2_PER_GJ} tCO2/GJ "
                f"(IPCC 2006 Vol2 Table 2.2, Indian sub-bituminous coal)"
            ),
            requires_human_review=False
        )

    # ── Scope 2 ───────────────────────────────────────────────────────────────
    @staticmethod
    def calculate_scope2(input: Scope2Input) -> EmissionResult:
        """
        Location-based Scope 2: kWh × CEA India grid factor
        CEA Grid Emission Factor FY2023-24: 0.716 tCO2/MWh
        Source: CEA/TPP/EE/2024 Table 2
        """
        value = (input.kwh_consumed / Decimal("1000")) * CEA_GRID_FACTOR_TCO2_PER_MWH

        return EmissionResult(
            value_tco2e=value,
            scope='scope2',
            calculation_method=(
                f"scope2_location: ({input.kwh_consumed}kWh ÷ 1000) × "
                f"{CEA_GRID_FACTOR_TCO2_PER_MWH} tCO2/MWh (CEA FY2024) = {value}tCO2"
            ),
            requires_human_review=False
        )

    # ── SEC Benchmark Fallback (primary path for pilot cohort) ────────────────
    @staticmethod
    def calculate_from_sec_benchmark(
        sec_total_GJ_per_tonne: Decimal,
        production_tonnes: Decimal,
        elec_fraction: Decimal,
        thermal_fraction: Decimal,
        fuel_type: Literal['coal', 'natural_gas']
    ) -> dict:
        """
        Energy-to-emissions fallback methodology.

        Used when a plant cannot provide sub-metered utility data (most Gujarat MSMEs
        in the pilot cohort). Plant provides:
          - SEC (specific energy consumption) in GJ/tonne from their energy audit
          - Electricity vs thermal split (elec_fraction + thermal_fraction = 1.0)
          - Primary thermal fuel type

        Returns BOTH scope1 and scope2 EmissionResult objects.
        Always sets requires_human_review=True — benchmark, not primary metered data.

        Formulas:
          total_energy_GJ = sec_total_GJ_per_tonne × production_tonnes
          elec_GJ         = total_energy_GJ × elec_fraction
          thermal_GJ      = total_energy_GJ × thermal_fraction
          scope2_tco2e    = (elec_GJ / 3.6) × 0.716   [MWh × CEA factor]
          scope1_tco2e    = thermal_GJ × fuel_ef        [coal: 0.0961 tCO2/GJ]

        Source methodology: BRSR GHG Emission Factor Research Report Section 5 (2025)
        Validated against: Section 5.2 worked example
            H-acid, 16.0 GJ/t, 20/80 split → 1.866 tCO2e/tonne
        """
        if production_tonnes <= Decimal("0"):
            raise CalculationInputError("production_tonnes must be positive")
        if not (Decimal("0") <= elec_fraction <= Decimal("1")):
            raise CalculationInputError("elec_fraction must be between 0 and 1")
        if not (Decimal("0") <= thermal_fraction <= Decimal("1")):
            raise CalculationInputError("thermal_fraction must be between 0 and 1")
        if abs(elec_fraction + thermal_fraction - Decimal("1.0")) > Decimal("0.01"):
            raise CalculationInputError(
                f"elec_fraction ({elec_fraction}) + thermal_fraction ({thermal_fraction}) "
                "must sum to 1.0 (±0.01 tolerance)"
            )

        total_energy_GJ = sec_total_GJ_per_tonne * production_tonnes
        elec_GJ         = total_energy_GJ * elec_fraction
        thermal_GJ      = total_energy_GJ * thermal_fraction

        # Scope 2
        elec_MWh    = elec_GJ / Decimal("3.6")
        scope2_val  = elec_MWh * CEA_GRID_FACTOR_TCO2_PER_MWH

        # Scope 1
        if fuel_type == 'coal':
            fuel_ef = COAL_EF_TCO2_PER_GJ
            fuel_source = "IPCC 2006 Vol2 Table 2.2, Indian sub-bituminous coal"
        else:
            # ⚠ HUMAN DECISION: natural_gas IPCC factor not yet confirmed.
            # Do NOT add a placeholder value. Raise until factor is provided.
            raise CalculationInputError(
                "natural_gas thermal emission factor not yet configured. "
                "⚠ HUMAN DECISION required: provide IPCC 2006 Vol 2 Table 2.2 "
                "natural gas EF (tCO2/GJ) before this path can be used."
            )

        scope1_val = thermal_GJ * fuel_ef

        scope1_method = (
            f"sec_benchmark_scope1: {sec_total_GJ_per_tonne}GJ/t × "
            f"{production_tonnes}t × {thermal_fraction}_thermal × "
            f"{fuel_ef}tCO2/GJ ({fuel_type}, {fuel_source})"
        )
        scope2_method = (
            f"sec_benchmark_scope2: {elec_GJ}GJ_elec ÷ 3.6 × "
            f"{CEA_GRID_FACTOR_TCO2_PER_MWH}tCO2/MWh (CEA FY2024)"
        )

        return {
            "scope1": EmissionResult(
                value_tco2e=scope1_val,
                scope='scope1_combustion',
                calculation_method=scope1_method,
                requires_human_review=True   # always True — benchmark, not metered
            ),
            "scope2": EmissionResult(
                value_tco2e=scope2_val,
                scope='scope2',
                calculation_method=scope2_method,
                requires_human_review=True   # always True — benchmark, not metered
            ),
        }

    # ── KPI 3 Energy ──────────────────────────────────────────────────────────
    @staticmethod
    def calculate_kpi3_energy(
        fuel_consumed_litres: Optional[Decimal] = None,
        kwh_consumed: Optional[Decimal] = None,
        thermal_coal_GJ: Optional[Decimal] = None,
        production_tonnes: Optional[Decimal] = None
    ) -> KPI3EnergyResult:
        """
        KPI 3 total energy and intensity.
        Accepts any combination of diesel, electricity, and coal thermal.
        At least one energy input must be provided.

        Constants:
          Diesel NCV: 43.0 GJ/t, density: 0.832 kg/L
          1 kWh = 1/277.778 GJ  (1 GJ = 277.778 kWh)
          Coal thermal: passed in directly as GJ (already in energy units)
        """
        if fuel_consumed_litres is None and kwh_consumed is None and thermal_coal_GJ is None:
            raise CalculationInputError(
                "At least one energy input required: "
                "fuel_consumed_litres, kwh_consumed, or thermal_coal_GJ."
            )

        KWH_TO_GJ_DIVISOR = Decimal("277.778")
        DIESEL_DENSITY    = Decimal("0.832")
        DIESEL_NCV        = Decimal("43.0")

        diesel_GJ = Decimal("0")
        if fuel_consumed_litres is not None:
            diesel_GJ = (fuel_consumed_litres * DIESEL_DENSITY / Decimal("1000")) * DIESEL_NCV

        elec_GJ = Decimal("0")
        if kwh_consumed is not None:
            elec_GJ = kwh_consumed / KWH_TO_GJ_DIVISOR

        coal_GJ = Decimal("0")
        if thermal_coal_GJ is not None:
            if thermal_coal_GJ < Decimal("0"):
                raise CalculationInputError("thermal_coal_GJ must be non-negative")
            coal_GJ = thermal_coal_GJ

        total_GJ = diesel_GJ + elec_GJ + coal_GJ

        intensity = None
        if production_tonnes is not None and production_tonnes > Decimal("0"):
            intensity = total_GJ / production_tonnes

        return KPI3EnergyResult(
            total_energy_GJ=total_GJ,
            energy_intensity_GJ_per_tonne=intensity,
            calculation_method=(
                f"kpi3: diesel={diesel_GJ}GJ + electricity={elec_GJ}GJ "
                f"+ coal_thermal={coal_GJ}GJ = {total_GJ}GJ"
                + (f" | intensity={intensity}GJ/t" if intensity else "")
            )
        )
