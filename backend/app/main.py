from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
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
    from .services.ocr_service import get_ocr_provider
    import json
    
    image = db.query(models.ReceiptImage).filter(models.ReceiptImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
        
    ocr = get_ocr_provider(provider)
    
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

@app.post("/ground_truth/")
def save_ground_truth(image_id: str, manual_json: dict, db: Session = Depends(get_db)):
    image = db.query(models.ReceiptImage).filter(models.ReceiptImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
        
    gt = models.ReceiptGroundTruth(
        image_id=image_id,
        manual_json=manual_json
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


