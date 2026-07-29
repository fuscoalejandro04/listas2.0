"""
Módulo Procesador - Orquesta todo el pipeline ETL.
"""
import pandas as pd
from typing import Dict, List, Any, Tuple
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.importers import Importer
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.normalizers import DataNormalizer
from backend.pipelines.validators import Validator

class PipelineProcessor:
    """Ejecuta el flujo completo de procesamiento."""
    
    def __init__(self, confidence_threshold: float = 0.6):
        self.mapper = ColumnMapper(confidence_threshold)
        self.normalizer = DataNormalizer()
        self.validator = Validator()
    
    def process(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Ejecuta todo el pipeline y retorna un resultado estructurado.
        """
        # 1. Detección de columnas
        mapping = self.mapper.map_columns(df)
        confidence_report = self.mapper.get_confidence_report(mapping)
        
        # 2. Normalización
        normalized_products = []
        for _, row in df.iterrows():
            normalized = self.normalizer.normalize_row(row, mapping)
            normalized_products.append(normalized)
        
        # 3. Validación
        validation_report = self.validator.validate_all(normalized_products)
        
        # 4. Detectar duplicados (básico por código)
        duplicates = self.find_duplicates(normalized_products)
        
        return {
            'mapping': mapping,
            'confidence_report': confidence_report,
            'products': normalized_products,
            'validation_report': validation_report,
            'duplicates': duplicates,
            'summary': self.generate_summary(normalized_products, validation_report, duplicates)
        }
    
    @staticmethod
    def find_duplicates(products: List[Dict]) -> List[Dict]:
        """Detecta productos con mismo código."""
        seen = {}
        duplicate_rows = []
        for idx, p in enumerate(products):
            code = p.get('codigo', '')
            if not code:
                continue
            if code in seen:
                duplicate_rows.append({
                    'row': idx + 1,
                    'code': code,
                    'previous_row': seen[code]
                })
            else:
                seen[code] = idx + 1
        return duplicate_rows
    
    @staticmethod
    def generate_summary(products: List[Dict], validation: Dict, duplicates: List) -> Dict:
        """Genera un resumen ejecutivo del procesamiento."""
        return {
            'total_rows': len(products),
            'valid_rows': validation['total_products'] - validation['error_count'],
            'error_rows': validation['error_count'],
            'warning_rows': validation['warning_count'],
            'duplicate_count': len(duplicates),
            'quality_score': validation['quality_score']
        }
