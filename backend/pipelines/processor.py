"""
Módulo Procesador - Orquesta todo el pipeline ETL.
Recibe el DataFrame ya importado, detecta columnas, consolida, normaliza y valida.
"""
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional

from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.normalizers import DataNormalizer
from backend.pipelines.validators import Validator


class PipelineProcessor:
    """
    Ejecuta el flujo completo de procesamiento sobre un DataFrame ya importado.
    """

    def __init__(self, confidence_threshold: float = 0.6, quality_threshold: float = 0.8):
        """
        Inicializa el procesador con umbrales configurables.

        Args:
            confidence_threshold: Confianza mínima para considerar un mapeo válido.
            quality_threshold: Puntuación de calidad mínima (0-1) para considerar los datos válidos.
        """
        self.mapper = ColumnMapper(confidence_threshold)
        self.normalizer = DataNormalizer()
        self.validator = Validator(quality_threshold=quality_threshold)

    def normalize_and_consolidate(
        self, 
        df: pd.DataFrame, 
        mapping: Dict[str, Tuple[Optional[str], float]]
    ) -> pd.DataFrame:
        """
        Renombra columnas según taxonomía, filtra las no mapeadas y consolida duplicados
        dando prioridad a la columna original con mayor índice de confianza.

        Args:
            df: DataFrame crudo.
            mapping: Diccionario {columna_original: (campo_taxonomia, confianza)}.

        Returns:
            DataFrame con columnas estandarizadas y consolidadas (sin duplicados).
        """
        # 1. Agrupar columnas por campo taxonómico
        groups = {}
        for orig_col, (field, conf) in mapping.items():
            if orig_col not in df.columns:
                continue
            if not field or field in (None, 'No detectado', ''):
                continue
            groups.setdefault(field, []).append((conf, orig_col))

        # 2. Crear nuevo DataFrame con columnas estandarizadas y consolidación (coalesce)
        df_result = pd.DataFrame(index=df.index)

        for field, cols_with_conf in groups.items():
            # Ordenar por confianza (mayor primero) para dar prioridad
            cols_sorted = [col for _, col in sorted(cols_with_conf, key=lambda x: x[0], reverse=True)]

            if len(cols_sorted) == 1:
                # Si solo hay una columna, asignar directamente
                df_result[field] = df[cols_sorted[0]]
            else:
                # Coalesce: combinar columnas con bfill(axis=1)
                combined = pd.concat([df[col] for col in cols_sorted], axis=1)
                # bfill hacia la izquierda: el primer valor no nulo se propaga a la columna 0
                df_result[field] = combined.bfill(axis=1).iloc[:, 0]

        return df_result

    def process(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Ejecuta todo el pipeline y retorna un resultado estructurado.

        Args:
            df: DataFrame crudo proveniente del importador.

        Returns:
            Diccionario con:
                - mapping: Mapeo de columnas originales a taxonomía.
                - confidence_report: Resumen de confianza por campo.
                - products: Lista de productos normalizados.
                - validation_report: Reporte de validación con issues y calidad.
                - duplicates: Lista de productos duplicados por código.
                - summary: Resumen ejecutivo.
        """
        # 0. Asegurar que los nombres de columnas sean string (previene AttributeError)
        df.columns = df.columns.astype(str)

        # 1. Detección de columnas (mapeo a taxonomía)
        mapping = self.mapper.map_columns(df)
        confidence_report = self.mapper.get_confidence_report(mapping)

        # 2. Normalización estructural: renombrar y consolidar columnas
        df_clean = self.normalize_and_consolidate(df, mapping)

        # 3. Normalización de datos (limpieza y tipificación)
        normalized_products = []
        for _, row in df_clean.iterrows():
            normalized = self.normalizer.normalize_row(row)
            normalized_products.append(normalized)

        # 4. Validación de calidad
        validation_report = self.validator.validate_all(normalized_products)

        # 5. Detección de duplicados por código
        duplicates = self.find_duplicates(normalized_products)

        # 6. Generar resumen ejecutivo
        summary = self.generate_summary(
            products=normalized_products,
            validation=validation_report,
            duplicates=duplicates
        )

        return {
            'mapping': mapping,
            'confidence_report': confidence_report,
            'products': normalized_products,
            'validation_report': validation_report,
            'duplicates': duplicates,
            'summary': summary,
        }

    @staticmethod
    def find_duplicates(products: List[Dict]) -> List[Dict]:
        """
        Detecta productos con mismo código (asumiendo que 'codigo' es único).

        Returns:
            Lista de duplicados con: {'row': idx, 'code': str, 'previous_row': int}
        """
        seen = {}
        duplicate_rows = []
        for idx, p in enumerate(products):
            code = p.get('codigo', '')
            if not code:
                continue
            if code in seen:
                duplicate_rows.append({
                    'row': idx + 1,          # 1-based para reporte
                    'code': code,
                    'previous_row': seen[code]
                })
            else:
                seen[code] = idx + 1
        return duplicate_rows

    @staticmethod
    def generate_summary(products: List[Dict], validation: Dict, duplicates: List) -> Dict:
        """
        Genera un resumen ejecutivo del procesamiento.
        """
        total = len(products)
        error_count = validation.get('error_count', 0)
        warning_count = validation.get('warning_count', 0)
        valid_count = total - error_count  # Aproximación: productos sin errores

        return {
            'total_rows': total,
            'valid_rows': valid_count,
            'error_rows': error_count,
            'warning_rows': warning_count,
            'duplicate_count': len(duplicates),
            'quality_score': validation.get('quality_score', 0.0),
            'is_valid': validation.get('is_valid', False),
        }
