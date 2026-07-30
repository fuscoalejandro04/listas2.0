"""
Detector de contexto global (moneda, unidades, etc.) a partir del DataFrame crudo.
"""
import pandas as pd
import re
from typing import Optional, Dict, Any

class FileContext:
    """Almacena el contexto inferido del archivo."""
    def __init__(self):
        self.currency: Optional[str] = None          # 'ARS' o 'USD'
        self.default_unit: Optional[str] = None      # 'un', 'kg', 'm', 'mg', etc.
        self.has_metadata: bool = False
        self.metadata_rows: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'currency': self.currency,
            'default_unit': self.default_unit,
            'has_metadata': self.has_metadata,
            'metadata_rows': self.metadata_rows
        }


class ContextDetector:
    """
    Analiza el DataFrame crudo (todavía con columnas originales) para inferir:
    - Moneda predominante.
    - Unidad de medida más frecuente (si aparece en descripciones o títulos).
    """
    @staticmethod
    def detect_currency(df: pd.DataFrame, sample_rows: int = 200) -> Optional[str]:
        """
        Examina las celdas de las primeras filas y las celdas de precios (columnas
        que parecen contener números con símbolos de moneda).
        """
        # 1. Revisar primeras 20 filas en busca de palabras clave
        # 🔥 FIX: forzar conversión a str dentro del join para evitar TypeError
        top_text = df.iloc[:20].astype(str).apply(
            lambda x: ' '.join(str(v) for v in x), axis=1
        ).str.cat(sep=' ')
        top_text = top_text.lower()

        usd_patterns = ['usd', 'u$s', 'us$', 'dólar', 'dolar', 'dólares', 'dolares']
        ars_patterns = ['ars', 'pesos', 'peso']

        for pat in usd_patterns:
            if pat in top_text:
                return 'USD'
        for pat in ars_patterns:
            if pat in top_text:
                return 'ARS'

        # 2. Analizar las columnas que parecen precios (con números y símbolos)
        price_cols = []
        for col in df.columns:
            sample = df[col].dropna().astype(str).head(sample_rows)
            if len(sample) < 5:
                continue
            has_currency = any(re.search(r'[\$€£]', str(v)) for v in sample)
            if has_currency:
                price_cols.append(col)

        if price_cols:
            all_vals = []
            for col in price_cols:
                all_vals.extend(df[col].dropna().astype(str).tolist())
            all_text = ' '.join(str(v) for v in all_vals).lower()
            if re.search(r'u?\$?\s?us\s?\$?|u\$s|us\$|dólar|dolar', all_text):
                return 'USD'
            if re.search(r'ars|pesos', all_text):
                return 'ARS'
            if '$' in all_text and 'u$s' not in all_text and 'us$' not in all_text:
                return 'ARS'

        return None

    @staticmethod
    def detect_unit(df: pd.DataFrame) -> Optional[str]:
        """
        Examina las descripciones o nombres de productos en busca de unidades
        comunes (kg, m, mg, un, l, etc.) y retorna la más frecuente.
        """
        desc_cols = []
        for col in df.columns:
            sample = df[col].dropna().astype(str).head(50)
            if len(sample) < 5:
                continue
            if sample.str.contains(r'[a-zA-Z]').mean() > 0.5:
                desc_cols.append(col)

        if not desc_cols:
            return None

        # 🔥 FIX: forzar conversión a str dentro del join
        all_desc = ' '.join(
            str(v) for v in df[desc_cols].dropna().astype(str).apply(
                lambda x: ' '.join(str(v) for v in x), axis=1
            ).tolist()
        ).lower()

        unit_patterns = {
            'kg': r'\bkg\b',
            'g': r'\bg\b(?!\w)',
            'mg': r'\bmg\b',
            'm': r'\bm\b(?!\w)',
            'cm': r'\bcm\b',
            'mm': r'\bmm\b',
            'un': r'\bun\b',
            'unidad': r'\bunidad(es)?\b',
            'paquete': r'\bpaquete\b',
            'caja': r'\bcaja\b',
            'rollo': r'\brollo\b',
            'litro': r'\blitro(s)?\b',
            'l': r'\bl\b(?!\w)',
            'tonelada': r'\btonelada(s)?\b',
            'tn': r'\btn\b',
        }
        detected = []
        for unit, pattern in unit_patterns.items():
            if re.search(pattern, all_desc):
                detected.append(unit)

        if detected:
            return detected[0]
        return None
