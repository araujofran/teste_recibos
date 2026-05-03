import os
import json
import time
import logging
import base64
import urllib3
import requests
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from collections import deque
from app.schemas import ReceiptStandardSchema, ItemSchema
from app.services.delivery_extractor import delivery_extractor
from app.services.gemini_delivery_extractor import gemini_delivery_extractor
from dotenv import load_dotenv

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


# ─── Rate Limiter ──────────────────────────────────────────────────────────────
class RateLimiter:
    """Controla quantas chamadas por minuto são feitas para cada provedor."""
    def __init__(self, max_calls: int, period_seconds: int = 60):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls = deque()

    def wait_if_needed(self):
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.period)
        while self.calls and self.calls[0] < cutoff:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            sleep_secs = (self.calls[0] - cutoff).total_seconds() + 1
            logger.warning(f"Rate limit atingido. Aguardando {sleep_secs:.1f}s...")
            time.sleep(sleep_secs)
        self.calls.append(now)

# Rate limiters por provedor
_rate_limiters = {
    "gemini": RateLimiter(max_calls=12, period_seconds=60),   # 15/min - margem de segurança
    "mindee": RateLimiter(max_calls=30, period_seconds=60),
    "veryfi": RateLimiter(max_calls=30, period_seconds=60),
}

# ─── Exponential Backoff ───────────────────────────────────────────────────────
def with_retry(func, max_retries=3, base_delay=5):
    """Executa função com retry e exponential backoff em caso de 429."""
    for attempt in range(max_retries):
        result = func()
        if isinstance(result, dict) and result.get("_quota_exceeded"):
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning(f"Quota 429 - tentativa {attempt+1}/{max_retries}. Aguardando {wait}s...")
                time.sleep(wait)
            else:
                return {"error": "quota_exceeded", "status": "quota_exceeded"}
        else:
            return result
    return {"error": "quota_exceeded", "status": "quota_exceeded"}

# ─── Interface Base ─────────────────────────────────────────────────────────────
class ReceiptProviderInterface(ABC):
    name = "base"

    @abstractmethod
    def extract_receipt(self, file_path: str) -> dict:
        pass

    @abstractmethod
    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        pass

    def _normalize_error(self, raw_data: dict, provider: str) -> ReceiptStandardSchema:
        schema = ReceiptStandardSchema()
        schema.provider = provider
        err = raw_data.get("error", "desconhecido")
        if raw_data.get("status") == "quota_exceeded":
            schema.merchant.name = "⚠️ QUOTA ESGOTADA — tente outro provedor"
        else:
            schema.merchant.name = f"ERRO: {str(err)[:80]}"
        return schema

# ─── Google Gemini ─────────────────────────────────────────────────────────────
class GeminiProvider(ReceiptProviderInterface):
    name = "gemini"

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = "gemini-2.0-flash"
        self.limiter = _rate_limiters["gemini"]

    def _call_api(self, file_path: str) -> dict:
        import google.generativeai as genai
        self.limiter.wait_if_needed()

        genai.configure(api_key=self.api_key)

        with open(file_path, "rb") as f:
            image_bytes = f.read()

        # Redimensionar se muito grande (> 1MB) para economizar tokens
        if len(image_bytes) > 1_000_000:
            try:
                import io
                from PIL import Image
                img = Image.open(io.BytesIO(image_bytes))
                img.thumbnail((1200, 1200))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                image_bytes = buf.getvalue()
                logger.info(f"Imagem redimensionada: {len(image_bytes)/1024:.0f}KB")
            except Exception:
                pass  # usa original se PIL falhar

        ext = file_path.lower().split(".")[-1]
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/jpeg")

        model = genai.GenerativeModel(self.model)
        image_part = {"mime_type": mime_type, "data": image_bytes}

        prompt = """
Você é um especialista em leitura de recibos/cupons fiscais brasileiros.
Analise esta imagem e extraia TODOS os dados visíveis.
Retorne APENAS um JSON com exatamente esta estrutura (sem explicações, só o JSON):

{
  "merchant": {
    "name": "nome do estabelecimento",
    "cnpj": "cnpj se visível",
    "address": "endereço do estabelecimento"
  },
  "document": {
    "number": "número do pedido",
    "issue_date": "YYYY-MM-DD",
    "issue_time": "HH:MM"
  },
  "payment": {
    "subtotal": 0.0,
    "delivery_fee": 0.0,
    "total": 0.0,
    "payment_method": "forma de pagamento"
  },
  "items": [
    {
      "description": "nome do item",
      "quantity": 1,
      "unit_price": 0.0,
      "total_price": 0.0
    }
  ],
  "delivery": {
    "address_raw": "endereço completo de entrega",
    "customer_name": "nome do cliente",
    "customer_phone": "telefone do cliente"
  }
}
"""
        response = model.generate_content([prompt, image_part])
        content = response.text.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content.strip())

    def extract_receipt(self, file_path: str) -> dict:
        if not self.api_key:
            return {"error": "GEMINI_API_KEY não configurada no .env"}
        try:
            return with_retry(lambda: self._try_extract(file_path))
        except Exception as e:
            logger.error(f"Erro Gemini: {str(e)}")
            return {"error": str(e)}

    def _try_extract(self, file_path: str) -> dict:
        try:
            return self._call_api(file_path)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str:
                logger.warning("Gemini 429 detectado.")
                return {"_quota_exceeded": True}
            raise

    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        if "error" in raw_data or "_quota_exceeded" in raw_data:
            return self._normalize_error(raw_data, "gemini")

        schema = ReceiptStandardSchema()
        schema.provider = "gemini"

        merchant = raw_data.get("merchant", {})
        schema.merchant.name = merchant.get("name")
        schema.merchant.cnpj = merchant.get("cnpj")
        schema.merchant.address = merchant.get("address")

        doc = raw_data.get("document", {})
        schema.document.issue_date = doc.get("issue_date")
        schema.document.issue_time = doc.get("issue_time")
        schema.document.number = doc.get("number")

        payment = raw_data.get("payment", {})
        try:
            schema.payment.total = float(payment.get("total") or 0.0)
            schema.payment.subtotal = float(payment.get("subtotal") or 0.0)
            schema.payment.delivery_fee = float(payment.get("delivery_fee") or 0.0)
            schema.payment.payment_method = payment.get("payment_method")
        except Exception:
            pass

        schema.delivery.address_raw = raw_data.get("delivery", {}).get("address_raw")

        for item in raw_data.get("items", []):
            try:
                schema.items.append(ItemSchema(
                    description=item.get("description"),
                    quantity=float(item.get("quantity") or 1.0),
                    unit_price=float(item.get("unit_price") or 0.0),
                    total_price=float(item.get("total_price") or 0.0)
                ))
            except Exception:
                continue

        return schema

