"""
Praxya Extraction Pipeline Integration Test
This is a standalone test that exercises OCR, LLM Extraction, and GHG Calculation.
No dependencies on testing frameworks, databases, or local caching services.
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

# Ensure praxya module is loadable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env.local'))

if not os.environ.get("GROQ_API_KEY"):
    print("WARNING: GROQ_API_KEY is not set or empty in .env.local")
    print("Cannot run pipeline tests without an API key.")
    sys.exit(1)

from services.domain.ingestion.ocr_worker import OCRWorker
from services.domain.ingestion.llm_extractor import LLMExtractor
from services.domain.emissions.ghg_calculator import GHGCalculator
from services.domain.emissions.models import Scope2Input, Scope1CombustionInput
from services.domain.emissions.exceptions import CalculationInputError

def run_pipeline():
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "documents"
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    docs = [
        "electricity_bill_sample.pdf",
        "fuel_invoice_sample.pdf",
        "production_log_sample.pdf"
    ]
    
    run_timestamp = datetime.now()
    run_ts_iso = run_timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    file_ts = run_timestamp.strftime("%Y%m%d_%H%M%S")
    
    ocr_worker = OCRWorker()
    extractor = LLMExtractor()
    ghg = GHGCalculator()
    
    results = []
    passed_count = 0
    failed_count = 0
    warnings_count = 0
    
    for filename in docs:
        doc_path = fixtures_dir / filename
        doc_status = "PASSED"
        doc_warning = False
        
        stages = {
            "ocr": {},
            "extraction": {},
            "calculation": {}
        }
        
        pdf_bytes = doc_path.read_bytes()
        
        # --- STAGE 1: OCR ---
        try:
            ocr_result = ocr_worker.process_pdf_bytes(pdf_bytes, document_id=filename)
            confs = [p.confidence for p in ocr_result.per_page_results if p.confidence is not None]
            overall_conf = sum(confs) / len(confs) if confs else None
            
            stages["ocr"] = {
                "status": "FAILED" if ocr_result.error_message else "PASSED",
                "ocr_method": getattr(ocr_result, "ocr_method", "mixed"),
                "page_count": getattr(ocr_result, "page_count", 0),
                "overall_confidence": overall_conf,
                "text_preview": ocr_result.raw_text[:500] if ocr_result.raw_text else "",
                "error": ocr_result.error_message
            }
            if ocr_result.error_message:
                doc_status = "FAILED"
                results.append({"filename": filename, "status": doc_status, "stages": stages})
                failed_count += 1
                continue
                
        except Exception as e:
            stages["ocr"] = {"status": "FAILED", "error": f"{type(e).__name__}: {str(e)}"}
            doc_status = "FAILED"
            results.append({"filename": filename, "status": doc_status, "stages": stages})
            failed_count += 1
            continue
            
        # --- STAGE 2: EXTRACTION ---
        if filename.startswith("electricity_bill"):
            doc_type = "electricity_bill"
        elif filename.startswith("fuel_invoice"):
            doc_type = "fuel_invoice"
        elif filename.startswith("production_log"):
            doc_type = "production_log"
        else:
            stages["extraction"] = {"status": "FAILED", "error": f"Unknown doc_type mapping for {filename}"}
            doc_status = "FAILED"
            results.append({"filename": filename, "status": doc_status, "stages": stages})
            failed_count += 1
            continue
            
        try:
            extraction_res = extractor.extract(ocr_result, doc_type, document_id=filename)
            extracted_dict = extraction_res.model_dump(mode='python')
            conf_scores = getattr(extraction_res, 'confidence', {})
            low_conf_flags = [k for k, v in conf_scores.items() if v < 0.70]
            
            stages["extraction"] = {
                "status": "PASSED",
                "doc_type": doc_type,
                "extracted_fields": extracted_dict,
                "confidence_scores": conf_scores,
                "low_confidence_flags": low_conf_flags,
                "error": None
            }
        except Exception as e:
            stages["extraction"] = {"status": "FAILED", "error": f"{type(e).__name__}: {str(e)}"}
            doc_status = "FAILED"
            results.append({"filename": filename, "status": doc_status, "stages": stages})
            failed_count += 1
            continue

        # --- STAGE 3: CALCULATION ---
        try:
            if doc_type == "electricity_bill":
                inp = Scope2Input(
                    kwh_consumed=extraction_res.total_units_kwh
                )
                calc_res = ghg.calculate_scope2(inp)
                stages["calculation"] = {
                    "status": "PASSED",
                    "scope": "scope2",
                    "value_tco2e": str(calc_res.value_tco2e),
                    "note": None
                }
            elif doc_type == "fuel_invoice":
                f_type = getattr(extraction_res, "fuel_type", "")
                if f_type == "diesel":
                    inp = Scope1CombustionInput(
                        fuel_type="diesel",
                        fuel_consumed_litres=extraction_res.quantity_litres
                    )
                    calc_res = ghg.calculate_scope1_combustion(inp)
                    stages["calculation"] = {
                        "status": "PASSED",
                        "scope": "scope1_combustion",
                        "value_tco2e": str(calc_res.value_tco2e),
                        "note": None
                    }
                else:
                    stages["calculation"] = {
                        "status": "SKIPPED",
                        "scope": "skipped",
                        "value_tco2e": None,
                        "note": f"Not calculating for fuel_type: {f_type}"
                    }
            elif doc_type == "production_log":
                stages["calculation"] = {
                    "status": "SKIPPED",
                    "scope": "skipped",
                    "value_tco2e": None,
                    "note": "SKIPPED — requires emission_factors DB"
                }
        except CalculationInputError as e:
            doc_warning = True
            stages["calculation"] = {
                "status": "WARNING",
                "scope": "skipped",
                "value_tco2e": None,
                "note": f"CalculationInputError: {str(e)}"
            }
        except Exception as e:
            doc_status = "FAILED"
            stages["calculation"] = {"status": "FAILED", "scope": "skipped", "value_tco2e": None, "note": f"{type(e).__name__}: {str(e)}"}
            results.append({"filename": filename, "status": doc_status, "stages": stages})
            failed_count += 1
            continue

        if doc_warning:
            doc_status = "WARNING"
            warnings_count += 1
        else:
            passed_count += 1
            
        results.append({"filename": filename, "status": doc_status, "stages": stages})

    # Output generation
    json_path = output_dir / f"pipeline_run_{file_ts}.json"
    txt_path = output_dir / f"pipeline_run_{file_ts}_summary.txt"
    
    output_data = {
        "run_timestamp": run_ts_iso,
        "documents_tested": len(docs),
        "passed": passed_count,
        "failed": failed_count,
        "warnings": warnings_count,
        "results": results
    }
    
    class CustomJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            return super().default(obj)
            
    json_path.write_text(json.dumps(output_data, cls=CustomJSONEncoder, indent=2))
    
    # Generate txt dump
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("============================================================\n")
        f.write("PRAXYA EXTRACTION PIPELINE — INTEGRATION TEST\n")
        f.write(f"Run: {run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("============================================================\n\n")
        
        failures = []
        
        for idx, res in enumerate(results, 1):
            f.write(f"[{idx}/{len(docs)}] {res['filename']} — {res['status']}\n")
            
            # Formulate text lines
            # OCR
            ocr = res["stages"].get("ocr", {})
            ocr_conf_str = f"{ocr.get('overall_confidence'):.2f}" if ocr.get('overall_confidence') is not None else "N/A"
            f.write(f"├── OCR:        {ocr.get('ocr_method', 'N/A')} | {ocr.get('page_count', 0)} page | confidence: {ocr_conf_str}\n")
            
            # Extraction
            ext = res["stages"].get("extraction", {})
            ext_fields = ext.get("extracted_fields", {})
            
            # Remove confidence manually from text print output just to streamline extraction fields payload out of noise
            ext_fields_clean = {k: v for k, v in ext_fields.items() if k != 'confidence'}
            
            ext_str_pts = [f"{k}={v}" for k, v in ext_fields_clean.items()]
            # Split over multiple lines safely
            if ext_str_pts:
                f.write(f"├── Extracted:  {', '.join(ext_str_pts[:2])}\n")
                if len(ext_str_pts) > 2:
                    f.write(f"│               {', '.join(ext_str_pts[2:])}\n")
            else:
                 f.write("├── Extracted:  none\n")
                 
            # Confidence
            conf_scores = ext.get("confidence_scores", {})
            conf_str_pts = [f"{k}={v} \u2713" if v >= 0.70 else f"{k}={v} \u2717" for k, v in conf_scores.items()]
            if conf_str_pts:
                 f.write(f"├── Confidence: {'  '.join(conf_str_pts)}\n")
            else:
                 f.write("├── Confidence: none\n")
            
            # Low_conf
            low_conf = ext.get("low_confidence_flags", [])
            low_conf_str = ", ".join(low_conf) if low_conf else "none"
            f.write(f"├── Low-conf:   {low_conf_str}\n")
            
            # GHG
            calc = res["stages"].get("calculation", {})
            calc_val = f"{calc.get('value_tco2e')} tCO2" if calc.get("value_tco2e") else calc.get("note", "none")
            calc_msg = f"{calc.get('scope', 'none')} \u2192 {calc_val}"
            f.write(f"└── GHG Calc:   {calc_msg} \u2713\n\n")
            
            # Append Failures
            if res["status"] == "FAILED":
                for st_name, st_data in res["stages"].items():
                    if st_data.get("status") == "FAILED":
                        failures.append(f"- [{res['filename']}] {st_name}: {st_data.get('error', 'Unknown Error')}")
        
        f.write("============================================================\n")
        f.write(f"SUMMARY: {len(docs)} tested | {passed_count} passed | {failed_count} failed | {warnings_count} warnings\n")
        f.write("============================================================\n")
        
        if failures:
            f.write("\nFAILURES:\n")
            for fails in failures:
                f.write(f"{fails}\n")

    print(f"Test completed. {passed_count} passed, {failed_count} failed, {warnings_count} warnings.")
    print(f"Results saved to: {json_path}")
    print(f"Summary saved to: {txt_path}")
    
    if failed_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    run_pipeline()
