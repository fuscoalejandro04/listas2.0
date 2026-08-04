""" 
Módulo Procesador - Orquesta todo el pipeline ETL.
Integra mapeo inteligente, normalización estructural, categorización por reglas, IA y validación. 
"""
import pandas as pd
import inspect
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
        
        # Inicializamos la IA
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
            
        # 2. Mapeo de columnas (SOLUCIÓN AL ERROR DEL CSV VACÍO)
        mapping_result = self.column_mapper.map_columns(df) 
        
        if isinstance(mapping_result, dict):
            # Obtenemos los nombres oficiales de la taxonomía
            taxonomy_keys = [f.name for f in TAXONOMY.fields] if hasattr(TAXONOMY, 'fields') else ['codigo', 'nombre_articulo', 'precio_lista']
            
            # Detectamos si el diccionario viene al revés {col_taxonomia: col_original}
            if any(k in taxonomy_keys for k in mapping_result.keys()):
                # Lo invertimos al formato correcto que requiere Pandas {col_original: col_taxonomia}
                rename_dict = {v: k for k, v in mapping_result.items() if isinstance(v, str)}
            else:
                rename_dict = mapping_result
                
            mapped_df = df.rename(columns=rename_dict)
        elif isinstance(mapping_result, pd.DataFrame):
            mapped_df = mapping_result
        else:
            mapped_df = df.copy()
        
        # 3. Normalización básica (Blindada)
        if hasattr(self.normalizer, 'normalize_dataframe'):
            normalized_df = self.normalizer.normalize_dataframe(mapped_df, context)
        else:
            norm_func = getattr(self.normalizer, 'normalize_row', None)
            if not norm_func:
                metodos = [m for m in dir(self.normalizer) if not m.startswith('_')]
                if metodos:
                    norm_func = getattr(self.normalizer, metodos[0])
            
            if norm_func:
                sig = inspect.signature(norm_func)
                uses_context = len(sig.parameters) > 1
                
                def safe_normalize(row):
                    try:
                        res = norm_func(row, context) if uses_context else norm_func(row)
                        if res is None:
                            return row
                        # Si devuelve un modelo Product (Pydantic), lo convertimos a fila de Pandas
                        if hasattr(res, 'dict'): 
                            return pd.Series(res.dict())
                        if isinstance(res, dict):
                            return pd.Series(res)
                        return res
                    except Exception:
                        return row
                
                normalized_df = mapped_df.apply(safe_normalize, axis=1)
            else:
                normalized_df = mapped_df.copy()
                
        if isinstance(normalized_df, pd.Series):
            normalized_df = pd.DataFrame(normalized_df.tolist(), index=mapped_df.index)
        
        # 4. Categorización por reglas locales
        if hasattr(self.rule_categorizer, 'categorize'):
            processed_df = self.rule_categorizer.categorize(normalized_df)
            if isinstance(processed_df, pd.Series):
                processed_df = pd.DataFrame(processed_df.tolist(), index=normalized_df.index)
        else:
            processed_df = normalized_df.copy()
        
        # 5. Enriquecimiento Semántico con IA
        if getattr(self, 'ai_enabled', False) and 'categoria' in processed_df.columns:
            # Filtramos para no enviarle a la IA datos vacíos o nulos
            categorias = processed_df['categoria'].dropna().astype(str)
            categorias = categorias[categorias.str.strip() != '']
            categorias_unicas = categorias.unique().tolist()
            
            if categorias_unicas:
                ai_results = self.ai_enricher.enrich_categories(categorias_unicas)
                
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
