""" Módulo Procesador - Orquesta todo el pipeline ETL. Ya no depende de
importers, recibe el DataFrame directamente. Integra la consolidación,
normalización estructural, categorización por reglas, IA y validación. """
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
    
    def __init__(self):
        self.column_mapper = ColumnMapper()
        self.normalizer = DataNormalizer()
        self.validator = Validator()
        self.rule_categorizer = RuleCategorizer()
        
        # Inicializamos el cerebro de IA
        try:
            self.ai_enricher = AIEnricher()
            self.ai_enabled = True
        except Exception as e:
            print(f"⚠️ IA deshabilitada: {e}")
            self.ai_enabled = False

    def process(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        # 1. Detección de contexto y mapeo (CORREGIDO)
        context = FileContext()
        # Verificamos si existe el método para no romper el código
        if hasattr(ContextDetector, 'detect_currency'):
            context.currency = ContextDetector.detect_currency(df)
            
        mapped_df = self.column_mapper.map_columns(df)
        
        # 2. Normalización básica
        normalized_df = self.normalizer.normalize(mapped_df, context)
        
        # 3. Categorización por reglas locales (Rápido y gratis)
        processed_df = self.rule_categorizer.categorize(normalized_df)
        
        # 4. Enriquecimiento Semántico con IA
        if getattr(self, 'ai_enabled', False) and 'categoria' in processed_df.columns:
            # Extraemos solo las categorías únicas
            categorias_unicas = processed_df['categoria'].dropna().unique().tolist()
            
            if categorias_unicas:
                # Llamamos a la API de Gemini (solo enviamos la lista deduplicada)
                ai_results = self.ai_enricher.enrich_categories(categorias_unicas)
                
                # Mapeamos los resultados de vuelta al DataFrame
                if ai_results:
                    for original_cat, inferencia in ai_results.items():
                        mask = processed_df['categoria'] == original_cat
                        
                        if isinstance(inferencia, dict):
                            cat_razonada = inferencia.get('categoria_razonada')
                            linea_prod = inferencia.get('linea_producto')
                            confianza = inferencia.get('confianza', 0.0)

                            if cat_razonada:
                                processed_df.loc[mask, 'categoria_razonada'] = cat_razonada
                                
                            # Solo pisamos la línea si la IA encontró una
                            if linea_prod:
                                processed_df.loc[mask, 'linea_producto'] = linea_prod
                                
                            processed_df.loc[mask, 'confianza_ia'] = confianza

        # 5. Validación final
        reporte_calidad = self.validator.validate(processed_df)
        
        return processed_df, reporte_calidad
