"""
Módulo de Detección de Encabezados - Usa sinónimos y fuzzy matching
para mapear columnas del archivo a campos de la taxonomía.
"""
import pandas as pd
from rapidfuzz import fuzz, process
from backend.domain.taxonomy import TAXONOMY
from typing import Dict, List, Tuple

class ColumnMapper:
    """Detecta y mapea columnas del DataFrame a la taxonomía."""
    
    def __init__(self, confidence_threshold: float = 0.7):
        self.threshold = confidence_threshold
        # Construir una lista plana de todos los sinónimos conocidos
        self.synonym_list = []
        self.synonym_to_field = {}
        for field in TAXONOMY.fields:
            for alias in field.aliases:
                self.synonym_list.append(alias.lower())
                self.synonym_to_field[alias.lower()] = field.name
            # Agregar el nombre del campo también como sinónimo de sí mismo
            self.synonym_list.append(field.name.lower())
            self.synonym_to_field[field.name.lower()] = field.name
    
    def map_columns(self, df: pd.DataFrame) -> Dict[str, Tuple[str, float]]:
        """
        Retorna un diccionario: {nombre_columna_origen: (campo_taxonomia, confianza)}
        """
        mapping = {}
        for col in df.columns:
            col_clean = col.strip().lower()
            # 1. Búsqueda exacta en sinónimos
            if col_clean in self.synonym_to_field:
                mapping[col] = (self.synonym_to_field[col_clean], 1.0)
                continue
            
            # 2. Fuzzy matching contra la lista de sinónimos
            result = process.extractOne(
                col_clean, 
                self.synonym_list, 
                scorer=fuzz.WRatio,
                score_cutoff=int(self.threshold * 100)
            )
            if result:
                synonym, score, _ = result
                field_name = self.synonym_to_field[synonym]
                mapping[col] = (field_name, score / 100.0)
            else:
                # No se pudo mapear
                mapping[col] = (None, 0.0)
        
        return mapping
    
    def get_confidence_report(self, mapping: Dict[str, Tuple[str, float]]) -> Dict:
        """Genera un resumen de confianza para el reporte."""
        total = len(mapping)
        mapped = sum(1 for v in mapping.values() if v[0] is not None)
        avg_confidence = sum(v[1] for v in mapping.values() if v[0] is not None) / mapped if mapped > 0 else 0
        return {
            "total_columns": total,
            "mapped_columns": mapped,
            "unmapped_columns": total - mapped,
            "average_confidence": avg_confidence,
        }
