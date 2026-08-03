""" Módulo Procesador - Orquesta todo el pipeline ETL. Ya no depende de
importers, recibe el DataFrame directamente. Integra la consolidación,
normalización estructural, categorización por reglas y validación. """
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
        # 1. Detección de contexto
        context = FileContext()
        if hasattr(ContextDetector, 'detect_currency'):
            context.currency = ContextDetector.detect_currency(df)
            
        # 2. Mapeo de columnas (CORREGIDO)
        # map_columns devuelve un dict {nombre_viejo: nombre_nuevo}
        mapping_dict = self.column_mapper.map_columns(df) 
        # Aplicamos el diccionario para renombrar las columnas del DataFrame
        mapped_df = df.rename(columns=mapping_dict)
        
        # 3. Normalización básica (COMPLETAMENTE ADAPTATIVA)
        import inspect
        
        if hasattr(self.normalizer, 'normalize_dataframe'):
            normalized_df = self.normalizer.normalize_dataframe(mapped_df, context)
        elif hasattr(self.normalizer, 'normalize_row'):
            # Revisamos cuántos argumentos espera realmente tu método
            sig = inspect.signature(self.normalizer.normalize_row)
            if len(sig.parameters) > 1: # Espera row y context
                normalized_df = mapped_df.apply(lambda row: self.normalizer.normalize_row(row, context), axis=1)
            else: # Solo espera row
                normalized_df = mapped_df.apply(lambda row: self.normalizer.normalize_row(row), axis=1)
        else:
            # Alternativa de emergencia
            metodos = [m for m in dir(self.normalizer) if not m.startswith('_')]
            if metodos:
                metodo_principal = getattr(self.normalizer, metodos[0])
                sig = inspect.signature(metodo_principal)
                if len(sig.parameters) > 1:
                    normalized_df = mapped_df.apply(lambda row: metodo_principal(row, context), axis=1)
                else:
                    normalized_df = mapped_df.apply(lambda row: metodo_principal(row), axis=1)
            else:
                normalized_df = mapped_df.copy()
        
        # 4. Categorización por reglas locales
        if hasattr(self.rule_categorizer, 'categorize'):
            processed_df = self.rule_categorizer.categorize(normalized_df)
        else:
            processed_df = normalized_df
        
        # 5. Enriquecimiento Semántico con IA
        if getattr(self, 'ai_enabled', False) and 'categoria' in processed_df.columns:
            # Extraemos solo las categorías únicas
            categorias_unicas = processed_df['categoria'].dropna().unique().tolist()
            
            if categorias_unicas:
                # Llamamos a la API de Gemini
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
                                
                            if linea_prod:
                                processed_df.loc[mask, 'linea_producto'] = linea_prod
                                
                            processed_df.loc[mask, 'confianza_ia'] = confianza

        # 6. Validación final
        reporte_calidad = {}
        if hasattr(self.validator, 'validate'):
            reporte_calidad = self.validator.validate(processed_df)
        
        return processed_df, reporte_calidad
