"""
Módulo Procesador - Orquesta todo el pipeline ETL.
Ya no depende de importers, recibe el DataFrame directamente.
Integra la consolidación, normalización estructural, enriquecimiento IA y validación.
"""
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional

from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.normalizers import DataNormalizer
from backend.pipelines.validators import Validator
from backend.pipelines.context_detector import ContextDetector, FileContext
from backend.pipelines.ai_enricher import AIEnricher   # 🆕 nuevo módulo


class PipelineProcessor:
    """Ejecuta el flujo completo de procesamiento sobre un DataFrame ya importado."""

    def __init__(self, 
                 confidence_threshold: float = 0.6,
                 enable_ai: bool = True,
                 ai_model: str = "gpt-4o-mini",
                 ai_batch_size: int = 20):
        self.mapper = ColumnMapper(confidence_threshold)
        self.normalizer = DataNormalizer()   # se crea sin contexto; se asignará en process()
        self.validator = Validator()
        self.enable_ai = enable_ai
        if self.enable_ai:
            self.ai_enricher = AIEnricher(model=ai_model, batch_size=ai_batch_size)

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

        # 🔥 0.5 Detectar contexto global (moneda y unidad por defecto)
        context = FileContext()
        context.currency = ContextDetector.detect_currency(df)
        context.default_unit = ContextDetector.detect_unit(df)
        # Inyectar el contexto en el normalizador
        self.normalizer.context = context
        self.normalizer.default_unit = context.default_unit

        # 1. Detección de columnas
        mapping = self.mapper.map_columns(df)
        confidence_report = self.mapper.get_confidence_report(mapping)

        # 1.5 Normalización Estructural y Consolidación (Elimina tuplas duplicadas)
        df_clean = self.normalize_and_consolidate(df, mapping)

        # ------------------------------------------------------------
        # FILTROS DE LIMPIEZA DE FILAS BASURA
        # ------------------------------------------------------------
        if 'codigo' in df_clean.columns and 'descripcion' in df_clean.columns:
            mask_codigo = df_clean['codigo'].isna() | (df_clean['codigo'].astype(str).str.strip() == '')
            mask_desc = df_clean['descripcion'].isna() | (df_clean['descripcion'].astype(str).str.strip() == '')
            df_clean = df_clean[~(mask_codigo & mask_desc)]
        elif 'codigo' in df_clean.columns:
            mask_codigo = df_clean['codigo'].isna() | (df_clean['codigo'].astype(str).str.strip() == '')
            df_clean = df_clean[~mask_codigo]

        if 'codigo' in df_clean.columns and 'precio_lista' in df_clean.columns:
            mask_codigo_vacio = df_clean['codigo'].isna() | (df_clean['codigo'].astype(str).str.strip() == '')
            mask_precio_vacio = df_clean['precio_lista'].isna() | (df_clean['precio_lista'].astype(str).str.strip() == '')
            df_clean = df_clean[~(mask_codigo_vacio & mask_precio_vacio)]

        if 'codigo' in df_clean.columns:
            codigo_str = df_clean['codigo'].astype(str).str.strip().str.upper()
            mascara_encabezado = codigo_str.isin(['CODIGO', 'CÓDIGO', 'CÓD'])
            df_clean = df_clean[~mascara_encabezado]

        # 2. Normalización de Datos (síntesis de atributos)
        normalized_products = []
        for _, row in df_clean.iterrows():
            normalized = self.normalizer.normalize_row(row)
            normalized_products.append(normalized)

        # 🔥 2.5 ENRIQUECIMIENTO SEMÁNTICO CON IA
        if self.enable_ai and self.ai_enricher:
            normalized_products = self.ai_enricher.enrich(normalized_products)

        # 3. Validación (ahora con campos enriquecidos)
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
