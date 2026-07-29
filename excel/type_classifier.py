import re
from datetime import datetime
from decimal import Decimal
from .models import CellType

class TypeClassifier:
    """Clasifica el contenido de una celda en un tipo semántico."""

    # Patrones para números con formato local (argentino, europeo, americano)
    NUMBER_PATTERNS = [
        re.compile(r'^[+-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?$'),           # 1.234.567,89
        re.compile(r'^[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?$'),           # 1,234,567.89
        re.compile(r'^[+-]?\d+(?:[.,]\d+)?$'),                        # 1234.56 o 1234,56
        re.compile(r'^\$?\d+(?:[.,]\d+)?$'),                          # $1234.56
        re.compile(r'^\d+(?:[.,]\d+)?%$'),                            # 21% o 21,5%
    ]

    # Patrones de fecha (simplificados)
    DATE_PATTERNS = [
        re.compile(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$'),               # 12/12/2024
        re.compile(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2}$'),                # 12/12/24
    ]

    # Patrones de booleanos
    BOOLEAN_TRUE = re.compile(r'^(true|yes|sí|si|1)$', re.IGNORECASE)
    BOOLEAN_FALSE = re.compile(r'^(false|no|0)$', re.IGNORECASE)

    # Patrones de error
    ERROR_PATTERNS = [
        re.compile(r'^#\w+!?$'),  # #N/A, #VALUE!, etc.
    ]

    @classmethod
    def classify(cls, value) -> CellType:
        """Clasifica el valor de una celda."""
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return CellType.EMPTY

        # Si es un booleano de Python
        if isinstance(value, bool):
            return CellType.BOOLEAN

        # Si es un número (int o float)
        if isinstance(value, (int, float)):
            return CellType.NUMBER

        # Si es fecha
        if isinstance(value, datetime):
            return CellType.DATE

        # Si es string, analizar contenido
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == '':
                return CellType.EMPTY

            # Error
            for pat in cls.ERROR_PATTERNS:
                if pat.match(stripped):
                    return CellType.ERROR

            # Fecha
            for pat in cls.DATE_PATTERNS:
                if pat.match(stripped):
                    return CellType.DATE

            # Número (moneda, porcentaje)
            for pat in cls.NUMBER_PATTERNS:
                if pat.match(stripped):
                    return CellType.NUMBER

            # Booleano
            if cls.BOOLEAN_TRUE.match(stripped) or cls.BOOLEAN_FALSE.match(stripped):
                return CellType.BOOLEAN

            # Si comienza con '=' es fórmula (pero openpyxl en read_only devuelve None o el valor calculado)
            if stripped.startswith('='):
                return CellType.FORMULA

            # Texto por defecto
            return CellType.TEXT

        # Otros (objetos, etc.) lo tratamos como texto
        return CellType.TEXT

    @classmethod
    def is_number_like(cls, value) -> bool:
        """Comprueba si el valor es numérico o parece un número (para validación de precios)."""
        cell_type = cls.classify(value)
        if cell_type == CellType.NUMBER:
            return True
        if isinstance(value, str):
            # Intentar limpiar formato y convertir a float
            cleaned = cls._clean_number_string(value)
            if cleaned is not None:
                try:
                    float(cleaned)
                    return True
                except ValueError:
                    pass
        return False

    @classmethod
    def _clean_number_string(cls, s: str) -> Optional[str]:
        """Limpia un string para intentar convertirlo a número."""
        s = s.strip()
        if not s:
            return None
        # Eliminar símbolo de moneda
        s = re.sub(r'^[\$€£¥]', '', s)
        # Eliminar espacios
        s = re.sub(r'\s', '', s)
        # Si termina en %, quitar %
        s = re.sub(r'%$', '', s)
        # Detectar formato europeo (última coma como decimal)
        if ',' in s and '.' in s:
            # Si el punto aparece antes que la coma, es europeo (1.234,56)
            if s.rfind('.') < s.rfind(','):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s and '.' not in s:
            # Solo comas: si hay más de una, son separadores de miles
            if s.count(',') > 1:
                s = s.replace(',', '')
            else:
                # Una sola coma: es decimal (1,5)
                s = s.replace(',', '.')
        # Si tiene puntos como separadores de miles (1.234.567)
        if '.' in s and s.count('.') > 1:
            s = s.replace('.', '')
        return s
