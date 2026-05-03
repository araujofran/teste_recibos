import os
from abc import ABC, abstractmethod
from app.schemas import ReceiptStandardSchema
import json
import logging

logger = logging.getLogger(__name__)

class OcrProviderInterface(ABC):
    @abstractmethod
    def extract_receipt(self, file_path: str) -> dict:
        """Extract receipt raw data from the provider API."""
        pass
        
    @abstractmethod
    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        """Convert provider's raw data into the standard ReceiptStandardSchema."""
        pass


class MockOcrProvider(OcrProviderInterface):
    """A mock provider for laboratory testing without hitting real APIs."""
    
    def extract_receipt(self, file_path: str) -> dict:
        return {
            "vendor": "Mock Mercadinho",
            "cnpj": "12.345.678/0001-90",
            "date": "2026-05-03",
            "total": 50.00,
            "line_items": [
                {"description": "BOLO DE AIPIM", "qty": 1.0, "unit_price": 20.00, "total": 20.00},
                {"description": "SUCO DE LARANJA", "qty": 2.0, "unit_price": 15.00, "total": 30.00}
            ],
            "delivery_addr": "Rua das Flores, 123"
        }
        
    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        schema = ReceiptStandardSchema()
        schema.provider = "mock"
        schema.merchant.name = raw_data.get("vendor")
        schema.merchant.cnpj = raw_data.get("cnpj")
        schema.document.issue_date = raw_data.get("date")
        schema.payment.total = raw_data.get("total")
        schema.delivery.address_raw = raw_data.get("delivery_addr")
        
        for item in raw_data.get("line_items", []):
            schema.items.append({
                "description": item.get("description"),
                "quantity": item.get("qty"),
                "unit_price": item.get("unit_price"),
                "total_price": item.get("total")
            })
            
        return schema

# Factory for OCR Providers
def get_ocr_provider(provider_name: str) -> OcrProviderInterface:
    if provider_name.lower() == "mock":
        return MockOcrProvider()
    # elif provider_name.lower() == "mindee":
    #     return MindeeOcrProvider()
    raise ValueError(f"Provider {provider_name} not supported.")
