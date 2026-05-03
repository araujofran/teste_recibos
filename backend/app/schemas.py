from pydantic import BaseModel, Field
from typing import List, Optional

class MerchantSchema(BaseModel):
    name: Optional[str] = None
    cnpj: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None

class DocumentSchema(BaseModel):
    type: Optional[str] = None
    number: Optional[str] = None
    issue_date: Optional[str] = None
    issue_time: Optional[str] = None
    access_key: Optional[str] = None
    qr_code_url: Optional[str] = None

class CustomerSchema(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    reference: Optional[str] = None

class DeliverySchema(BaseModel):
    address_raw: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geocode_confidence: Optional[float] = None

class ItemSchema(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    confidence: Optional[float] = None

class PaymentSchema(BaseModel):
    subtotal: Optional[float] = None
    discount: Optional[float] = None
    delivery_fee: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    payment_method: Optional[str] = None

class ConfidenceSchema(BaseModel):
    overall: Optional[float] = None
    merchant: Optional[float] = None
    items: Optional[float] = None
    total: Optional[float] = None
    address: Optional[float] = None

class ValidationSchema(BaseModel):
    status: Optional[str] = None
    score: Optional[float] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    needs_human_review: bool = False

class ReceiptStandardSchema(BaseModel):
    document_id: Optional[str] = None
    image_id: Optional[str] = None
    provider: Optional[str] = None
    merchant: MerchantSchema = Field(default_factory=MerchantSchema)
    document: DocumentSchema = Field(default_factory=DocumentSchema)
    customer: CustomerSchema = Field(default_factory=CustomerSchema)
    delivery: DeliverySchema = Field(default_factory=DeliverySchema)
    items: List[ItemSchema] = Field(default_factory=list)
    payment: PaymentSchema = Field(default_factory=PaymentSchema)
    raw_text: Optional[str] = None
    confidence: ConfidenceSchema = Field(default_factory=ConfidenceSchema)
    validation: ValidationSchema = Field(default_factory=ValidationSchema)
    delivery_extraction: Optional[dict] = None   # resultado do DeliveryDataExtractor


class GroundTruthCreate(BaseModel):
    image_id: str
    manual_json: dict

