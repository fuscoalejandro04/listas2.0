"""
Módulo de Normalización - Limpia y tipifica los datos crudos.
Asume que las columnas ya tienen los nombres de la taxonomía (ej. 'precio_lista', 'ean').
"""
import pandas as pd
import re
from typing import Dict, Any, Optional, Callable, Tuple


class DataNormalizer:
    """
    Normaliza una fila del DataFrame que ya tiene columnas de la taxonomía.
    Cada campo se somete a una función de limpieza/conversión específica.
    """

    def __init__(self):
        # Registro de funciones de normalización por campo
        self.normalizers: Dict[str, Callable[[Any], Any]] = {
            'codigo': self._normalize_codigo,
            'nombre_articulo': self._normalize_text,
            'descripcion': self._normalize_text,
            'categoria': self._normalize_text,
            'marca': self._normalize_text,
            'modelo': self._normalize_text,
            'ean': self._normalize_ean,          # <-- Corregido el bug del "cero fantasma"
            'precio_lista': self._normalize_price_with_currency,
            'precio_sugerido': self._normalize_price_with_currency,
            'precio_2': self._normalize_price_with_currency,
            'precio_3': self._normalize_price_with_currency,
            'iva': self._normalize_iva,
            'moneda': self._normalize_text,      # Se usa si viene explícita, o la extraemos del precio
            'hoja_origen': self._normalize_text,
        }
        # Patrones de moneda para extracción
        self.currency_patterns = [
            (r'^\s*U?\$?\s*', 'USD'),   # U$S, US$, $, etc.
            (r'^\s*ARS\s*', 'ARS'),
            (r'^\s*EUR\s*', 'EUR'),
            (r'\s*U?\$?\s*$', 'USD'),   # al final
        ]

    def normalize_row(self, row: pd.Series) -> Dict[str, Any]:
        """
        Recibe una fila (con columnas de la taxonomía) y devuelve un diccionario
        con los valores normalizados.
        """
        normalized = {}
        for field, normalizer_func in self.normalizers.items():
            raw_value = row.get(field)
            # Si el campo es un precio, puede devolver (valor, moneda)
            if field.startswith('precio_'):
                result = normalizer_func(raw_value)
                if isinstance(result, tuple) and len(result) == 2:
                    normalized[field] = result[0]
                    # Asignar moneda si no existe ya o es None
                    if 'moneda' not in normalized or normalized['moneda'] is None:
                        normalized['moneda'] = result[1]
                else:
                    normalized[field] = result
            else:
                normalized[field] = normalizer_func(raw_value)
        return normalized

    # ---------- Funciones de normalización específicas ----------
    def _normalize_text(self, value: Any) -> Optional[str]:
        """Limpia y convierte a string, maneja nulos."""
        if pd.isna(value):
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned else None
        return str(value).strip()

    def _normalize_codigo(self, value: Any) -> Optional[str]:
        """Código: se espera string numérico o alfanumérico."""
        if pd.isna(value):
            return None
        # Si es float con .0, convertir a entero y luego a string
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
        return str(value).strip()

    def _normalize_ean(self, value: Any) -> Optional[str]:
        """
        EAN: solo dígitos, manejo seguro de floats para evitar el 'cero fantasma'.
        Ej: 4006825613964.0 -> '4006825613964' (sin el punto ni el cero extra).
        """
        if pd.isna(value):
            return None

        # --- CORRECCIÓN CLAVE: Manejar floats antes de convertir a string ---
        if isinstance(value, float):
            # Si el float representa un entero (ej. 4006825613964.0)
            if value.is_integer():
                value = int(value)
            else:
                # Si tiene decimales (caso raro), truncamos para evitar errores
                value = int(value)

        # Ahora eliminamos todo lo que no sea dígito
        cleaned = re.sub(r'[^0-9]', '', str(value))
        return cleaned if cleaned else None

    def _normalize_price_with_currency(self, value: Any) -> Tuple[Optional[float], Optional[str]]:
        """
        Normaliza el precio y extrae el símbolo de moneda.
        Retorna (valor_float, simbolo_moneda).
        """
        if pd.isna(value):
            return None, None

        if isinstance(value, (int, float)):
            return float(value), None

        if isinstance(value, str):
            cleaned = value.strip()
            currency_symbol = None

            # 1. Extraer símbolo de moneda
            for pattern, symbol in self.currency_patterns:
                if re.search(pattern, cleaned):
                    currency_symbol = symbol
                    cleaned = re.sub(pattern, '', cleaned)
                    break

            # 2. Limpiar el número (formato latinoamericano)
            if ',' in cleaned and '.' in cleaned:
                parts = cleaned.rsplit(',', 1)
                if len(parts) == 2:
                    integer_part = parts[0].replace('.', '').replace(' ', '')
                    decimal_part = parts[1]
                    cleaned = integer_part + '.' + decimal_part
            elif ',' in cleaned and '.' not in cleaned:
                cleaned = cleaned.replace(',', '.')

            # 3. Remover todo lo que no sea dígito, punto o signo menos
            cleaned = re.sub(r'[^\d.-]', '', cleaned)
            try:
                return float(cleaned), currency_symbol
            except ValueError:
                return None, currency_symbol

        return None, None

    def _normalize_iva(self, value: Any) -> Optional[float]:
        """IVA: convierte a float, interpreta porcentajes."""
        if pd.isna(value):
            return None
        if isinstance(value, (int, float)):
            # Si es 21.0, asumimos que es 21% (0.21)
            if value > 1:
                return value / 100.0
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.endswith('%'):
                cleaned = cleaned[:-1]
            cleaned = cleaned.replace(',', '.')
            try:
                num = float(cleaned)
                if num > 1:
                    return num / 100.0
                return num
            except ValueError:
                return None
        return None
