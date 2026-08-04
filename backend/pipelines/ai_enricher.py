"""
Módulo de Enriquecimiento Semántico con IA (LLM) - Gemini 2.5 Flash.
Optimizado por deduplicación sobre valores únicos de 'categoria'.
Mantiene caché, modo simulación y manejo robusto de errores.
"""
import json
import hashlib
import os
from typing import List, Dict, Any, Optional, Set


class AIEnricher:
    """
    Enriquece productos normalizados usando Gemini Flash,
    operando sobre valores únicos de 'categoria' para minimizar costos y latencia.
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = "gemini-2.5-flash",
                 temperature: float = 0.1,
                 simulate: bool = False):
        """
        Args:
            api_key: Clave de API de Google. Si es None, intenta leer de st.secrets o ENV.
            model: Modelo Gemini (por defecto gemini-2.5-flash).
            temperature: Temperatura (baja para respuestas deterministas).
            simulate: Si True, no llama a la API real y devuelve datos simulados.
        """
        self.model = model
        self.temperature = temperature
        self.cache: Dict[str, Dict[str, Any]] = {}

        # 1. Obtener API key
        self.api_key = api_key
        if not self.api_key:
            # Intentar desde st.secrets (si estamos en Streamlit)
            try:
                import streamlit as st
                if "GEMINI_API_KEY" in st.secrets:
                    self.api_key = st.secrets["GEMINI_API_KEY"]
            except ImportError:
                pass

        if not self.api_key:
            self.api_key = os.getenv("GEMINI_API_KEY")

        # 2. Decidir modo simulación
        self.simulate = simulate or not self.api_key

        if self.simulate:
            print("⚠️ AIEnricher en modo SIMULACIÓN (sin API key o forzado).")
        else:
            # Inicializar cliente Gemini
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                print("⚠️ google-genai no instalado. Cambiando a modo simulación.")
                self.simulate = True
                self.client = None
            except Exception as e:
                print(f"⚠️ Error al inicializar cliente Gemini: {e}. Modo simulación.")
                self.simulate = True
                self.client = None

    def enrich(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enriquece los productos operando sobre valores únicos de 'categoria'.
        Retorna la misma lista de productos pero con campos actualizados.
        """
        if not products:
            return products

        # 1. Extraer categorías únicas (ignorando nulos, vacíos y espacios)
        categoria_set: Set[str] = set()
        for p in products:
            cat = p.get('categoria')
            if cat and isinstance(cat, str) and cat.strip():
                categoria_set.add(cat.strip())

        if not categoria_set:
            return products

        # 2. Obtener el mapeo (desde caché o vía IA)
        mapping = self._get_mapping_for_categories(list(categoria_set))

        # 3. Aplicar el mapeo a cada producto
        for p in products:
            cat_original = p.get('categoria')
            if cat_original and isinstance(cat_original, str):
                cat_clean = cat_original.strip()
                if cat_clean in mapping:
                    enriched = mapping[cat_clean]
                    # Solo sobreescribir si hay un valor válido
                    if enriched.get('categoria_razonada'):
                        p['categoria'] = enriched['categoria_razonada']
                    if enriched.get('linea_producto'):
                        p['linea_producto'] = enriched['linea_producto']
                    # Siempre asignar confianza (puede ser 0)
                    p['confianza_ia'] = enriched.get('confianza', 0.0)
                # Si no está en mapping (por error), se deja como estaba

        return products

    def _get_mapping_for_categories(self, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene el mapeo semántico para la lista de categorías únicas.
        Retorna: {categoria_original: {"categoria_razonada": str, "linea_producto": str, "confianza": float}}
        """
        categories_sorted = sorted(categories)
        cache_key = hashlib.md5(json.dumps(categories_sorted).encode()).hexdigest()

        if cache_key in self.cache:
            return self.cache[cache_key]

        # Si no está en caché, procesar
        if self.simulate:
            mapping = self._simulate_mapping(categories_sorted)
        else:
            prompt = self._build_prompt(categories_sorted)
            response = self._call_llm(prompt)
            mapping = self._parse_response(response, categories_sorted)

        self.cache[cache_key] = mapping
        return mapping

    def _simulate_mapping(self, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Simula el enriquecimiento sin llamar a la API.
        Detecta líneas de producto por palabras clave y limpia la categoría.
        """
        mapping = {}
        for cat in categories:
            cat_upper = cat.upper()
            linea = None
            categoria_razonada = cat

            lineas_keywords = ['CLASSIC', 'PROFESSIONAL', 'EXPERT', 'PREMIUM', 'BASIC', 'CAR EXPERT']
            for kw in lineas_keywords:
                if kw in cat_upper:
                    linea = kw.capitalize()
                    # Remover la palabra clave de la categoría
                    categoria_razonada = cat_upper.replace(kw, '').strip()
                    break

            if not categoria_razonada:
                categoria_razonada = cat

            mapping[cat] = {
                "categoria_razonada": categoria_razonada,
                "linea_producto": linea,
                "confianza": 0.85
            }
        return mapping

    def _build_prompt(self, categories: List[str]) -> str:
        """
        Construye el prompt para Gemini. Pide un diccionario de traducción.
        """
        categories_list = "\n".join([f"- {cat}" for cat in categories])

        prompt = f"""
Eres un sistema de enriquecimiento semántico para catálogos de productos industriales.

Recibirás una lista de valores de la columna "categoría" tal como vienen del archivo original.
Tu tarea es analizar CADA valor y deducir:
1. **categoria_razonada**: la categoría semántica real (ej. Taladros, Amoladoras, Sierras, Accesorios, etc.).
   - Si el valor contiene palabras como "CLASSIC", "PROFESSIONAL", "EXPERT", "PREMIUM", etc., ignóralas para la categoría.
2. **linea_producto**: si el valor contiene una línea comercial explícita (CLASSIC, PROFESSIONAL, EXPERT, PREMIUM, BASIC, etc.), extráela. Si no, pon null.
3. **confianza**: un número entre 0 y 1 que indique qué tan seguro estás de tu inferencia.

Devuelve ÚNICAMENTE un JSON válido con la siguiente estructura (es un diccionario donde la clave es la categoría original):
{{
  "CATEGORIA_ORIGINAL_1": {{
    "categoria_razonada": "Categoría Real",
    "linea_producto": "Línea o null",
    "confianza": 0.95
  }},
  "CATEGORIA_ORIGINAL_2": {{
    "categoria_razonada": "Otra Categoría",
    "linea_producto": null,
    "confianza": 0.90
  }}
}}

Lista de categorías a analizar:
{categories_list}

Ejemplo de entrada:
- Categoría: "★★★★★ PROFESSIONAL"
Salida esperada:
{{
  "★★★★★ PROFESSIONAL": {{
    "categoria_razonada": "Taladros",
    "linea_producto": "PROFESSIONAL",
    "confianza": 0.95
  }}
}}

Ahora, analiza la lista de categorías proporcionada.
"""
        return prompt

    def _call_llm(self, prompt: str) -> str:
        """
        Llama a Gemini con manejo de errores.
        """
        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=self.temperature
                ),
            )
            return response.text
        except Exception as e:
            print(f"❌ Error en llamada a Gemini: {e}. Cambiando a modo simulación.")
            self.simulate = True
            return "{}"

    def _parse_response(self, response: str, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Parsea la respuesta del LLM y valida contra la lista de categorías originales.
        Si falta alguna categoría, la rellena con un valor por defecto (sin cambios).
        """
        try:
            data = json.loads(response)
            if not isinstance(data, dict):
                raise ValueError("La respuesta no es un diccionario JSON")

            # Asegurar que todas las categorías estén presentes
            for cat in categories:
                if cat not in data:
                    data[cat] = {
                        "categoria_razonada": cat,
                        "linea_producto": None,
                        "confianza": 0.0
                    }
                else:
                    entry = data[cat]
                    if not isinstance(entry, dict):
                        data[cat] = {
                            "categoria_razonada": cat,
                            "linea_producto": None,
                            "confianza": 0.0
                        }
                    else:
                        if "categoria_razonada" not in entry:
                            entry["categoria_razonada"] = cat
                        if "linea_producto" not in entry:
                            entry["linea_producto"] = None
                        if "confianza" not in entry:
                            entry["confianza"] = 0.0
            return data
        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️ Error al parsear respuesta: {e}. Usando simulación.")
            return self._simulate_mapping(categories)
