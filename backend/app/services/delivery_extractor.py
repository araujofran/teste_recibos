"""
DeliveryDataExtractor
=====================
Módulo responsável por extrair dados de entrega a partir do raw_text OCR.

Arquitetura híbrida:
  1. Regex  → telefone, CEP, padrões numéricos simples
  2. Heurística contextual → linhas próximas de palavras-chave
  3. Normalização → capitalização, formatação de telefone
  4. Score de confiança por campo (0.0 – 1.0)
  5. Flag precisa_revisao se confiança insuficiente
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6  # abaixo disso → precisa_revisao


@dataclass
class DeliveryField:
    value: Optional[str] = None
    confidence: float = 0.0
    source: str = "not_found"   # "regex", "heuristic", "llm", "manual"

    def as_dict(self):
        return {
            "value": self.value,
            "confidence": round(self.confidence, 2),
            "source": self.source,
        }


@dataclass
class DeliveryExtractionResult:
    customer_name: DeliveryField = field(default_factory=DeliveryField)
    phone: DeliveryField = field(default_factory=DeliveryField)
    address_raw: DeliveryField = field(default_factory=DeliveryField)
    street: DeliveryField = field(default_factory=DeliveryField)
    number: DeliveryField = field(default_factory=DeliveryField)
    neighborhood: DeliveryField = field(default_factory=DeliveryField)
    city: DeliveryField = field(default_factory=DeliveryField)
    state: DeliveryField = field(default_factory=DeliveryField)
    complement: DeliveryField = field(default_factory=DeliveryField)
    reference: DeliveryField = field(default_factory=DeliveryField)
    delivery_time: DeliveryField = field(default_factory=DeliveryField)
    precisa_revisao: bool = False
    overall_confidence: float = 0.0

    def compute_flags(self):
        key_fields = [self.customer_name, self.phone, self.address_raw]
        scores = [f.confidence for f in key_fields]
        self.overall_confidence = round(sum(scores) / len(scores), 2)
        self.precisa_revisao = self.overall_confidence < CONFIDENCE_THRESHOLD or \
                               self.address_raw.value is None or \
                               self.phone.value is None

    def as_dict(self):
        return {
            "customer_name": self.customer_name.as_dict(),
            "phone": self.phone.as_dict(),
            "address_raw": self.address_raw.as_dict(),
            "street": self.street.as_dict(),
            "number": self.number.as_dict(),
            "neighborhood": self.neighborhood.as_dict(),
            "city": self.city.as_dict(),
            "state": self.state.as_dict(),
            "complement": self.complement.as_dict(),
            "reference": self.reference.as_dict(),
            "delivery_time": self.delivery_time.as_dict(),
            "precisa_revisao": self.precisa_revisao,
            "overall_confidence": self.overall_confidence,
        }


# ─── Padrões Regex ────────────────────────────────────────────────────────────

PHONE_PATTERN = re.compile(
    r'(\(?\d{2}\)?\s*(?:9\s?)?\d{4}[-\s]?\d{4})'
)

CEP_PATTERN = re.compile(r'\d{5}-?\d{3}')

STATE_PATTERN = re.compile(
    r'\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b'
)

TIME_PATTERN = re.compile(
    r'(?:hora.*?entrega|entrega.*?hora|hrs?\.?|horário)[:\s]*(\d{1,2}:\d{2})',
    re.IGNORECASE
)

ADDRESS_PREFIXES = re.compile(
    r'^(RUA|R\.|AV\.?|AVENIDA|TRAVESSA|TV\.?|ESTRADA|ROD\.?|RODOVIA|AL\.?|ALAMEDA|PC\.?|PRAÇA|BL\.?|BLOCO)',
    re.IGNORECASE
)

# Palavras-chave que precedem o nome do cliente
CUSTOMER_KEYWORDS = re.compile(
    r'(?:cliente|nome|customer|comprador)[:\s]+(.{2,50})',
    re.IGNORECASE
)

# Palavras-chave que precedem telefone
PHONE_KEYWORDS = re.compile(
    r'(?:fone|tel\.?|telefone|celular|whatsapp|cel\.?)[:\s]+(.+)',
    re.IGNORECASE
)

# Palavras-chave que precedem endereço
ADDRESS_KEYWORDS = re.compile(
    r'(?:endereço|endere[cç]o|entrega|delivery|local)[:\s]+(.+)',
    re.IGNORECASE
)

# Complemento
COMPLEMENT_PATTERN = re.compile(
    r'\b(apto?\.?|apartamento|bloco|bl\.?|casa|cs\.?|sala|andar|ap\.?)\s*[\d\w-]+',
    re.IGNORECASE
)

# Referência
REFERENCE_KEYWORDS = re.compile(
    r'(?:refer[eê]ncia|próximo|perto|ao lado|em frente)[:\s]+(.+)',
    re.IGNORECASE
)


class DeliveryDataExtractor:
    """
    Extrai dados de entrega de texto OCR bruto usando abordagem híbrida.
    """

    def extract(self, raw_text: str) -> DeliveryExtractionResult:
        result = DeliveryExtractionResult()
        if not raw_text:
            result.precisa_revisao = True
            return result

        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

        self._extract_phone(raw_text, lines, result)
        self._extract_customer_name(raw_text, lines, result)
        self._extract_address(raw_text, lines, result)
        self._extract_delivery_time(raw_text, result)
        self._extract_complement(raw_text, result)
        self._extract_reference(raw_text, result)

        result.compute_flags()
        logger.info(
            f"[DeliveryExtractor] confiança={result.overall_confidence:.2f} "
            f"revisao={result.precisa_revisao}"
        )
        return result

    # ─── Telefone ─────────────────────────────────────────────────────────────
    def _extract_phone(self, text: str, lines: list, result: DeliveryExtractionResult):
        # 1. Keyword explícita (ex: "Tel: (11) 9xxx-xxxx")
        m = PHONE_KEYWORDS.search(text)
        if m:
            phone_candidate = PHONE_PATTERN.search(m.group(1))
            if phone_candidate:
                result.phone = DeliveryField(
                    value=self._format_phone(phone_candidate.group(1)),
                    confidence=0.95,
                    source="heuristic"
                )
                return

        # 2. Regex direta no texto
        matches = PHONE_PATTERN.findall(text)
        if matches:
            # Pega o primeiro que parece ser celular (9 dígitos) ou fixo
            phones = [self._format_phone(p) for p in matches]
            result.phone = DeliveryField(
                value=phones[0],
                confidence=0.80,
                source="regex"
            )

    # ─── Nome do Cliente ──────────────────────────────────────────────────────
    def _extract_customer_name(self, text: str, lines: list, result: DeliveryExtractionResult):
        # 1. Keyword explícita
        m = CUSTOMER_KEYWORDS.search(text)
        if m:
            name = m.group(1).strip().split("\n")[0].strip()
            # Limpa telefones misturados no nome
            name = PHONE_PATTERN.sub("", name).strip()
            if 2 < len(name) < 60:
                result.customer_name = DeliveryField(
                    value=name.title(),
                    confidence=0.90,
                    source="heuristic"
                )
                return

        # 2. Heurística: linha após "Pedido:" geralmente tem cliente
        for i, line in enumerate(lines):
            if re.search(r'\bpedido\b', line, re.IGNORECASE) and i + 1 < len(lines):
                candidate = lines[i + 1]
                # Candidato não é endereço nem telefone
                if not ADDRESS_PREFIXES.match(candidate) and not PHONE_PATTERN.search(candidate):
                    if 2 < len(candidate) < 50:
                        result.customer_name = DeliveryField(
                            value=candidate.title(),
                            confidence=0.55,
                            source="heuristic"
                        )
                        return

    # ─── Endereço ─────────────────────────────────────────────────────────────
    def _extract_address(self, text: str, lines: list, result: DeliveryExtractionResult):
        """
        Estratégia:
        1. Encontra a linha-âncora de entrega (Hora p/Entrega, Cliente, Telefone).
        2. Busca endereços SOMENTE abaixo dessa âncora → evita capturar o endereço do estabelecimento.
        3. Fallback: keyword explícita "Endereço:", "Entrega:".
        4. Último recurso: segunda ocorrência de logradouro no texto.
        """

        # ── 1. Encontrar índice da âncora de entrega ──────────────────────────
        anchor_idx = None
        anchor_patterns = re.compile(
            r'(hora\s*p[/.]?\s*entrega|cliente\s*:|telefone\s*:|celular\s*:|fone\s*:)',
            re.IGNORECASE
        )
        for i, line in enumerate(lines):
            if anchor_patterns.search(line):
                anchor_idx = i
                break

        # ── 2. Buscar endereço ABAIXO da âncora ───────────────────────────────
        search_lines = lines[anchor_idx:] if anchor_idx is not None else lines

        for i, line in enumerate(search_lines):
            if ADDRESS_PREFIXES.match(line):
                addr = line
                # Concatena próxima linha se parece complemento / bairro / cidade
                if i + 1 < len(search_lines):
                    next_l = search_lines[i + 1].strip()
                    if (not ADDRESS_PREFIXES.match(next_l)
                            and len(next_l) < 80
                            and re.search(r'(SP|RJ|MG|bairro|jardim|parque|vila|centro|rafael|pirani)', next_l, re.IGNORECASE)):
                        addr = f"{addr}, {next_l}"
                result.address_raw = DeliveryField(value=addr.strip(), confidence=0.88, source="heuristic")
                self._parse_address_parts(addr, lines, text, result)
                return

        # ── 3. Keyword explícita em qualquer posição ───────────────────────────
        m = ADDRESS_KEYWORDS.search(text)
        if m:
            addr = m.group(1).strip().split("\n")[0].strip()
            if len(addr) > 5:
                result.address_raw = DeliveryField(value=addr, confidence=0.85, source="heuristic")
                self._parse_address_parts(addr, lines, text, result)
                return

        # ── 4. Último recurso: segunda ocorrência de logradouro ───────────────
        occurrences = [line for line in lines if ADDRESS_PREFIXES.match(line)]
        if len(occurrences) >= 2:
            addr = occurrences[1]   # pula o endereço do estabelecimento (1ª ocorrência)
            result.address_raw = DeliveryField(value=addr.strip(), confidence=0.55, source="heuristic")
            self._parse_address_parts(addr, lines, text, result)


    def _parse_address_parts(self, addr: str, lines: list, text: str, result: DeliveryExtractionResult):
        # Número
        m = re.search(r',?\s*(\d+(?:\s*[A-Za-z])?)\b', addr)
        if m:
            result.number = DeliveryField(value=m.group(1).strip(), confidence=0.75, source="regex")

        # Estado
        m = STATE_PATTERN.search(addr) or STATE_PATTERN.search(text)
        if m:
            result.state = DeliveryField(value=m.group(1).upper(), confidence=0.90, source="regex")

        # CEP
        m = CEP_PATTERN.search(addr) or CEP_PATTERN.search(text)
        if m:
            result.complement = DeliveryField(value=m.group(0), confidence=0.95, source="regex")

        # Bairro (heurística: última parte após vírgula que não é número/estado)
        parts = [p.strip() for p in re.split(r'[-,]', addr) if p.strip()]
        if len(parts) >= 3:
            bairro_candidate = parts[-2] if STATE_PATTERN.search(parts[-1]) else parts[-1]
            if not bairro_candidate.isdigit() and len(bairro_candidate) > 2:
                result.neighborhood = DeliveryField(
                    value=bairro_candidate.title(),
                    confidence=0.60,
                    source="heuristic"
                )

        # Cidade (linha separada buscando SP/RJ/etc)
        for line in lines:
            if STATE_PATTERN.search(line):
                city_m = re.match(r'^([A-ZÀ-Ú\s]+?)(?:\s*[-–]\s*' + STATE_PATTERN.pattern + r')?$', line, re.IGNORECASE)
                if city_m:
                    result.city = DeliveryField(
                        value=city_m.group(1).strip().title(),
                        confidence=0.65,
                        source="heuristic"
                    )
                    break

    # ─── Hora de Entrega ──────────────────────────────────────────────────────
    def _extract_delivery_time(self, text: str, result: DeliveryExtractionResult):
        m = TIME_PATTERN.search(text)
        if m:
            result.delivery_time = DeliveryField(value=m.group(1), confidence=0.90, source="regex")
        else:
            # Heurística: "22:57", "21:15" isolado próximo a "entrega"
            m2 = re.search(r'\b(\d{1,2}:\d{2})\b', text)
            if m2:
                result.delivery_time = DeliveryField(value=m2.group(1), confidence=0.50, source="heuristic")

    # ─── Complemento ──────────────────────────────────────────────────────────
    def _extract_complement(self, text: str, result: DeliveryExtractionResult):
        m = COMPLEMENT_PATTERN.search(text)
        if m:
            result.complement = DeliveryField(value=m.group(0).strip(), confidence=0.75, source="regex")

    # ─── Referência ───────────────────────────────────────────────────────────
    def _extract_reference(self, text: str, result: DeliveryExtractionResult):
        m = REFERENCE_KEYWORDS.search(text)
        if m:
            result.reference = DeliveryField(value=m.group(1).strip(), confidence=0.85, source="heuristic")

    # ─── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _format_phone(raw: str) -> str:
        digits = re.sub(r'\D', '', raw)
        if len(digits) == 11:
            return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
        elif len(digits) == 10:
            return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
        return raw.strip()


# Singleton
delivery_extractor = DeliveryDataExtractor()
