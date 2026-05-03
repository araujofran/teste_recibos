from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
import uuid

from . import models, schemas
from .database import engine, get_db

# Create DB tables (Lab mode)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="OCR Validation Lab API", version="1.0.0")

# CORS setup for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "OCR Validation Lab API is running"}

@app.post("/upload/", response_model=dict)
async def upload_receipt(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Uploads a receipt image and saves the metadata."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
        
    ext = file.filename.split('.')[-1]
    unique_filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Create DB entry
    db_image = models.ReceiptImage(
        filename=file.filename,
        file_url=file_path # Local path for lab
    )
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    
    return {"image_id": db_image.id, "file_url": db_image.file_url}

@app.get("/images/")
def list_images(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    images = db.query(models.ReceiptImage).order_by(models.ReceiptImage.created_at.desc()).offset(skip).limit(limit).all()
    return images

@app.post("/extract/{image_id}")
def run_extraction(image_id: str, provider: str = "mock", db: Session = Depends(get_db)):
    from .services.ocr_service import get_receipt_provider
    import json
    
    image = db.query(models.ReceiptImage).filter(models.ReceiptImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
        
    ocr = get_receipt_provider(provider)

    
    # 1. Extract raw data
    raw_data = ocr.extract_receipt(image.file_url)
    
    # 2. Normalize
    normalized_schema = ocr.normalize(raw_data)
    
    # 3. Save extraction
    db_provider = db.query(models.OcrProvider).filter(models.OcrProvider.name == provider).first()
    if not db_provider:
        db_provider = models.OcrProvider(name=provider)
        db.add(db_provider)
        db.commit()
        db.refresh(db_provider)
        
    extraction = models.ReceiptExtraction(
        image_id=image_id,
        provider_id=db_provider.id,
        raw_json=raw_data,
        normalized_json=normalized_schema.model_dump()
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)
    
    return {"extraction_id": extraction.id, "status": "success", "normalized": extraction.normalized_json}

@app.get("/extractions/{image_id}")
def list_extractions(image_id: str, db: Session = Depends(get_db)):
    extractions = db.query(models.ReceiptExtraction).filter(models.ReceiptExtraction.image_id == image_id).all()
    return extractions


@app.post("/ground_truth/")
def save_ground_truth(payload: schemas.GroundTruthCreate, db: Session = Depends(get_db)):
    image = db.query(models.ReceiptImage).filter(models.ReceiptImage.id == payload.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
        
    gt = models.ReceiptGroundTruth(
        image_id=payload.image_id,
        manual_json=payload.manual_json
    )
    db.add(gt)
    db.commit()
    db.refresh(gt)
    return {"ground_truth_id": gt.id, "status": "success"}


@app.post("/validate/{extraction_id}")
def run_validation(extraction_id: str, db: Session = Depends(get_db)):
    from .services.validation_engine import validate_extraction
    
    extraction = db.query(models.ReceiptExtraction).filter(models.ReceiptExtraction.id == extraction_id).first()
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
        
    # Get latest ground truth for this image
    gt = db.query(models.ReceiptGroundTruth).filter(models.ReceiptGroundTruth.image_id == extraction.image_id).order_by(models.ReceiptGroundTruth.created_at.desc()).first()
    
    if not gt:
        raise HTTPException(status_code=400, detail="No ground truth found for this image. Cannot validate.")
        
    # Run validation engine
    result_data = validate_extraction(extraction.normalized_json, gt.manual_json)
    
    # Save validation results
    validation = models.ReceiptValidationResult(
        extraction_id=extraction.id,
        ground_truth_id=gt.id,
        status=result_data["status"],
        score_overall=result_data["score_overall"],
        metrics_json=result_data["metrics_json"]
    )
    db.add(validation)
    db.commit()
    db.refresh(validation)
    
    # If approved, prepare delivery candidate
    if validation.status == "approved":
        candidate = models.DeliveryCandidate(
            receipt_id=extraction.id,
            customer_name=extraction.normalized_json.get("customer", {}).get("name", "N/A"),
            customer_phone=extraction.normalized_json.get("customer", {}).get("phone", "N/A"),
            address_raw=extraction.normalized_json.get("delivery", {}).get("address_raw", "N/A"),
            order_value=extraction.normalized_json.get("payment", {}).get("total", 0.0),
            status="validated"
        )
        db.add(candidate)
        db.commit()
        
    return {"validation_id": validation.id, "status": validation.status, "score": validation.score_overall, "metrics": validation.metrics_json}


# ─── Endpoint: Extração por Região (ROI) ──────────────────────────────────────
from pydantic import BaseModel as PydanticBase
import base64 as b64lib, tempfile, json as jsonlib

class ROIRequest(PydanticBase):
    image_base64: str   # data:image/jpeg;base64,....

def _build_empty_de() -> dict:
    return {
        "customer_name": "", "customer_phone": "", "delivery_address_raw": "",
        "street": "", "number": "", "complement": "", "neighborhood": "",
        "city": "", "state": "", "zip_code": "", "reference": "",
        "confidence": {"customer_name": 0.0, "customer_phone": 0.0, "address": 0.0, "overall": 0.0},
        "evidence": {"customer_name_text": "", "phone_text": "", "address_text": ""},
        "needs_human_review": True, "auto_approve_logistics": False, "reason": []
    }

@app.post("/extract-region/{image_id}")
async def extract_region(image_id: str, body: ROIRequest, db: Session = Depends(get_db)):
    """
    Extrai dados de entrega de uma região da imagem selecionada pelo usuário.

    Fallback em cascata:
      1. Gemini Vision (semântico, mais preciso)
      2. Veryfi OCR text + DeliveryDataExtractor (regex híbrido)
      3. DeliveryDataExtractor puro na imagem (regex no tmp file)
    """
    import os, re
    from .services.delivery_extractor import delivery_extractor as regex_extractor

    # ── Decodifica base64 ──────────────────────────────────────────────────────
    try:
        header, b64data = body.image_base64.split(",", 1)
        img_bytes = b64lib.b64decode(b64data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"base64 inválido: {e}")

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(img_bytes)
        tmp_path = tmp.name

    de_result = None
    provider_used = "gemini-roi"
    raw_text_used = ""

    try:
        # ── 1. Gemini Vision ───────────────────────────────────────────────────
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = """Você é um extrator de dados de entrega de recibos brasileiros.
Analise esta imagem (recorte de um recibo) e extraia os dados de entrega.
Retorne EXCLUSIVAMENTE JSON válido (sem texto extra):
{
  "customer_name": "",
  "customer_phone": "",
  "delivery_address_raw": "",
  "street": "", "number": "", "complement": "",
  "neighborhood": "", "city": "", "state": "", "zip_code": "",
  "reference": "",
  "confidence": {"customer_name": 0.0, "customer_phone": 0.0, "address": 0.0, "overall": 0.0},
  "evidence": {"customer_name_text": "", "phone_text": "", "address_text": ""},
  "needs_human_review": true,
  "reason": []
}
Regras: não invente dados; confidence 0.0-1.0; se não achar, campo vazio."""

        img_part = {"mime_type": "image/jpeg", "data": img_bytes}
        response = model.generate_content([prompt, img_part], generation_config={"temperature": 0.0})
        content = response.text.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        de_result = jsonlib.loads(content.strip())
        de_result["auto_approve_logistics"] = de_result.get("confidence", {}).get("overall", 0) >= 0.85
        provider_used = "gemini-roi"

    except Exception as gemini_err:
        logger.warning(f"[ROI] Gemini falhou ({gemini_err}), tentando Veryfi...")

        try:
            # ── 2. Veryfi OCR → delivery_extractor regex ─────────────────────
            veryfi_client_id     = os.getenv("VERYFI_CLIENT_ID")
            veryfi_client_secret = os.getenv("VERYFI_CLIENT_SECRET")
            veryfi_username      = os.getenv("VERYFI_USERNAME")
            veryfi_api_key       = os.getenv("VERYFI_API_KEY")

            if veryfi_api_key and veryfi_client_id:
                from veryfi import Client as VeryfiClient
                vclient = VeryfiClient(
                    client_id=veryfi_client_id,
                    client_secret=veryfi_client_secret,
                    username=veryfi_username,
                    api_key=veryfi_api_key
                )
                veryfi_raw = vclient.process_document(tmp_path)
                ocr_text = veryfi_raw.get("ocr_text", "") or ""
                raw_text_used = ocr_text

                if ocr_text.strip():
                    extracted = regex_extractor.extract(ocr_text)
                    de_result = {
                        "customer_name": extracted.customer_name.value or "",
                        "customer_phone": extracted.phone.value or "",
                        "delivery_address_raw": extracted.address_raw.value or "",
                        "street": "",
                        "number": extracted.number.value or "",
                        "complement": extracted.complement.value or "",
                        "neighborhood": extracted.neighborhood.value or "",
                        "city": extracted.city.value or "",
                        "state": extracted.state.value or "",
                        "zip_code": "",
                        "reference": extracted.reference.value or "",
                        "confidence": {
                            "customer_name": extracted.customer_name.confidence,
                            "customer_phone": extracted.phone.confidence,
                            "address": extracted.address_raw.confidence,
                            "overall": extracted.overall_confidence,
                        },
                        "evidence": {"customer_name_text": "", "phone_text": "", "address_text": ""},
                        "needs_human_review": extracted.precisa_revisao,
                        "auto_approve_logistics": extracted.overall_confidence >= 0.85,
                        "reason": [f"Gemini indisponível ({type(gemini_err).__name__}), usado Veryfi+regex"],
                    }
                    provider_used = "veryfi-roi+regex"

        except Exception as veryfi_err:
            logger.warning(f"[ROI] Veryfi também falhou ({veryfi_err})")

    # ── 3. Fallback final ─────────────────────────────────────────────────────
    if de_result is None:
        de_result = _build_empty_de()
        de_result["reason"] = ["Gemini e Veryfi indisponíveis. Revisão manual necessária."]
        provider_used = "roi-manual"

    # Limpa arquivo temporário
    try:
        os.unlink(tmp_path)
    except Exception:
        pass

    # ── Monta schema padronizado ──────────────────────────────────────────────
    normalized = {
        "provider": provider_used,
        "document_id": None,
        "image_id": image_id,
        "merchant": {"name": None, "cnpj": None, "address": None, "phone": None},
        "document": {"issue_date": None, "issue_time": None, "number": None},
        "customer": {
            "name": de_result.get("customer_name") or None,
            "phone": de_result.get("customer_phone") or None,
        },
        "delivery": {
            "address_raw": de_result.get("delivery_address_raw") or None,
            "street":       de_result.get("street") or None,
            "number":       de_result.get("number") or None,
            "complement":   de_result.get("complement") or None,
            "neighborhood": de_result.get("neighborhood") or None,
            "city":         de_result.get("city") or None,
            "state":        de_result.get("state") or None,
            "zip_code":     de_result.get("zip_code") or None,
            "reference":    de_result.get("reference") or None,
        },
        "items": [],
        "payment": {"total": None, "subtotal": None, "delivery_fee": None, "payment_method": None},
        "raw_text": raw_text_used or None,
        "delivery_extraction": de_result,
        "confidence": {"status": None, "score": None, "errors": [], "warnings": [],
                       "needs_human_review": de_result.get("needs_human_review", True)},
        "validation":  {"status": None, "score": None, "errors": [], "warnings": [],
                        "needs_human_review": de_result.get("needs_human_review", True)},
    }

    extraction = models.ReceiptExtraction(
        image_id=image_id,
        provider_id=provider_used,
        raw_json=de_result,
        normalized_json=normalized,
        status="roi_extracted"
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    return {"extraction_id": extraction.id, "provider": provider_used, "result": de_result}
