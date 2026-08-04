"""
Módulo Procesador - Orquesta todo el pipeline ETL.
Integra consolidación, normalización estructural, categorización por reglas, IA (Gemini) y validación.
"""
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
import streamlit as st  # ← Importamos para usar mensajes visuales

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
        st.toast("🚀 Inicializando PipelineProcessor...")  # 👈 Mensaje visual

        self.mapper = ColumnMapper(confidence_threshold)
        self.normalizer = DataNormalizer()
        self.validator = Validator()
        self.enable_categorizer = enable_categorizer
        self.enable_ai = enable_ai

        if self.enable_categorizer:
            self.categorizer = RuleCategorizer()
            st.toast("✅ RuleCategorizer inicializado")

        # Inicializar IA (si está habilitada)
        self.ai_enricher = None
        self.ai_enabled = False  # ← Bandera para saber si la IA está operativa

        if self.enable_ai:
            st.info("🧠 Inicializando AIEnricher...")
            try:
                self.ai_enricher = AIEnricher()
                self.ai_enabled = True
                st.success("✅ Módulo de IA inicializado correctamente")
            except Exception as e:
                st.error(f"❌ Error al inicializar AIEnricher: {e}")
                self.ai_enabled = False
        else:
            st.warning("⚠️ La IA está deshabilitada (enable_ai=False)")

        st.success("✅ PipelineProcessor listo")

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
        st.info(f"📥 Iniciando process() con DataFrame de shape: {df.shape}")

        # 0. Prevenir AttributeError con columnas
        df.columns = df.columns.astype(str)

        # Inferir categorías desde títulos
        df = self._inferir_categorias_de_titulos(df)

        # Detectar contexto
        context = FileContext()
        context.currency = ContextDetector.detect_currency(df)
        context.default_unit = ContextDetector.detect_unit(df)
        self.normalizer.context = context
        self.normalizer.default_unit = context.default_unit

        # 1. Mapeo de columnas
        mapping = self.mapper.map_columns(df)
        confidence_report = self.mapper.get_confidence_report(mapping)

        if 'categoria_heredada' in df.columns:
            mapping['categoria_heredada'] = ('categoria', 1.0)

        # 1.5 Consolidación
        df_clean = self.normalize_and_consolidate(df, mapping)

        # Filtros de basura
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

        # 2. Normalización
        normalized_products = []
        for _, row in df_clean.iterrows():
            normalized = self.normalizer.normalize_row(row)
            normalized_products.append(normalized)

        # 2.5 Categorización por reglas
        if self.enable_categorizer and self.categorizer:
            normalized_products = self.categorizer.enrich(normalized_products)

        # =======================================================
        # 🔥 2.6 ENRIQUECIMIENTO CON IA (con mensajes visuales)
        # =======================================================
        if self.ai_enabled and self.ai_enricher:
            st.info("🧠 Aplicando enriquecimiento con IA...")

            # Verificar que la columna 'categoria' existe en los productos
            # Nota: normalized_products es una lista de diccionarios
            tiene_categoria = any('categoria' in p for p in normalized_products)

            if tiene_categoria:
                try:
                    antes = len(normalized_products)
                    normalized_products = self.ai_enricher.enrich(normalized_products)
                    despues = len(normalized_products)
                    st.success(f"✅ IA aplicada a {despues} productos (cambiaron: {antes != despues})")
                except Exception as e:
                    st.error(f"❌ Error en enriquecimiento IA: {e}")
                    import traceback
                    st.code(traceback.format_exc())
            else:
                st.warning("⚠️ No se encontró la columna 'categoria' en los productos. Se omite IA.")
        else:
            st.warning("⚠️ IA deshabilitada o no inicializada. Saltando enriquecimiento.")

        # 3. Validación
        validation_report = self.validator.validate_all(normalized_products)

        # 4. Duplicados
        duplicates = self.find_duplicates(normalized_products)

        # 5. Resumen
        summary = self.generate_summary(normalized_products, validation_report, duplicates)

        st.success("✅ Procesamiento completado")
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
        return {
            'total_rows': len(products),
            'valid_rows': validation['total_products'] - validation['error_count'],
            'error_rows': validation['error_count'],
            'warning_rows': validation['warning_count'],
            'duplicate_count': len(duplicates),
            'quality_score': validation['quality_score']
        }
