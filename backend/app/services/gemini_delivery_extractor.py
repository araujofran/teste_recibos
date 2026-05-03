"""
GeminiDeliveryExtractor
=======================
Extrai dados de entrega a partir do raw_text OCR usando o Gemini como motor semântico.

Fluxo:
  raw_text (Veryfi/Mindee) → Gemini (extração semântica) → regex (validação) → score → revisão

Não depende de palavras-chave fixas.
Funciona com qualquer formato: iFood, Burger King, McDonald's, farmácia, mercado, pedido manual, etc.
"""

import os
import re
import json
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ─── Validadores Regex (usados APÓS extração do Gemini) ───────────────────────

PHONE_RE = re.compile(r'^\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}$')
CEP_RE   = re.compile(r'^\d{5}-?\d{3}$')
STATE_RE = re.compile(
    r'^(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)$'
)

CONFIDENCE_THRESHOLD = 0.70   # abaixo → needs_human_review = True
ADDRESS_AUTO_APPROVE  = 0.85  # acima → pode ir para logística

# ─── Prompt ───────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """
Você é um extrator especializado em dados de entrega de recibos e pedidos brasileiros.

Sua tarefa é analisar o texto OCR abaixo e extrair SOMENTE as informações relacionadas à entrega.

REGRAS OBRIGATÓRIAS:
1. Não dependa de palavras-chave fixas (ex: CLIENTE, ENDEREÇO, TELEFONE). Use contexto semântico.
2. Aceite qualquer formato: iFood, Burger King, McDonald's, farmácia, mercado, restaurante, pedido manual.
3. Não invente dados. Se não tiver certeza, deixe o campo vazio e reduza o confidence.
4. Nunca complete informações que não estão no texto.
5. Retorne EXCLUSIVAMENTE JSON válido, sem explicações.
6. Para confidence, use valores de 0.0 a 1.0.
7. Em "evidence", copie o trecho exato do texto que justifica cada campo.
8. Se endereço ou telefone tiver confidence < 0.7, adicione o motivo em "reason".
9. Se o endereço for do estabelecimento (não do cliente), ignore-o.
10. A entrega é para quem RECEBE o pedido, não quem vende.

SCHEMA DE SAÍDA:
{
  "customer_name": "",
  "customer_phone": "",
  "delivery_address_raw": "",
  "street": "",
  "number": "",
  "complement": "",
  "neighborhood": "",
  "city": "",
  "state": "",
  "zip_code": "",
  "reference": "",
  "confidence": {
    "customer_name": 0.0,
    "customer_phone": 0.0,
    "address": 0.0,
    "overall": 0.0
  },
  "evidence": {
    "customer_name_text": "",
    "phone_text": "",
    "address_text": ""
  },
  "needs_human_review": true,
  "reason": []
}

