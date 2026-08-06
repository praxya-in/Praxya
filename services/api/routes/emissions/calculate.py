import logging
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from services.api.routes.deps import get_user_supabase
from services.domain.emissions.ghg_calculator import GHGCalculator
from services.domain.emissions.models import (
    Scope1ProcessInput, Scope1CombustionInput, Scope2Input, EmissionFactor
)
from services.domain.emissions.exceptions import FactorNotFoundError, CalculationInputError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emissions", tags=["emissions"])

class CalculateRequest(BaseModel):
    reporting_period_id: str

@router.post("/calculate")
async def calculate_emissions(
    req: CalculateRequest,
    client: Client = Depends(get_user_supabase)
):
    """
    Trigger GHG + energy calc for a period.
    """
    reporting_period_id = req.reporting_period_id

    # Get all approved inputs that don't have results yet
    # Actually, we can fetch all approved inputs for the period
    inputs_res = client.table("emission_inputs").select("*").eq("reporting_period_id", reporting_period_id).eq("status", "eitl_approved").execute()
    
    if not inputs_res.data:
        return {"status": "ok", "message": "No approved inputs found for this period.", "results": 0}

    # Fetch all factors
    factors_res = client.table("emission_factors").select("*").execute()
    factors_by_process = {f["process_id"]: f for f in factors_res.data}

    # Also check if results already exist to avoid duplicates
    results_res = client.table("emission_results").select("input_id").execute()
    existing_input_ids = {r["input_id"] for r in results_res.data}

    inputs_to_process = [inp for inp in inputs_res.data if inp["id"] not in existing_input_ids]

    if not inputs_to_process:
        return {"status": "ok", "message": "All inputs already calculated.", "results": 0}

    results_to_insert = []

    for inp in inputs_to_process:
        inp_type = inp["input_type"]
        qty = Decimal(str(inp["quantity"]))

        try:
            if inp_type == "grid_electricity":
                res = GHGCalculator.calculate_scope2(Scope2Input(kwh_consumed=qty))
                results_to_insert.append({
                    "input_id": inp["id"],
                    "factor_id": res.factor_id,
                    "scope": res.scope,
                    "value_tco2e": str(res.value_tco2e),
                    "calculation_method": res.calculation_method,
                    "requires_human_review": res.requires_human_review
                })

            elif inp_type == "fuel_consumption":
                # Assuming fuel_type is diesel since MVP only supports diesel
                sub_type = inp.get("fuel_sub_type", "diesel")
                res = GHGCalculator.calculate_scope1_combustion(Scope1CombustionInput(
                    fuel_type=sub_type, fuel_consumed_litres=qty
                ))
                results_to_insert.append({
                    "input_id": inp["id"],
                    "factor_id": res.factor_id,
                    "scope": res.scope,
                    "value_tco2e": str(res.value_tco2e),
                    "calculation_method": res.calculation_method,
                    "requires_human_review": res.requires_human_review
                })

            elif inp_type == "thermal_coal":
                unit = inp.get("unit")
                if unit != "GJ":
                    # Cannot calculate without GJ
                    continue
                res = GHGCalculator.calculate_scope1_thermal_coal(qty)
                results_to_insert.append({
                    "input_id": inp["id"],
                    "factor_id": res.factor_id,
                    "scope": res.scope,
                    "value_tco2e": str(res.value_tco2e),
                    "calculation_method": res.calculation_method,
                    "requires_human_review": res.requires_human_review
                })

            elif inp_type == "production_volume":
                process_id = inp["process_id"]
                if process_id not in factors_by_process:
                    raise FactorNotFoundError(process_id)
                
                f_data = factors_by_process[process_id]
                factor = EmissionFactor(
                    id=f_data["id"],
                    process_id=f_data["process_id"],
                    factor_value=Decimal(str(f_data["factor_value"])),
                    unit=f_data["unit"],
                    source=f_data["source"],
                    confidence=f_data["confidence"],
                    factor_type=f_data.get("factor_type", "direct_ghg")
                )

                # Need to handle sec_benchmark fallback if factor_type is energy_intensity
                if factor.factor_type == "energy_intensity":
                    meta = inp.get("metadata", {})
                    if meta.get("calculation_path") == "sec_benchmark":
                        # We need the fuel split etc.
                        elec_fraction = Decimal(str(meta.get("elec_fraction", 0.2)))
                        thermal_fraction = Decimal(str(meta.get("thermal_fraction", 0.8)))
                        sec_gj = factor.factor_value
                        
                        fallback_res = GHGCalculator.calculate_from_sec_benchmark(
                            sec_total_GJ_per_tonne=sec_gj,
                            production_tonnes=qty,
                            elec_fraction=elec_fraction,
                            thermal_fraction=thermal_fraction,
                            fuel_type='coal' # Assuming coal for MVP
                        )
                        
                        # Add scope1 and scope2
                        for scope_key in ["scope1", "scope2"]:
                            res_obj = fallback_res[scope_key]
                            results_to_insert.append({
                                "input_id": inp["id"],
                                "factor_id": factor.id,
                                "scope": res_obj.scope,
                                "value_tco2e": str(res_obj.value_tco2e),
                                "calculation_method": res_obj.calculation_method,
                                "requires_human_review": res_obj.requires_human_review
                            })
                    else:
                        raise CalculationInputError("Missing sec_benchmark metadata for energy_intensity factor")
                else:
                    res = GHGCalculator.calculate_scope1_process(Scope1ProcessInput(
                        production_volume_tonnes=qty, emission_factor=factor
                    ))
                    results_to_insert.append({
                        "input_id": inp["id"],
                        "factor_id": res.factor_id,
                        "scope": res.scope,
                        "value_tco2e": str(res.value_tco2e),
                        "calculation_method": res.calculation_method,
                        "requires_human_review": res.requires_human_review
                    })

        except FactorNotFoundError as e:
            raise HTTPException(status_code=422, detail={"error": "factor_not_found", "process_id": e.process_id})
        except CalculationInputError as e:
            raise HTTPException(status_code=422, detail={"error": "calculation_error", "message": str(e)})

    if results_to_insert:
        try:
            client.table("emission_results").insert(results_to_insert).execute()
        except Exception as e:
            logger.exception("Failed to insert emission results")
            raise HTTPException(status_code=500, detail="Failed to save results")

    return {"status": "ok", "calculated_results": len(results_to_insert)}