# ─── Mindee ─────────────────────────────────────────────────────────────────
class MindeeProvider(ReceiptProviderInterface):
    name = "mindee"

    def __init__(self):
        self.api_key = os.getenv("MINDEE_API_KEY")

    def extract_receipt(self, file_path: str) -> dict:
        if not self.api_key:
            return {"error": "MINDEE_API_KEY não configurada"}
        url = "https://api.mindee.net/v1/products/mindee/expense_receipts/v5/predict"
        headers = {"Authorization": f"Token {self.api_key}"}
        with open(file_path, "rb") as f:
            response = requests.post(url, headers=headers, files={"document": f})
            return response.json()

    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        if "error" in raw_data:
            return self._normalize_error(raw_data, "mindee")
        schema = ReceiptStandardSchema()
        schema.provider = "mindee"
        prediction = raw_data.get("document", {}).get("inference", {}).get("prediction", {})
        schema.merchant.name = prediction.get("merchant_name", {}).get("value")
        schema.document.issue_date = prediction.get("date", {}).get("value")
        schema.payment.total = prediction.get("total_amount", {}).get("value")
        for item in prediction.get("line_items", []):
            schema.items.append(ItemSchema(
                description=item.get("description"),
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                total_price=item.get("total_amount")
            ))
        return schema

# ─── Veryfi ──────────────────────────────────────────────────────────────────
class VeryfiProvider(ReceiptProviderInterface):
    name = "veryfi"

    def __init__(self):
        self.client_id = os.getenv("VERYFI_CLIENT_ID")
        self.username = os.getenv("VERYFI_USERNAME")
        self.api_key = os.getenv("VERYFI_API_KEY")
        self.base_url = "https://api.veryfi.com/api/v8/partner"

    def extract_receipt(self, file_path: str) -> dict:
        if not self.api_key or not self.client_id:
            return {"error": "Veryfi: configure VERYFI_CLIENT_ID, VERYFI_USERNAME e VERYFI_API_KEY no .env"}
        try:
            from veryfi import Client as VeryfiClient
            client = VeryfiClient(
                client_id=self.client_id,
                client_secret=os.getenv("VERYFI_CLIENT_SECRET", ""),
                username=self.username,
                api_key=self.api_key
            )
            result = client.process_document(file_path)
            return result
        except Exception as e:
            logger.error(f"Erro Veryfi: {str(e)}")
            return {"error": str(e)}


    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        if "error" in raw_data:
            return self._normalize_error(raw_data, "veryfi")

        schema = ReceiptStandardSchema()
        schema.provider = "veryfi"

        vendor = raw_data.get("vendor", {})
        schema.merchant.name = vendor.get("name") or raw_data.get("vendor_name")
        schema.merchant.cnpj = vendor.get("vat_number") or raw_data.get("tax_number")
        schema.merchant.address = vendor.get("address") or raw_data.get("vendor_address")

        schema.document.issue_date = raw_data.get("date")
        schema.document.number = str(raw_data.get("invoice_number") or "")

        schema.payment.total = raw_data.get("total")
        schema.payment.subtotal = raw_data.get("subtotal")
        schema.payment.delivery_fee = raw_data.get("shipping")
        schema.payment.payment_method = raw_data.get("payment", {}).get("type")

        for item in raw_data.get("line_items", []):
            try:
                schema.items.append(ItemSchema(
                    description=item.get("description") or item.get("name"),
                    quantity=float(item.get("quantity") or 1.0),
                    unit_price=float(item.get("price") or item.get("unit_price") or 0.0),
                    total_price=float(item.get("total") or 0.0)
                ))
            except Exception:
                continue

        # ── Segunda camada: GeminiDeliveryExtractor (semântico) ─────────────────
        ocr_text = raw_data.get("ocr_text", "") or ""
        schema.raw_text = ocr_text
        if ocr_text:
            context = {
                "merchant": schema.merchant.name,
                "total": schema.payment.total,
            }
            de = gemini_delivery_extractor.extract(ocr_text, context=context)
            schema.delivery_extraction = de

            # Propaga campos para o schema principal
            if de.get("customer_name") and not schema.customer.name:
                schema.customer.name = de["customer_name"]
            if de.get("customer_phone") and not schema.customer.phone:
                schema.customer.phone = de["customer_phone"]
            if de.get("delivery_address_raw") and not schema.delivery.address_raw:
                schema.delivery.address_raw = de["delivery_address_raw"]
            if de.get("neighborhood"):
                schema.delivery.neighborhood = de["neighborhood"]
            if de.get("city"):
                schema.delivery.city = de["city"]
            if de.get("state"):
                schema.delivery.state = de["state"]
            if de.get("zip_code"):
                schema.delivery.zip_code = de["zip_code"]

            # Decisão de revisão humana
            if de.get("needs_human_review"):
                schema.validation.needs_human_review = True
                for r in de.get("reason", []):
                    schema.validation.warnings.append(r)

        return schema




