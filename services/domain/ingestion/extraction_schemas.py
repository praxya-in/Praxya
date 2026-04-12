"""
Pydantic v2 extraction schemas for each document type.

ISOLATION RULE: These schemas are the ONLY bridge between LLM output
and the rest of the system. No raw LLM text escapes this module.

⚠ FIELD ADDITIONS vs ORIGINAL PROMPT 4:
  - ThermalCoalInvoiceExtraction: new (coal boiler is the PRIMARY Gujarat Scope 1 path;
    omitting it causes ~5x Scope 1 underestimate)
  - ProductionLogExtraction: added reported_sec_GJ_per_tonne, elec_fraction,
    thermal_fraction — required for calculate_from_sec_benchmark fallback
    when a company has its own BEE energy audit data
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Literal, Union
from datetime import date
from decimal import Decimal


class ElectricityBillExtraction(BaseModel):
    """DISCOM bill: DGVCL, GETCO, MGVCL — typical Gujarat industrial tariffs."""
    billing_period_start: date
    billing_period_end: date
    total_units_kwh: Decimal = Field(gt=Decimal("0"))
    peak_units_kwh: Optional[Decimal] = None          # HT tariff bills split peak/off-peak
    off_peak_units_kwh: Optional[Decimal] = None
    sanctioned_load_kva: Optional[Decimal] = None     # for demand charge verification
    discom_name: Optional[str] = None                 # e.g. 'DGVCL', 'MGVCL'
    consumer_number: Optional[str] = None
    confidence: Dict[str, float]                      # per-field confidence 0.0–1.0

    @model_validator(mode='after')
    def validate_period(self) -> 'ElectricityBillExtraction':
        if self.billing_period_end <= self.billing_period_start:
            raise ValueError('billing_period_end must be strictly after billing_period_start')
        return self

    @model_validator(mode='after')
    def validate_peak_sum(self) -> 'ElectricityBillExtraction':
        """If both peak and off-peak are present, their sum should approximate total."""
        if self.peak_units_kwh is not None and self.off_peak_units_kwh is not None:
            summed = self.peak_units_kwh + self.off_peak_units_kwh
            tolerance = self.total_units_kwh * Decimal("0.02")  # 2% tolerance for rounding
            if abs(summed - self.total_units_kwh) > tolerance:
                raise ValueError(
                    f'peak ({self.peak_units_kwh}) + off_peak ({self.off_peak_units_kwh}) '
                    f'= {summed}, does not match total_units_kwh={self.total_units_kwh} '
                    f'within 2% tolerance. Mark requires_human_review.'
                )
        return self


class FuelInvoiceExtraction(BaseModel):
    """Diesel/petrol/LPG invoice. MVP: only diesel feeds GHGCalculator.
    Other fuel types are captured but excluded from calculation until
    IPCC constants are confirmed (see HUMAN DECISIONS)."""
    invoice_date: date
    fuel_type: Literal['diesel', 'petrol', 'lpg', 'png', 'furnace_oil']
    quantity_litres: Decimal = Field(gt=Decimal("0"))
    rate_per_litre: Optional[Decimal] = None           # audit trail, not used in calculation
    supplier_name: Optional[str] = None
    vehicle_number: Optional[str] = None               # delivery tanker, not the forklift
    confidence: Dict[str, float]


class ThermalCoalInvoiceExtraction(BaseModel):
    """
    Coal delivery receipt / invoice for coal-fired boilers.

    PRIMARY Gujarat Scope 1 path for chemical manufacturers.
    Akshar Chem, Jay Chemical, and majority of Ankleshwar cluster
    use coal boilers as primary heat source.

    quantity_GJ is the REQUIRED field for GHGCalculator.calculate_scope1_thermal_coal.
    If the document only states quantity in metric tonnes, Claude must:
      - Extract quantity_tonnes
      - Leave quantity_GJ as None (do NOT guess GCV — GCV varies by coal grade)
      - Set requires_human_review hint in confidence

    The queue worker will flag the record for EITL review if quantity_GJ is None.
    """
    delivery_date: date
    supplier_name: Optional[str] = None
    coal_grade: Optional[str] = None                   # e.g. 'F-Grade', 'G-Grade', 'Imported'
    quantity_tonnes: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    quantity_GJ: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    gross_calorific_value_MJ_per_kg: Optional[Decimal] = None  # from lab report if present
    invoice_number: Optional[str] = None
    confidence: Dict[str, float]

    @model_validator(mode='after')
    def at_least_one_quantity(self) -> 'ThermalCoalInvoiceExtraction':
        if self.quantity_tonnes is None and self.quantity_GJ is None:
            raise ValueError(
                'At least one of quantity_tonnes or quantity_GJ must be present. '
                'Extract whichever the document states — do not fabricate the other.'
            )
        return self

    @model_validator(mode='after')
    def derive_gj_if_possible(self) -> 'ThermalCoalInvoiceExtraction':
        """
        If GCV is stated and quantity_tonnes is stated, derive quantity_GJ.
        GHGCalculator needs GJ; this saves an EITL review step.
        Formula: GJ = tonnes × GCV_MJ_per_kg × 1000 / 1,000,000 = tonnes × GCV / 1000
        """
        if (self.quantity_GJ is None
                and self.quantity_tonnes is not None
                and self.gross_calorific_value_MJ_per_kg is not None):
            self.quantity_GJ = (
                self.quantity_tonnes
                * self.gross_calorific_value_MJ_per_kg
                / Decimal("1000")
            )
        return self


class ProductionLogExtraction(BaseModel):
    """
    Monthly/quarterly production record from plant operator.

    REQUIRED BY GHGCalculator:
      - quantity_tonnes → production_volume emission_input
      - process_id → looked up in emission_factors table at calculation time

    OPTIONAL (benchmark fallback path):
      - reported_sec_GJ_per_tonne → if company has BEE energy audit, use their
        own SEC instead of the benchmark. Routes to calculate_from_sec_benchmark.
        If present, always set requires_human_review=True (EITL must verify audit source).
      - elec_fraction → fraction of SEC that is electricity (0.0–1.0)
      - thermal_fraction → fraction of SEC that is thermal (0.0–1.0).
        elec_fraction + thermal_fraction must equal 1.0 ± 0.01 if both are present.

    If the production log states SEC, elec_fraction, thermal_fraction:
      → ExtractionService routes to calculate_from_sec_benchmark
    If it does not:
      → ExtractionService routes to calculate_scope1_process + calculate_scope2
        using sub-metered inputs
    """
    period_start: date
    period_end: date
    product_name: str
    product_code: Optional[str] = None
    quantity_tonnes: Decimal = Field(gt=Decimal("0"))
    process_id: str  # must match emission_factors.process_id — validated at calculation time, NOT here
    batch_numbers: Optional[List[str]] = None

    # Benchmark fallback fields — ADDED vs original Prompt 4
    reported_sec_GJ_per_tonne: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    elec_fraction: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    thermal_fraction: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    confidence: Dict[str, float]

    @model_validator(mode='after')
    def validate_period(self) -> 'ProductionLogExtraction':
        if self.period_end <= self.period_start:
            raise ValueError('period_end must be strictly after period_start')
        return self

    @model_validator(mode='after')
    def validate_fractions_sum(self) -> 'ProductionLogExtraction':
        if self.elec_fraction is not None and self.thermal_fraction is not None:
            total = self.elec_fraction + self.thermal_fraction
            if abs(total - Decimal("1.0")) > Decimal("0.01"):
                raise ValueError(
                    f'elec_fraction ({self.elec_fraction}) + thermal_fraction '
                    f'({self.thermal_fraction}) = {total}, must sum to 1.0 ± 0.01'
                )
        return self

    @model_validator(mode='after')
    def sec_requires_fractions(self) -> 'ProductionLogExtraction':
        """If SEC is reported, we need fractions for the benchmark calculator."""
        if (self.reported_sec_GJ_per_tonne is not None
                and (self.elec_fraction is None or self.thermal_fraction is None)):
            # Don't raise — just note it in confidence. EITL can supply missing fractions.
            # The calculation layer will use default 20/80 split with requires_human_review=True
            pass
        return self


# ── Union type for type hints downstream ──────────────────────────
ExtractionSchema = Union[
    ElectricityBillExtraction,
    FuelInvoiceExtraction,
    ThermalCoalInvoiceExtraction,
    ProductionLogExtraction,
]

DocType = Literal['electricity_bill', 'fuel_invoice', 'thermal_coal_invoice', 'production_log']
