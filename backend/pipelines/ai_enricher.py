""" Módulo de Enriquecimiento Semántico con IA (LLM) - Optimizado por
Deduplicación. Razona sobre los valores únicos de 'categoria' para inferir:
  - Categoría real (corregida semánticamente)
  - Línea/Calidad del producto (Classic, Professional, Expert, etc.)
"""
import json
import os
from typing import List, Dict, Any
from google import genai
from google.genai import types

class AIEnricher:
    """ 
    Enriquece productos normalizados usando Gemini Flash, 
    leyendo las credenciales de forma segura desde Streamlit Secrets. 
    """
    
    def __init__(self):
        api_key = None
        
        # 1. Intentar leer desde los secretos de Streamlit (Entorno Cloud)
        try:
            import streamlit as st
            if "GEMINI_API_KEY" in st.secrets:
                api_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
            
        # 2. Alternativa local por si las moscas
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
            
        if not api_key:
            raise ValueError("❌ No se encontró la GEMINI_API_KEY en st.secrets.")

        self.client = genai.Client(api_key=api_key)

    def enrich_categories(self, unique_categories: List[str]) -> Dict[str, Any]:
        """Envía la lista deduplicada a Gemini y retorna un diccionario con las inferencias."""
        if not unique_categories:
            return {}

        categories_str = json.dumps(unique_categories, ensure_ascii=False)

        prompt = f"""
        Eres un sistema de enriquecimiento semántico para catálogos de productos industriales.
        Recibirás una lista de valores de la columna "categoría" tal como vienen del archivo original.
        Tu tarea es analizar CADA valor y deducir:
        1. categoria_razonada: la categoría semántica real (ej. Taladros, Amoladoras, Sierras, Accesorios, etc.).
        - Si el valor contiene palabras como "CLASSIC", "PROFESSIONAL", "EXPERT", "PREMIUM", etc., ignóralas para la categoría.
        2. linea_producto: si el valor contiene una línea comercial explícita (CLASSIC, PROFESSIONAL, EXPERT, PREMIUM, BASIC, etc.), extráela. Si no, pon null.
        3. confianza: un número entre 0 y 1 que indique qué tan seguro estás de tu inferencia.
        
        Devuelve ÚNICAMENTE un JSON válido con la siguiente estructura (es un diccionario donde la clave es la categoría original):
        {{
            "CATEGORIA_ORIGINAL_1": {{ "categoria_razonada": "Categoría Real", "linea_producto": "Línea o null", "confianza": 0.95 }},
            "CATEGORIA_ORIGINAL_2": {{ "categoria_razonada": "Otra Categoría", "linea_producto": null, "confianza": 0.90 }}
        }}
        
        Lista de categorías a analizar:
        {categories_str}
        """

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Error al conectar con Google Gemini: {str(e)}")
            return {}
