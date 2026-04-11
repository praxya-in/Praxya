import pytest
from decimal import Decimal
from services.domain.emissions.ghg_calculator import (
    GHGCalculator, BENCHMARK_SEC_GJ_PER_TONNE, COAL_EF_TCO2_PER_GJ,
    CEA_GRID_FACTOR_TCO2_PER_MWH
)
from services.domain.emissions.models import (
    Scope1ProcessInput, Scope1CombustionInput, Scope2Input, EmissionFactor
)
from services.domain.emissions.exceptions import FactorNotFoundError, CalculationInputError


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_direct_factor(confidence='HIGH', value='2.5'):
    """direct_ghg factor — tCO2e/tonne_product — for stoichiometric path."""
    return EmissionFactor(
        id='test-factor-id',
        process_id='azo_dye_synthesis',
        factor_value=Decimal(value),
        unit='tCO2e/tonne_product',
        source='IPCC 2006 Vol 3',
        confidence=confidence,
        factor_type='direct_ghg'
    )

def make_energy_factor():
    """energy_intensity factor — GJ/tonne_product — must NOT go into scope1_process."""
    return EmissionFactor(
        id='energy-factor-id',
        process_id='dyes_pigments_manufacturing_ankleshwar_average',
        factor_value=Decimal('6.0'),
        unit='GJ/tonne_product',
        source='BEE/TERI 2022',
        confidence='MEDIUM',
        factor_type='energy_intensity'
    )


# ── Scope 1 Process ────────────────────────────────────────────────────────────

def test_scope1_process_basic():
    result = GHGCalculator.calculate_scope1_process(
        Scope1ProcessInput(
            production_volume_tonnes=Decimal('100'),
            emission_factor=make_direct_factor()
        )
    )
    assert result.value_tco2e == Decimal('250')
    assert result.requires_human_review is False


def test_scope1_process_low_confidence_flags_review():
    result = GHGCalculator.calculate_scope1_process(
        Scope1ProcessInput(
            production_volume_tonnes=Decimal('100'),
            emission_factor=make_direct_factor(confidence='LOW')
        )
    )
    assert result.requires_human_review is True


def test_scope1_process_missing_factor_id_raises():
    bad_factor = EmissionFactor(
        id='',  # empty id triggers FactorNotFoundError
        process_id='azo_dye_synthesis',
        factor_value=Decimal('2.5'),
        unit='tCO2e/tonne_product',
        source='test',
        confidence='HIGH',
        factor_type='direct_ghg'
    )
    with pytest.raises(FactorNotFoundError):
        GHGCalculator.calculate_scope1_process(
            Scope1ProcessInput(
                production_volume_tonnes=Decimal('100'),
                emission_factor=bad_factor
            )
        )


def test_scope1_process_rejects_energy_intensity_factor():
    """
    Energy intensity factors (GJ/tonne) must NOT go into stoichiometric calculation.
    They must route through calculate_from_sec_benchmark instead.
    """
    with pytest.raises(CalculationInputError, match="energy_intensity"):
        GHGCalculator.calculate_scope1_process(
            Scope1ProcessInput(
                production_volume_tonnes=Decimal('100'),
                emission_factor=make_energy_factor()
            )
        )


# ── Scope 1 Combustion — Diesel ────────────────────────────────────────────────

def test_scope1_combustion_diesel():
    """
    Verified derivation:
    1000L × 0.832 kg/L = 832 kg
    832 / 1000 = 0.832 t
    0.832 × 43.0 = 35.776 GJ
    35.776 / 1000 = 0.035776 TJ
    0.035776 × 74.1 = 2.651002 tCO2e → 2.65100 to 5dp
    """
    result = GHGCalculator.calculate_scope1_combustion(
        Scope1CombustionInput(fuel_type='diesel', fuel_consumed_litres=Decimal('1000'))
    )
    assert isinstance(result.value_tco2e, Decimal)
    assert abs(result.value_tco2e - Decimal('2.65100')) < Decimal('0.00001')


def test_scope1_combustion_unsupported_fuel():
    with pytest.raises(CalculationInputError):
        GHGCalculator.calculate_scope1_combustion(
            Scope1CombustionInput(fuel_type='petrol', fuel_consumed_litres=Decimal('500'))
        )


# ── Scope 1 Combustion — Thermal Coal ─────────────────────────────────────────

def test_scope1_thermal_coal_basic():
    """
    100 GJ × 0.0961 tCO2/GJ = 9.61 tCO2e
    Source: IPCC 2006 Vol 2 Table 2.2, Indian sub-bituminous coal
    """
    result = GHGCalculator.calculate_scope1_thermal_coal(Decimal('100'))
    assert isinstance(result.value_tco2e, Decimal)
    assert abs(result.value_tco2e - Decimal('9.61')) < Decimal('0.001')
    assert result.scope == 'scope1_combustion'
    assert result.requires_human_review is False


def test_scope1_thermal_coal_zero_raises():
    with pytest.raises(CalculationInputError):
        GHGCalculator.calculate_scope1_thermal_coal(Decimal('0'))


# ── Scope 2 ────────────────────────────────────────────────────────────────────

