"""
Módulo Procesador - Orquesta todo el pipeline ETL.
Integra consolidación, normalización estructural, categorización por reglas, IA (Gemini) y validación.
"""
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional

from backend.domain.taxonomy import TAXONOMY
from backend.pipelines.detectors import ColumnMapper
from backend.pipelines.normalizers import DataNormalizer
from backend.pipelines.validators import Validator
from backend.pipelines.context_detector import ContextDetector, FileContext
from backend.pipelines.rule_categorizer import RuleCategorizer
from backend.pipelines.ai_enricher import AIEnricher

class PipelineProcessor:
    """Ejecuta el flujo completo de procesamiento sobre un DataFrame ya importado."""

    def __init__(self,
                 confidence_threshold: float = 0.8,
                 enable_categorizer: bool = True,
                 enable_ai: bool = True):
        """
        Args:
            confidence_threshold: Umbral mínimo de confianza para mapeo de columnas.
            enable_categorizer: Si se debe ejecutar la categorización por reglas locales.
            enable_ai: Si se debe ejecutar el enriquecimiento semántico con IA (Gemini).
        """
        print("🚀 Inicializando PipelineProcessor...")
        self.mapper = ColumnMapper(confidence_threshold)
        self.normalizer = DataNormalizer()
        self.validator = Validator()
        self.enable_categorizer = enable_categorizer
        self.enable_ai = enable_ai
        print(f"🔧 enable_ai = {self.enable_ai}")

        if self.enable_categorizer:
            self.categorizer = RuleCategorizer()
            print("✅ RuleCategorizer inicializado")
        else:
            self.categorizer = None

        # Inicializar IA (si está habilitada)
        self.ai_enricher = None
        if self.enable_ai:
            print("🧠 Inicializando AIEnricher...")
            try:
                self.ai_enricher = AIEnricher()  # Si no tiene API key, internamente se pone en modo simulación.
                print(f"✅ AIEnricher inicializado (simulate={self.ai_enricher.simulate})")
            except Exception as e:
                print(f"❌ Error al inicializar AIEnricher: {e}")
                self.ai_enricher = None
        print("✅ PipelineProcessor listo.\n")

    def _inferir_categorias_de_titulos(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detecta filas que son títulos de categoría (≥80% celdas vacías),
        propaga la categoría hacia abajo con forward fill, y luego ELIMINA
        las filas de título para que no sean procesadas como productos.
        """
        if df.empty:
            return df

        df['categoria_heredada'] = None
        titulos_indices = []
        total_cols = df.shape[1]
        threshold = 0.8

        for idx in range(len(df)):
            row = df.iloc[idx]
            non_empty = row.count()
            empty_ratio = 1 - (non_empty / total_cols)

            if empty_ratio >= threshold:
                titulo = None
                for col in range(min(3, total_cols)):
                    val = row.iloc[col]
                    if pd.notna(val) and str(val).strip():
                        titulo = str(val).strip()
                        break
                if titulo:
                    df.at[idx, 'categoria_heredada'] = titulo
                    titulos_indices.append(idx)

        df['categoria_heredada'] = df['categoria_heredada'].ffill()

        if titulos_indices:
            df = df.drop(index=titulos_indices).reset_index(drop=True)

        return df

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
            cols_sorted = [
                col for _, col in sorted(cols_with_conf, key=lambda x: x[0], reverse=True)
            ]
            if len(cols_sorted) == 1:
                df_result[field] = df[cols_sorted[0]]
            else:
                combined = pd.concat([df[col] for col in cols_sorted], axis=1)
                df_result[field] = combined.bfill(axis=1).iloc[:, 0]

        return df_result

    def process(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Ejecuta todo el pipeline y retorna un resultado estructurado con:
        - mapping: mapeo de columnas origen → campo taxonomía
        - confidence_report: reporte de confianza del mapeo
        - products: lista de diccionarios con productos normalizados y enriquecidos
        - validation_report: errores y advertencias de calidad
        - duplicates: productos con código duplicado
        - summary: métricas resumidas
        """
        print(f"📥 Iniciando process() con DataFrame de shape: {df.shape}")

        # 0. Prevenir AttributeError con columnas
        df.columns = df.columns.astype(str)

        # 🔥 INFERIR CATEGORÍAS DESDE TÍTULOS (Y ELIMINAR FILAS DE TÍTULO)
        print("🔄 Infiriendo categorías desde títulos...")
        df = self._inferir_categorias_de_titulos(df)
        print(f"📊 DataFrame después de inferir títulos: {df.shape}")

        # 🔥 DETECTAR CONTEXTO GLOBAL (moneda y unidad por defecto)
        context = FileContext()
        context.currency = ContextDetector.detect_currency(df)
        context.default_unit = ContextDetector.detect_unit(df)
        self.normalizer.context = context
        self.normalizer.default_unit = context.default_unit
        print(f"💱 Contexto: moneda={context.currency}, unidad={context.default_unit}")

        # 1. MAPEO DE COLUMNAS
        print("🔍 Mapeando columnas...")
        mapping = self.mapper.map_columns(df)
        confidence_report = self.mapper.get_confidence_report(mapping)

        # 🔥 FORZAR QUE 'categoria_heredada' sea mapeada con confianza máxima
        if 'categoria_heredada' in df.columns:
            mapping['categoria_heredada'] = ('categoria', 1.0)

        # 1.5 CONSOLIDACIÓN (elimina columnas duplicadas)
        print("🧩 Consolidando columnas...")
        df_clean = self.normalize_and_consolidate(df, mapping)

        # ------------------------------------------------------------
        # FILTROS DE LIMPIEZA DE FILAS BASURA
        # ------------------------------------------------------------
        # A. Eliminar filas donde 'codigo' y 'descripcion' son nulos o vacios
        if 'codigo' in df_clean.columns and 'descripcion' in df_clean.columns:
            mask_codigo = df_clean['codigo'].isna() | (df_clean['codigo'].astype(str).str.strip() == '')
            mask_desc = df_clean['descripcion'].isna() | (df_clean['descripcion'].astype(str).str.strip() == '')
            df_clean = df_clean[~(mask_codigo & mask_desc)]
        elif 'codigo' in df_clean.columns:
            mask_codigo = df_clean['codigo'].isna() | (df_clean['codigo'].astype(str).str.strip() == '')
            df_clean = df_clean[~mask_codigo]

        # B. Eliminar filas donde 'codigo' y 'precio_lista' están vacios
        if 'codigo' in df_clean.columns and 'precio_lista' in df_clean.columns:
            mask_codigo_vacio = df_clean['codigo'].isna() | (df_clean['codigo'].astype(str).str.strip() == '')
            mask_precio_vacio = df_clean['precio_lista'].isna() | (df_clean['precio_lista'].astype(str).str.strip() == '')
            df_clean = df_clean[~(mask_codigo_vacio & mask_precio_vacio)]

        # C. Eliminar filas donde 'codigo' literalmente dice "CÓDIGO", "CÓDIGO" o "COD"
        if 'codigo' in df_clean.columns:
            codigo_str = df_clean['codigo'].astype(str).str.strip().str.upper()
            mascara_encabezado = codigo_str.isin(['CODIGO', 'CÓDIGO', 'COD'])
            df_clean = df_clean[~mascara_encabezado]

        print(f"🧹 DataFrame después de limpieza: {df_clean.shape}")

        # 2. NORMALIZACIÓN DE DATOS (síntesis de atributos)
        print("🛠️ Normalizando datos...")
        normalized_products = []
        for _, row in df_clean.iterrows():
            normalized = self.normalizer.normalize_row(row)
            normalized_products.append(normalized)
        print(f"📦 {len(normalized_products)} productos normalizados")

        # 2.5 CATEGORIZACIÓN POR REGLAS (local, sin IA)
        if self.enable_categorizer and self.categorizer:
            print("📋 Aplicando categorización por reglas...")
            normalized_products = self.categorizer.enrich(normalized_products)
            print(f"📋 {len(normalized_products)} productos después de reglas")

        # 2.6 ENRIQUECIMIENTO SEMÁNTICO CON IA (Gemini)
        # Se ejecuta sobre las categorías ya normalizadas y regladas
        print(f"🧠 Verificando IA: enable_ai={self.enable_ai}, ai_enricher={self.ai_enricher is not None}")
        if self.enable_ai and self.ai_enricher:
            print("🧠 Aplicando enriquecimiento con IA...")
            try:
                before = len(normalized_products)
                normalized_products = self.ai_enricher.enrich(normalized_products)
                after = len(normalized_products)
                print(f"✅ Productos después de IA: {after} (cambiaron: {before != after})")
            except Exception as e:
                print(f"❌ Error en enriquecimiento IA: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("⚠️ IA deshabilitada o no inicializada. Saltando enriquecimiento.")

        # 3. VALIDACIÓN
        print("✅ Validando productos...")
        validation_report = self.validator.validate_all(normalized_products)

        # 4. DETECTAR DUPLICADOS (básico por código)
        duplicates = self.find_duplicates(normalized_products)

        # 5. GENERAR RESUMEN EJECUTIVO
        summary = self.generate_summary(normalized_products, validation_report, duplicates)

        print("🏁 Procesamiento completado.\n")
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