TEXTO OCR:
{{RAW_TEXT}}
""".strip()


# ─── Classe Principal ──────────────────────────────────────────────────────────

class GeminiDeliveryExtractor:
    """
    Extrai dados de entrega semanticamente via Gemini,
    depois valida com regex e calcula score final.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = "gemini-2.0-flash"

    def extract(self, raw_text: str, context: Optional[dict] = None) -> dict:
        """
        Parâmetros
        ----------
        raw_text : str
            Texto OCR bruto (retornado pela Veryfi/Mindee).
        context : dict, optional
            Dados financeiros já extraídos (merchant, total, etc.) para contexto adicional.

        Retorna
        -------
        dict com o schema padronizado + metadados de validação.
        """
        if not raw_text or not raw_text.strip():
            return self._empty_result(reason=["raw_text vazio ou ausente"])

        # 1. Extração semântica via Gemini
        gemini_result = self._call_gemini(raw_text)
        if "error" in gemini_result:
            # Fallback para regex simples se Gemini falhar
            logger.warning(f"Gemini falhou, usando fallback regex: {gemini_result['error']}")
            return self._regex_fallback(raw_text, reason=[f"Gemini indisponível: {gemini_result['error']}"])

        # 2. Validação com regex
        validated = self._validate_fields(gemini_result, raw_text)

        # 3. Decisão de revisão humana
        validated = self._compute_review_decision(validated)

        logger.info(
            f"[GeminiDeliveryExtractor] overall={validated['confidence']['overall']:.2f} "
            f"review={validated['needs_human_review']}"
        )
        return validated

    # ─── Chamada Gemini ────────────────────────────────────────────────────────
    def _call_gemini(self, raw_text: str) -> dict:
        if not self.api_key:
            return {"error": "GEMINI_API_KEY não configurada"}
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name)

            prompt = EXTRACTION_PROMPT.replace("{{RAW_TEXT}}", raw_text[:4000])  # limite de segurança

            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.0}  # máxima precisão
            )
            content = response.text.strip()

            # Limpar markdown se vier envolvido
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content.strip())

        except Exception as e:
            logger.error(f"Erro Gemini DeliveryExtractor: {e}")
            return {"error": str(e)}

    # ─── Validação com Regex ───────────────────────────────────────────────────
    def _validate_fields(self, data: dict, raw_text: str) -> dict:
        """Valida campos extraídos pelo Gemini com regex. Penaliza confidence se inválido."""

        # Telefone
        phone = (data.get("customer_phone") or "").strip()
        phone_digits = re.sub(r'\D', '', phone)
        if phone and not (10 <= len(phone_digits) <= 11):
            data["customer_phone"] = ""
            data["confidence"]["customer_phone"] = 0.0
            data.setdefault("reason", []).append(f"Telefone '{phone}' inválido (dígitos: {len(phone_digits)})")
        elif phone:
            # Formatar
            if len(phone_digits) == 11:
                data["customer_phone"] = f"({phone_digits[:2]}) {phone_digits[2:7]}-{phone_digits[7:]}"
            else:
                data["customer_phone"] = f"({phone_digits[:2]}) {phone_digits[2:6]}-{phone_digits[6:]}"

        # CEP
        cep = (data.get("zip_code") or "").strip()
        if cep and not CEP_RE.match(re.sub(r'\s', '', cep)):
            data["zip_code"] = ""

        # Estado
        state = (data.get("state") or "").strip().upper()
        if state and not STATE_RE.match(state):
            data["state"] = ""
        elif state:
            data["state"] = state

        # Endereço mínimo
        addr = (data.get("delivery_address_raw") or "").strip()
        if addr and len(addr) < 5:
            data["delivery_address_raw"] = ""
            data["confidence"]["address"] = 0.0
            data.setdefault("reason", []).append("Endereço muito curto — descartado")

        # Nome mínimo
        name = (data.get("customer_name") or "").strip()
        if name and len(name) < 2:
            data["customer_name"] = ""
            data["confidence"]["customer_name"] = 0.0

        return data

    # ─── Decisão de Revisão ────────────────────────────────────────────────────
    def _compute_review_decision(self, data: dict) -> dict:
        conf = data.get("confidence", {})
        phone_c   = conf.get("customer_phone", 0.0)
        address_c = conf.get("address", 0.0)
        name_c    = conf.get("customer_name", 0.0)
        overall   = conf.get("overall", (phone_c + address_c + name_c) / 3)

        conf["overall"] = round(overall, 2)
        data["confidence"] = conf

        reasons = data.get("reason") or []

        needs_review = False

        if not data.get("delivery_address_raw"):
            needs_review = True
            reasons.append("Endereço de entrega ausente")

        if not data.get("customer_phone"):
            needs_review = True
            reasons.append("Telefone ausente")

        if address_c < CONFIDENCE_THRESHOLD:
            needs_review = True
            reasons.append(f"Confiança do endereço baixa ({address_c:.0%})")

        if phone_c < CONFIDENCE_THRESHOLD and data.get("customer_phone"):
            needs_review = True
            reasons.append(f"Confiança do telefone baixa ({phone_c:.0%})")

        # Flag de aprovação automática para logística
        data["auto_approve_logistics"] = (
            address_c >= ADDRESS_AUTO_APPROVE
            and bool(data.get("delivery_address_raw"))
            and not needs_review
        )

        data["needs_human_review"] = needs_review
        data["reason"] = reasons
        return data

    # ─── Fallback Regex ────────────────────────────────────────────────────────
    def _regex_fallback(self, raw_text: str, reason: list) -> dict:
        """Extração mínima via regex quando o Gemini está indisponível."""
        result = self._empty_result(reason=reason)

        # Telefone
        m = re.search(r'(\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4})', raw_text)
        if m:
            result["customer_phone"] = m.group(1).strip()
            result["confidence"]["customer_phone"] = 0.50

        # Endereço: primeira ocorrência após linha do cliente/entrega
        lines = raw_text.split("\n")
        anchor_re = re.compile(r'(cliente|telefone|entrega|fone|hora\s*p)', re.IGNORECASE)
        addr_re   = re.compile(r'^(RUA|AV\.?|AVENIDA|TRAVESSA|ESTRADA|AL\.?|ALAMEDA)', re.IGNORECASE)
        after_anchor = False
        for line in lines:
            if anchor_re.search(line):
                after_anchor = True
            if after_anchor and addr_re.match(line.strip()):
                result["delivery_address_raw"] = line.strip()
                result["confidence"]["address"] = 0.40
                break

        result = self._compute_review_decision(result)
        return result

    # ─── Empty Result ─────────────────────────────────────────────────────────
    @staticmethod
    def _empty_result(reason: list = None) -> dict:
        return {
            "customer_name": "",
            "customer_phone": "",
            "delivery_address_raw": "",
            "street": "",
            "number": "",
            "complement": "",
            "neighborhood": "",
            "city": "",
            "state": "",
            "zip_code": "",
            "reference": "",
            "confidence": {
                "customer_name": 0.0,
                "customer_phone": 0.0,
                "address": 0.0,
                "overall": 0.0
            },
            "evidence": {
                "customer_name_text": "",
                "phone_text": "",
                "address_text": ""
            },
            "needs_human_review": True,
            "auto_approve_logistics": False,
            "reason": reason or []
        }


# Singleton
gemini_delivery_extractor = GeminiDeliveryExtractor()
