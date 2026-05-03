from app.schemas import ReceiptStandardSchema
import difflib

def calculate_string_similarity(str1: str, str2: str) -> float:
    if not str1 and not str2:
        return 1.0
    if not str1 or not str2:
        return 0.0
    return difflib.SequenceMatcher(None, str(str1).lower(), str(str2).lower()).ratio()

def validate_extraction(extracted: dict, ground_truth: dict) -> dict:
    """
    Compares extracted JSON against ground_truth JSON.
    Returns metrics and a score.
    """
    metrics = {
        "fields": {},
        "errors": [],
        "warnings": []
    }
    
    total_score = 0.0
    field_count = 0
    
    # 1. Compare Merchant
    merchant_ext = extracted.get("merchant", {})
    merchant_gt = ground_truth.get("merchant", {})
    
    # CNPJ
    cnpj_score = 1.0 if merchant_ext.get("cnpj") == merchant_gt.get("cnpj") else 0.0
    metrics["fields"]["cnpj"] = {"score": cnpj_score, "extracted": merchant_ext.get("cnpj"), "expected": merchant_gt.get("cnpj")}
    total_score += cnpj_score
    field_count += 1
    
    # Math validation
    payment_ext = extracted.get("payment", {})
    items_ext = extracted.get("items", [])
    
    math_errors = []
    calculated_subtotal = 0.0
    for i, item in enumerate(items_ext):
        qty = float(item.get("quantity") or 0.0)
        u_price = float(item.get("unit_price") or 0.0)
        item_total = float(item.get("total_price") or 0.0)
        
        # Math Check 1: qty * unit_price ~= total_price
        if abs((qty * u_price) - item_total) > 0.05: # allow 5 cents rounding
            math_errors.append(f"Item {i} math mismatch: {qty} * {u_price} != {item_total}")
            
        calculated_subtotal += item_total
        
    ext_total = float(payment_ext.get("total") or 0.0)
    
    if items_ext and abs(calculated_subtotal - ext_total) > 0.10:
        math_errors.append(f"Subtotal mismatch: items sum ({calculated_subtotal}) != total ({ext_total})")
        
    metrics["math_errors"] = math_errors
    
    final_score = (total_score / field_count) if field_count > 0 else 0.0
    
    # Rules for approval
    approved = False
    if final_score >= 0.90 and len(math_errors) == 0:
        approved = True
        
    return {
        "score_overall": final_score * 100,
        "metrics_json": metrics,
        "status": "approved" if approved else "needs_human_review"
    }