# ─── Mock ─────────────────────────────────────────────────────────────────────
class MockReceiptProvider(ReceiptProviderInterface):
    name = "mock"

    def extract_receipt(self, file_path: str) -> dict:
        return {
            "merchant": {"name": "Mock Mercadinho", "cnpj": "12.345.678/0001-90"},
            "document": {"issue_date": "2026-05-03"},
            "payment": {"total": 50.00, "subtotal": 50.00},
            "items": [
                {"description": "BOLO DE AIPIM", "quantity": 1.0, "unit_price": 20.00, "total_price": 20.00},
                {"description": "SUCO DE LARANJA", "quantity": 2.0, "unit_price": 15.00, "total_price": 30.00}
            ],
            "delivery": {"address_raw": "Rua das Flores, 123"}
        }

    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        schema = ReceiptStandardSchema()
        schema.provider = "mock"
        m = raw_data.get("merchant", {})
        schema.merchant.name = m.get("name")
        schema.merchant.cnpj = m.get("cnpj")
        schema.document.issue_date = raw_data.get("document", {}).get("issue_date")
        schema.payment.total = raw_data.get("payment", {}).get("total")
        schema.delivery.address_raw = raw_data.get("delivery", {}).get("address_raw")
        for item in raw_data.get("items", []):
            schema.items.append(ItemSchema(
                description=item.get("description"),
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                total_price=item.get("total_price")
            ))
        return schema

# ─── Fallback Chain ───────────────────────────────────────────────────────────
class FallbackChainProvider(ReceiptProviderInterface):
    """
    Tenta provedores em ordem. Se um falha com 429 ou erro, tenta o próximo.
    Ordem: Mindee → Veryfi → Gemini → Mock
    """
    name = "auto"

    def __init__(self):
        self.chain = [VeryfiProvider(), MindeeProvider(), GeminiProvider(), MockReceiptProvider()]

    def extract_receipt(self, file_path: str) -> dict:
        for provider in self.chain:
            try:
                result = provider.extract_receipt(file_path)
                if "error" not in result and "_quota_exceeded" not in result:
                    result["_used_provider"] = provider.name
                    logger.info(f"✅ Extração bem-sucedida com: {provider.name}")
                    return result
                logger.warning(f"⚠️ {provider.name} falhou: {result.get('error', 'quota')}. Tentando próximo...")
            except Exception as e:
                logger.warning(f"⚠️ {provider.name} excepção: {e}. Tentando próximo...")
        return {"error": "Todos os provedores falharam", "_used_provider": "none"}

    def normalize(self, raw_data: dict) -> ReceiptStandardSchema:
        used = raw_data.get("_used_provider", "mock")
        provider_map = {p.name: p for p in self.chain}
        provider = provider_map.get(used, MockReceiptProvider())
        return provider.normalize(raw_data)

# ─── Factory ──────────────────────────────────────────────────────────────────
def get_receipt_provider(provider_name: str) -> ReceiptProviderInterface:
    providers = {
        "mock": MockReceiptProvider,
        "gemini": GeminiProvider,
        "veryfi": VeryfiProvider,
        "mindee": MindeeProvider,
        "auto": FallbackChainProvider,
    }
    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Provider '{provider_name}' not supported.")
    return provider_class()
