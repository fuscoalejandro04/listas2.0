import sys
import os
from pathlib import Path

# 1. Calcular la ruta absoluta de la raíz del repositorio (listas2.0)
root_path = str(Path(__file__).resolve().parent.parent)

# 2. Inyectar la ruta en sys.path ANTES de importar cualquier módulo interno
if root_path not in sys.path:
    sys.path.insert(0, root_path)

# 3. Importar librerías de terceros
import streamlit as st
import pandas as pd
import io

# 4. AHORA SÍ: Importar tus módulos de backend
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.processor import PipelineProcessor

"""
Módulo Procesador - Orquesta todo el pipeline ETL.
Ya no depende de importers, recibe el DataFrame directamente.
Integra la consolidación y normalización estructural de columnas.
"""
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.normalizers import DataNormalizer
from backend.pipelines.validators import Validator


class PipelineProcessor:
    """Ejecuta el flujo completo de procesamiento sobre un DataFrame ya importado."""

    def __init__(self, confidence_threshold: float = 0.6):
        self.mapper = ColumnMapper(confidence_threshold)
        self.normalizer = DataNormalizer()
        self.validator = Validator()

    def normalize_and_consolidate(
        self, df: pd.DataFrame, mapping: Dict[str, Tuple[Optional[str], float]]
    ) -> pd.DataFrame:
        """
        Renombra columnas según taxonomía, filtra las no mapeadas y consolida duplicados
        dando prioridad a la columna original con mayor índice de confianza.
        """
        groups = {}
        for orig_col, (field, conf) in mapping.items():
            if orig_col not in df.columns:
                continue
            if not field or field in (None, 'No detectado', ''):
                continue
            groups.setdefault(field, []).append((conf, orig_col))

        df_result = pd.DataFrame(index=df.index)

        for field, cols_with_conf in groups.items():
            # Ordenar por confianza descendente para priorizar la mejor columna
            cols_sorted = [
                col for _, col in sorted(cols_with_conf, key=lambda x: x[0], reverse=True)
            ]

            if len(cols_sorted) == 1:
                df_result[field] = df[cols_sorted[0]]
            else:
                # Coalesce: bfill a lo largo de las columnas, luego tomar la primera
                combined = pd.concat([df[col] for col in cols_sorted], axis=1)
                df_result[field] = combined.bfill(axis=1).iloc[:, 0]

        return df_result

    def process(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Ejecuta todo el pipeline y retorna un resultado estructurado.
        """
        # 0. Prevenir AttributeError: 'int' object has no attribute 'strip'
        df.columns = df.columns.astype(str)

        # 1. Detección de columnas
        mapping = self.mapper.map_columns(df)
        confidence_report = self.mapper.get_confidence_report(mapping)

        # 1.5 Normalización Estructural y Consolidación (Elimina tuplas duplicadas)
        df_clean = self.normalize_and_consolidate(df, mapping)

        # 2. Normalización de Datos
        normalized_products = []
        for _, row in df_clean.iterrows():
            # 🔥 CORRECCIÓN CLAVE: NO pasar mapping, solo la fila
            normalized = self.normalizer.normalize_row(row)
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
            'summary': self.generate_summary(
                normalized_products, validation_report, duplicates
            ),
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