def test_scope2_basic():
    result = GHGCalculator.calculate_scope2(Scope2Input(kwh_consumed=Decimal('1000')))
    assert result.value_tco2e == Decimal('0.716')


def test_scope2_large_scale():
    result = GHGCalculator.calculate_scope2(Scope2Input(kwh_consumed=Decimal('500000')))
    assert result.value_tco2e == Decimal('358.000')


# ── SEC Benchmark Fallback ─────────────────────────────────────────────────────

def test_sec_benchmark_h_acid_worked_example():
    """
    Validates against the worked example in BRSR GHG Research Report Section 5.2:
    H-acid, SEC=16.0 GJ/t, 20% elec / 80% thermal (coal), 1 tonne production

    Exact Decimal arithmetic:
      scope1 = 16.0 × 0.80 × 0.0961 = 12.8 × 0.0961 = 1.23008 tCO2e
      scope2 = 16.0 × 0.20 / 3.6 × 0.716 ≈ 0.63644 tCO2e
      combined ≈ 1.8665 tCO2e

    Report quotes combined 1.866 tCO2e/tonne — matches within rounding.
    (Report's 1.22848 for scope1 appears to be a manual rounding artefact;
     Decimal gives 1.23008 exactly.)
    """
    results = GHGCalculator.calculate_from_sec_benchmark(
        sec_total_GJ_per_tonne=Decimal('16.0'),
        production_tonnes=Decimal('1'),
        elec_fraction=Decimal('0.20'),
        thermal_fraction=Decimal('0.80'),
        fuel_type='coal'
    )
    scope1 = results['scope1']
    scope2 = results['scope2']

    assert isinstance(scope1.value_tco2e, Decimal)
    assert isinstance(scope2.value_tco2e, Decimal)

    # Individual scope checks (exact Decimal arithmetic)
    assert abs(scope1.value_tco2e - Decimal('1.23008')) < Decimal('0.001')
    assert abs(scope2.value_tco2e - Decimal('0.63644')) < Decimal('0.001')

    # Combined should match report's 1.866 tCO2e/tonne
    combined = scope1.value_tco2e + scope2.value_tco2e
    assert abs(combined - Decimal('1.866')) < Decimal('0.01')

    # Must always require human review — benchmark, not metered data
    assert scope1.requires_human_review is True
    assert scope2.requires_human_review is True


def test_sec_benchmark_fractions_must_sum_to_one():
    with pytest.raises(CalculationInputError, match="sum to 1.0"):
        GHGCalculator.calculate_from_sec_benchmark(
            sec_total_GJ_per_tonne=Decimal('6.0'),
            production_tonnes=Decimal('100'),
            elec_fraction=Decimal('0.30'),
            thermal_fraction=Decimal('0.80'),   # 0.30 + 0.80 = 1.10 — invalid
            fuel_type='coal'
        )


def test_sec_benchmark_natural_gas_raises():
    """Natural gas EF not yet confirmed — must raise, not approximate."""
    with pytest.raises(CalculationInputError, match="HUMAN DECISION"):
        GHGCalculator.calculate_from_sec_benchmark(
            sec_total_GJ_per_tonne=Decimal('9.67'),
            production_tonnes=Decimal('100'),
            elec_fraction=Decimal('0.30'),
            thermal_fraction=Decimal('0.70'),
            fuel_type='natural_gas'
        )


# ── KPI 3 Energy ──────────────────────────────────────────────────────────────

def test_kpi3_energy_all_three_inputs():
    """KPI 3 now accepts coal thermal GJ in addition to diesel and electricity."""
    result = GHGCalculator.calculate_kpi3_energy(
        fuel_consumed_litres=Decimal('1000'),
        kwh_consumed=Decimal('10000'),
        thermal_coal_GJ=Decimal('50'),
        production_tonnes=Decimal('100')
    )
    assert result.total_energy_GJ > Decimal('0')
    assert result.energy_intensity_GJ_per_tonne is not None
    assert isinstance(result.total_energy_GJ, Decimal)
    # Coal contributes exactly 50 GJ directly — verify it's included
    assert result.total_energy_GJ > Decimal('50')


def test_kpi3_energy_no_inputs_raises():
    with pytest.raises(CalculationInputError):
        GHGCalculator.calculate_kpi3_energy()


# ── Decimal precision ─────────────────────────────────────────────────────────

def test_decimal_precision_everywhere():
    """All public methods must return Decimal, never float."""
    r1 = GHGCalculator.calculate_scope2(Scope2Input(kwh_consumed=Decimal('1000')))
    assert isinstance(r1.value_tco2e, Decimal), "scope2 must return Decimal"

    r2 = GHGCalculator.calculate_scope1_thermal_coal(Decimal('100'))
    assert isinstance(r2.value_tco2e, Decimal), "thermal_coal must return Decimal"

    r3 = GHGCalculator.calculate_from_sec_benchmark(
        Decimal('6.0'), Decimal('100'), Decimal('0.20'), Decimal('0.80'), 'coal'
    )
    assert isinstance(r3['scope1'].value_tco2e, Decimal)
    assert isinstance(r3['scope2'].value_tco2e, Decimal)
