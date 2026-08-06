from pydantic import BaseModel, Field, model_validator, field_validator
from typing import Optional, List, Dict, Literal, Union
from datetime import date
from decimal import Decimal, InvalidOperation


def _to_decimal(v):
    """Coerce LLM string outputs to Decimal. Returns None if unparseable."""
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError):
        return None


class ElectricityBillExtraction(BaseModel):
    billing_period_start: date
    billing_period_end: date
    total_units_kwh: Decimal = Field(gt=Decimal("0"))
    peak_units_kwh: Optional[Decimal] = None
    off_peak_units_kwh: Optional[Decimal] = None
    sanctioned_load_kva: Optional[Decimal] = None
    discom_name: Optional[str] = None
    consumer_number: Optional[str] = None
    confidence: Dict[str, float]

    @field_validator('total_units_kwh', 'peak_units_kwh',
                     'off_peak_units_kwh', 'sanctioned_load_kva',
                     mode='before')
    @classmethod
    def coerce_numeric(cls, v):
        return _to_decimal(v)

    @model_validator(mode='after')
    def validate_period(self) -> 'ElectricityBillExtraction':
        if self.billing_period_end <= self.billing_period_start:
            raise ValueError('billing_period_end must be strictly after billing_period_start')
        return self

    @model_validator(mode='after')
    def validate_peak_sum(self) -> 'ElectricityBillExtraction':
        if self.peak_units_kwh is not None and self.off_peak_units_kwh is not None:
            summed = self.peak_units_kwh + self.off_peak_units_kwh
            if summed == Decimal("0"):
                self.peak_units_kwh = None
                self.off_peak_units_kwh = None
            else:
                tolerance = self.total_units_kwh * Decimal("0.02")
                if abs(summed - self.total_units_kwh) > tolerance:
                    raise ValueError(
                        f'peak ({self.peak_units_kwh}) + off_peak ({self.off_peak_units_kwh}) '
                        f'= {summed}, does not match total_units_kwh={self.total_units_kwh} '
                        f'within 2% tolerance.'
                    )
        return self


class FuelInvoiceExtraction(BaseModel):
    invoice_date: date
    fuel_type: Literal['diesel', 'petrol', 'lpg', 'png', 'furnace_oil']
    quantity_litres: Decimal = Field(gt=Decimal("0"))
    rate_per_litre: Optional[Decimal] = None
    supplier_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    confidence: Dict[str, float]

    @field_validator('quantity_litres', 'rate_per_litre', mode='before')
    @classmethod
    def coerce_numeric(cls, v):
        return _to_decimal(v)


class ThermalCoalInvoiceExtraction(BaseModel):
    delivery_date: date
    supplier_name: Optional[str] = None
    coal_grade: Optional[str] = None
    quantity_tonnes: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    quantity_GJ: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    gross_calorific_value_MJ_per_kg: Optional[Decimal] = None
    invoice_number: Optional[str] = None
    confidence: Dict[str, float]

    @field_validator('quantity_tonnes', 'quantity_GJ',
                     'gross_calorific_value_MJ_per_kg', mode='before')
    @classmethod
    def coerce_numeric(cls, v):
        return _to_decimal(v)

    @model_validator(mode='after')
    def at_least_one_quantity(self) -> 'ThermalCoalInvoiceExtraction':
        if self.quantity_tonnes is None and self.quantity_GJ is None:
            raise ValueError('At least one of quantity_tonnes or quantity_GJ must be present.')
        return self

    @model_validator(mode='after')
    def derive_gj_if_possible(self) -> 'ThermalCoalInvoiceExtraction':
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
    period_start: date
    period_end: date
    product_name: str
    product_code: Optional[str] = None
    quantity_tonnes: Decimal = Field(gt=Decimal("0"))
    process_id: str
    batch_numbers: Optional[List[str]] = None
    reported_sec_GJ_per_tonne: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    elec_fraction: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    thermal_fraction: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    confidence: Dict[str, float]

    @field_validator('quantity_tonnes', 'reported_sec_GJ_per_tonne',
                     'elec_fraction', 'thermal_fraction', mode='before')
    @classmethod
    def coerce_numeric(cls, v):
        return _to_decimal(v)

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
                    f'elec_fraction + thermal_fraction = {total}, must sum to 1.0 ± 0.01'
                )
        return self


ExtractionSchema = Union[
    ElectricityBillExtraction,
    FuelInvoiceExtraction,
    ThermalCoalInvoiceExtraction,
    ProductionLogExtraction,
]

DocType = Literal['electricity_bill', 'fuel_invoice', 'thermal_coal_invoice', 'production_log']