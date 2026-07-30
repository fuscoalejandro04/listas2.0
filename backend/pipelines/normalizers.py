"""
Módulo de Normalización - Limpia y tipifica los datos crudos.
Ahora con detección de contexto (moneda y unidades) y extracción de unidades desde descripciones.
"""
import pandas as pd
import re
from typing import Dict, Any, Optional, Callable, Tuple

from backend.pipelines.context_detector import FileContext


class DataNormalizer:
    """
    Normaliza una fila del DataFrame que ya tiene columnas de la taxonomía.
    Cada campo se somete a una función de limpieza/conversión específica.
    """

    def __init__(self, context: Optional[FileContext] = None):
        self.context = context or FileContext()
        self.default_unit = self.context.default_unit

        # Registro de funciones de normalización por campo
        self.normalizers: Dict[str, Callable[[Any], Any]] = {
            'codigo': self._normalize_codigo,
            'nombre_articulo': self._normalize_text,
            'descripcion': self._normalize_text,
            'categoria': self._normalize_text,
            'marca': self._normalize_text,
            'modelo': self._normalize_text,
            'ean': self._normalize_ean,
            'precio_lista': self._normalize_price_with_currency,
            'precio_sugerido': self._normalize_price_with_currency,
            'precio_2': self._normalize_price_with_currency,
            'precio_3': self._normalize_price_with_currency,
            'iva': self._normalize_iva,
            'moneda': self._normalize_moneda,
            'unidad_medida': self._normalize_unit,      # <-- extrae desde descripción
            'hoja_origen': self._normalize_text,
        }

        # Patrones de moneda para extracción
        self.currency_patterns = [
            (r'\s*U?\$?\s*', 'USD'),   # U$S, US$, $, etc.
            (r'\s*ARS\s*', 'ARS'),
            (r'\s*EUR\s*', 'EUR'),
            (r'\s*U?\$?\s*$', 'USD'),   # al final
        ]

    def normalize_row(self, row: pd.Series) -> Dict[str, Any]:
        """
        Recibe una fila (con columnas de la taxonomía) y devuelve un diccionario
        con los valores normalizados.
        """
        normalized = {}

        # --- Paso 1: Normalización estándar ---
        for field, normalizer_func in self.normalizers.items():
            # Para 'unidad_medida', tomamos el valor de 'descripcion' si existe
            if field == 'unidad_medida':
                desc = row.get('descripcion', '')
                normalized[field] = self._normalize_unit(desc)
            else:
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

        # ============================================================
        # 🔥 PASO 2: SÍNTESIS DE ATRIBUTOS FALTANTES
        # ============================================================
        # Asegurar que todos los campos existen en el diccionario
        normalized.setdefault('marca', None)
        normalized.setdefault('modelo', None)
        normalized.setdefault('descripcion', None)
        normalized.setdefault('nombre_articulo', None)
        normalized.setdefault('hoja_origen', None)

        # 1. Inferir marca desde hoja_origen
        marca = normalized.get('marca')
        if not marca or marca.strip() == '':
            hoja = normalized.get('hoja_origen', '')
            if hoja:
                hoja_upper = hoja.upper()
                if 'EINHELL' in hoja_upper:
                    normalized['marca'] = 'EINHELL'
                elif 'KWB' in hoja_upper:
                    normalized['marca'] = 'KWB'
                # Si no coincide, se deja como estaba (None o vacío)

        # 2. Sintetizar nombre_articulo si está vacío
        nombre = normalized.get('nombre_articulo')
        if not nombre or nombre.strip() == '':
            marca_final = normalized.get('marca', '')
            modelo = normalized.get('modelo', '')
            desc = normalized.get('descripcion', '')

            # 2a. Si hay marca y modelo, concatenarlos
            if marca_final and modelo:
                normalized['nombre_articulo'] = f"{marca_final} {modelo}".strip()
            # 2b. Fallback: usar primeros 60 caracteres de descripcion
            elif desc:
                truncated = desc[:60]
                if len(desc) > 60:
                    truncated += '...'
                normalized['nombre_articulo'] = truncated
            # 2c. Si no hay nada, dejar vacío (ya está None)

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
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
        return str(value).strip()

    def _normalize_ean(self, value: Any) -> Optional[str]:
        """
        EAN: solo dígitos, manejo seguro de floats para evitar el 'cero fantasma'.
        """
        if pd.isna(value):
            return None
        if isinstance(value, float):
            if value.is_integer():
                value = int(value)
            else:
                value = int(value)
        cleaned = re.sub(r'[^0-9]', '', str(value))
        return cleaned if cleaned else None

    def _normalize_price_with_currency(self, value: Any) -> Tuple[Optional[float], Optional[str]]:
        """
        Normaliza el precio y extrae el símbolo de moneda.
        Retorna (valor_float, simbolo_moneda).
        Si no se detecta moneda en la celda, usa la del contexto global.
        """
        if pd.isna(value):
            return None, self.context.currency

        if isinstance(value, (int, float)):
            return float(value), self.context.currency

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
                return float(cleaned), currency_symbol or self.context.currency
            except ValueError:
                return None, currency_symbol or self.context.currency

        return None, self.context.currency

    def _normalize_iva(self, value: Any) -> Optional[float]:
        """IVA: convierte a float, interpreta porcentajes."""
        if pd.isna(value):
            return None
        if isinstance(value, (int, float)):
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

    def _normalize_moneda(self, value: Any) -> Optional[str]:
        """
        Normaliza la moneda filtrando ruido (solo acepta strings cortos ≤ 4 caracteres).
        Si no se detecta, usa la moneda del contexto.
        """
        if pd.isna(value):
            return self.context.currency
        if isinstance(value, str):
            cleaned = value.strip()
            if len(cleaned) <= 4:
                return cleaned.upper()
        return self.context.currency

    def _normalize_unit(self, value: Any) -> Optional[str]:
        """
        Extrae unidad de medida de la descripción o nombre del producto.
        Si no se encuentra, usa la unidad por defecto del contexto.
        """
        if pd.isna(value) or not isinstance(value, str):
            return self.default_unit

        text = value.lower()

        unit_map = {
            'kg': 'kg', 'kilogramo': 'kg', 'kilogramos': 'kg',
            'g': 'g', 'gramo': 'g', 'gramos': 'g',
            'mg': 'mg', 'miligramo': 'mg', 'miligramos': 'mg',
            'm': 'm', 'metro': 'm', 'metros': 'm',
            'cm': 'cm', 'centímetro': 'cm', 'centímetros': 'cm',
            'mm': 'mm', 'milímetro': 'mm', 'milímetros': 'mm',
            'un': 'un', 'unidad': 'un', 'unidades': 'un',
            'paquete': 'paquete', 'paquetes': 'paquete',
            'caja': 'caja', 'cajas': 'caja',
            'rollo': 'rollo', 'rollos': 'rollo',
            'l': 'l', 'litro': 'l', 'litros': 'l',
            'tonelada': 'tn', 'toneladas': 'tn', 'tn': 'tn',
        }

        # Patrón: "x <número> <unidad>" (ej. "x 100 m" o "caja x 50 un")
        match = re.search(r'x\s*(\d+\.?\d*)\s*([a-záéíóú]+)', text)
        if match:
            unit_candidate = match.group(2)
            for key, unit in unit_map.items():
                if key in unit_candidate:
                    return unit

        # Patrón: "<número> <unidad>" (ej. "100 m", "50 kg")
        match = re.search(r'(\d+\.?\d*)\s*([a-záéíóú]+)', text)
        if match:
            unit_candidate = match.group(2)
            for key, unit in unit_map.items():
                if key in unit_candidate:
                    return unit

        return self.default_unit
