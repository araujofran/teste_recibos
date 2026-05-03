from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class ReceiptImage(Base):
    __tablename__ = "receipt_images"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    filename = Column(String, index=True)
    file_url = Column(String) # local path or S3 url
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    extractions = relationship("ReceiptExtraction", back_populates="image")
    ground_truths = relationship("ReceiptGroundTruth", back_populates="image")

class OcrProvider(Base):
    __tablename__ = "ocr_providers"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, unique=True, index=True) # e.g. 'mindee', 'veryfi'
    api_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

class ReceiptExtraction(Base):
    __tablename__ = "receipt_extractions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    image_id = Column(String, ForeignKey("receipt_images.id"))
    provider_id = Column(String, ForeignKey("ocr_providers.id"))
    raw_json = Column(JSON) # Original response from provider
    normalized_json = Column(JSON) # Standardized according to ReceiptStandardSchema
    extracted_at = Column(DateTime(timezone=True), server_default=func.now())
    
    image = relationship("ReceiptImage", back_populates="extractions")
    provider = relationship("OcrProvider")
    validation_result = relationship("ReceiptValidationResult", back_populates="extraction", uselist=False)

class ReceiptGroundTruth(Base):
    __tablename__ = "receipt_ground_truth"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    image_id = Column(String, ForeignKey("receipt_images.id"))
    manual_json = Column(JSON) # Standardized JSON format typed by human
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    image = relationship("ReceiptImage", back_populates="ground_truths")

class ReceiptValidationResult(Base):
    __tablename__ = "receipt_validation_results"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    extraction_id = Column(String, ForeignKey("receipt_extractions.id"), unique=True)
    ground_truth_id = Column(String, ForeignKey("receipt_ground_truth.id"), nullable=True)
    
    status = Column(String, default="pending") # pending, approved, needs_human_review, rejected
    score_overall = Column(Float, nullable=True)
    metrics_json = Column(JSON) # Field-by-field accuracy, errors, missing fields
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    extraction = relationship("ReceiptExtraction", back_populates="validation_result")
    ground_truth = relationship("ReceiptGroundTruth")

class DeliveryCandidate(Base):
    __tablename__ = "delivery_candidates"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    receipt_id = Column(String, ForeignKey("receipt_extractions.id")) # Refers to the approved extraction
    customer_name = Column(String)
    customer_phone = Column(String)
    address_raw = Column(String)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    order_value = Column(Float, nullable=True)
    
    status = Column(String, default="validated")
    route_ready = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
