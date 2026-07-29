"""
Módulo de Normalización - Convierte valores a formatos estándar.
"""
import pandas as pd
import re
from typing import Any, Dict

class DataNormalizer:
    """Aplica transformaciones según el tipo de campo."""
    
    @staticmethod
    def normalize_string(value: Any) -> str:
        """Limpia texto: elimina espacios extra, convierte a string."""
        if pd.isna(value):
            return ""
        return str(value).strip()
    
    @staticmethod
    def normalize_float(value: Any) -> float:
        """Convierte a float manejando formatos locales (1.234,56 o 1,234.56)."""
        if pd.isna(value):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        
        # Limpiar símbolos de moneda y espacios
        cleaned = re.sub(r'[^\d.,\-]', '', str(value))
        
        # Detectar formato europeo (1.234,56) vs americano (1,234.56)
        if ',' in cleaned and '.' in cleaned:
            # Si el punto está antes que la coma, es europeo
            if cleaned.rfind('.') < cleaned.rfind(','):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned and '.' not in cleaned:
            # Solo coma: puede ser decimal (1,5) o separador de miles (1,234)
            # Si hay más de una coma, es miles
            if cleaned.count(',') > 1:
                cleaned = cleaned.replace(',', '')
            else:
                cleaned = cleaned.replace(',', '.')
        
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    
    @staticmethod
    def normalize_percentage(value: Any) -> float:
        """Convierte porcentajes a valor decimal (21% → 0.21)."""
        if pd.isna(value):
            return 0.0
        if isinstance(value, (int, float)):
            # Si es > 1, asumimos que es porcentaje (ej: 21 → 0.21)
            return value / 100.0 if value > 1 else value
        cleaned = re.sub(r'[^\d.,\-]', '', str(value))
        # Convertir a float primero
        num = DataNormalizer.normalize_float(cleaned)
        # Si el número es > 1, es porcentaje (21% → 0.21)
        return num / 100.0 if num > 1 else num
    
    @staticmethod
    def normalize_ean(value: Any) -> str:
        """Limpia EAN: solo dígitos, elimina espacios y guiones."""
        if pd.isna(value):
            return ""
        cleaned = re.sub(r'[^0-9]', '', str(value))
        return cleaned[:13]  # Trunca a 13 dígitos
    
    def normalize_row(self, row: pd.Series, mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Aplica normalización a una fila según el mapeo de columnas.
        mapping: {columna_origen: campo_taxonomia}
        """
        normalized = {}
        for col, field in mapping.items():
            if field is None:
                continue
            value = row.get(col, None)
            
            # Aplicar normalización según el tipo de campo
            # (esto debería venir de la taxonomía, pero lo hacemos simple)
            if field in ['codigo', 'nombre_articulo', 'descripcion', 'marca', 'moneda']:
                normalized[field] = self.normalize_string(value)
            elif field in ['precio_lista', 'precio_sugerido']:
                normalized[field] = self.normalize_float(value)
            elif field == 'iva':
                normalized[field] = self.normalize_percentage(value)
            elif field == 'ean':
                normalized[field] = self.normalize_ean(value)
            else:
                normalized[field] = value
        
        return normalized
