"""
Módulo de Normalización - Limpia y tipifica los datos crudos.
Ahora con detección de contexto (moneda y unidades), extracción de unidades,
limpieza universal y síntesis de atributos (marca, nombre, dimensiones).
"""
import pandas as pd
import re
import unicodedata
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
            'dimensiones': self._normalize_text,
            'categoria': self._normalize_text,
            'marca': self._normalize_text,
            'modelo': self._normalize_text,
            'linea_producto': self._normalize_text,   # 🆕 campo para IA
            'ean': self._normalize_ean,
            'precio_lista': self._normalize_price_with_currency,
            'precio_sugerido': self._normalize_price_with_currency,
            'precio_2': self._normalize_price_with_currency,
            'precio_3': self._normalize_price_with_currency,
            'iva': self._normalize_iva,
            'moneda': self._normalize_moneda,
            'unidad_medida': self._normalize_unit,
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
        # 🔥 PASO 2: SÍNTESIS DE ATRIBUTOS FALTANTES (CON DIMENSIONES)
        # ============================================================
        # Asegurar que todos los campos existen en el diccionario
        normalized.setdefault('marca', None)
        normalized.setdefault('modelo', None)
        normalized.setdefault('dimensiones', None)
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

        # 2. Sintetizar nombre_articulo si está vacío (CON DIMENSIONES)
        nombre = normalized.get('nombre_articulo')
        if not nombre or nombre.strip() == '':
            marca_final = normalized.get('marca', '')
            modelo = normalized.get('modelo', '')
            dimensiones = normalized.get('dimensiones', '')
            desc = normalized.get('descripcion', '')

            # 2a. Construir nombre con Marca + Modelo + Dimensiones (si existen)
            nombre_parts = []
            if marca_final:
                nombre_parts.append(marca_final)
            if modelo:
                nombre_parts.append(modelo)
            if dimensiones:
                nombre_parts.append(dimensiones)

            if nombre_parts:
                normalized['nombre_articulo'] = " ".join(nombre_parts).strip()
            # 2b. Fallback: usar primeros 60 caracteres de descripcion
            elif desc:
                truncated = desc[:60]
                if len(desc) > 60:
                    truncated += '...'
                normalized['nombre_articulo'] = truncated
            # 2c. Si no hay nada, dejar vacío

        return normalized

    # ---------- Funciones de normalización específicas ----------
    def _normalize_text(self, value: Any) -> Optional[str]:
        """
        Limpia y convierte a string, maneja nulos.
        🔥 UNIVERSAL CLEANING: elimina caracteres decorativos (★, ®, ™, emojis, etc.)
        pero conserva letras (incluyendo acentos), números, espacios y puntuación gramatical estándar.
        """
        if pd.isna(value):
            return None

        # Convertir a string y eliminar espacios extremos
        if isinstance(value, str):
            cleaned = value.strip()
        else:
            cleaned = str(value).strip()

        if not cleaned:
            return None

        # 🔥 PASO 1: Normalizar Unicode (NFKC convierte caracteres especiales a formas base)
        # Ej: ㎏ → kg, pero é → é (lo conservamos)
        normalized = unicodedata.normalize('NFKC', cleaned)

        # 🔥 PASO 2: Eliminar todo lo que NO sea:
        # - Letras (incluyendo acentos y ñ) -> \w (con flag UNICODE)
        # - Números -> \d
        # - Espacios -> \s
        # - Puntuación gramatical estándar: . , ; : ( ) - / %
        # NOTA: El patrón usa [^\w\s.,;:()\-/%] que significa "cualquier cosa que NO esté en esta lista"
        cleaned = re.sub(r'[^\w\s.,;:()\-/%]', '', normalized, flags=re.UNICODE)

        # 🔥 PASO 3: Limpiar espacios múltiples
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned if cleaned else None

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

    # 🔥 CORRECCIÓN: Método _normalize_unit con filtro estricto de empaque comercial
    def _normalize_unit(self, value: Any) -> Optional[str]:
        """
        🔥 CORREGIDO: Extrae UNIDAD DE VENTA COMERCIAL (empaque) usando límites de palabra estricta.
        Solo detecta palabras como 'caja', 'rollo', 'pack', 'kit', etc.
        Si no encuentra un empaque comercial, retorna 'un' (Unidad) por defecto.
        """
        default_comercial = "un"
        if pd.isna(value) or not isinstance(value, str):
            return default_comercial

        text = value.lower().strip()
        
        # 🔥 Diccionario de unidades de empaque comercial con patrones de límite de palabra (\b)
        unit_map = {
            'caja': r'\bcaja\b|\bcajas\b',
            'rollo': r'\brollo\b|\brollos\b',
            'pack': r'\bpack\b|\bpacks\b',
            'paquete': r'\bpaquete\b|\bpaquetes\b',
            'kit': r'\bkit\b|\bkits\b',
            'par': r'\bpar\b|\bpares\b',
            'juego': r'\bjuego\b|\bjuegos\b',
            'set': r'\bset\b|\bsets\b',
            'litro': r'\blitro\b|\blitros\b',
            'l': r'\bl\b',
            'galon': r'\bgalon\b|\bgalones\b',
            'docena': r'\bdocena\b|\bdocenas\b',
            'bolsa': r'\bbolsa\b|\bbolsas\b'
        }

        for unit, pattern in unit_map.items():
            if re.search(pattern, text):
                return unit

        return default_comercial
