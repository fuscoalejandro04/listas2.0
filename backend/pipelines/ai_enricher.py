"""
Módulo de Enriquecimiento Semántico con IA (LLM) - Gemini 2.5 Flash.
Optimizado por deduplicación sobre valores únicos de 'categoria'.
Mantiene caché, modo simulación y manejo robusto de errores.
"""
import json
import hashlib
import os
from typing import List, Dict, Any, Optional, Set
import streamlit as st


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
        self.model = model
        self.temperature = temperature
        self.cache: Dict[str, Dict[str, Any]] = {}  # Mantenemos pero no usaremos en esta prueba

        # 1. Obtener API key
        self.api_key = api_key
        if not self.api_key:
            try:
                import streamlit as st
                if "GEMINI_API_KEY" in st.secrets:
                    self.api_key = st.secrets["GEMINI_API_KEY"]
                    print("🔑 Clave API leída desde st.secrets")
            except ImportError:
                print("⚠️ No se pudo importar streamlit")
            except Exception as e:
                print(f"⚠️ Error al leer st.secrets: {e}")

        if not self.api_key:
            self.api_key = os.getenv("GEMINI_API_KEY")
            if self.api_key:
                print("🔑 Clave API leída desde variable de entorno GEMINI_API_KEY")

        self.simulate = simulate or not self.api_key

        if self.simulate:
            print("⚠️ AIEnricher en modo SIMULACIÓN (sin API key o forzado).")
        else:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                print("✅ Cliente Gemini inicializado correctamente.")
            except ImportError:
                print("⚠️ google-genai no instalado. Cambiando a modo simulación.")
                self.simulate = True
                self.client = None
            except Exception as e:
                print(f"⚠️ Error al inicializar cliente Gemini: {e}. Modo simulación.")
                self.simulate = True
                self.client = None

        print(f"🔑 AIEnricher: simulate={self.simulate}, api_key={'OK' if self.api_key else 'NO'}")

    def _normalize_category(self, cat: str) -> str:
        """Normaliza una categoría: mayúsculas, sin espacios extra."""
        if not cat:
            return cat
        return cat.strip().upper()

    def enrich(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        print(f"🧠 AIEnricher.enrich() llamado con {len(products)} productos")
        if not products:
            return products

        # 1. Extraer categorías únicas normalizadas
        categoria_set: Set[str] = set()
        for p in products:
            cat = p.get('categoria')
            if not cat:
                cat = p.get('categoría')
            if cat and isinstance(cat, str) and cat.strip():
                categoria_set.add(self._normalize_category(cat))

        print(f"📋 Categorías únicas normalizadas: {len(categoria_set)}")
        if not categoria_set:
            return products

        # 2. Obtener el mapeo (SIN CACHÉ para esta prueba)
        # Forzamos a que siempre se genere nuevo mapping
        mapping = self._generate_mapping(list(categoria_set))
        print(f"📊 Mapping generado para {len(mapping)} categorías")

        # Debug
        st.write("🔍 **Debug del mapping:**")
        st.write(f"Claves del mapping: {list(mapping.keys())[:10]}")
        st.write(f"Primeras categorías a enriquecer: {list(categoria_set)[:10]}")
        if products:
            primer_producto = products[0]
            cat_primer = primer_producto.get('categoria', primer_producto.get('categoría', 'N/A'))
            st.write(f"📌 **Primer producto - categoría original:** '{cat_primer}'")
            st.write(f"📌 **Categoría normalizada:** '{self._normalize_category(cat_primer if cat_primer else '')}'")

        # 3. Aplicar el mapeo
        productos_actualizados = 0
        for p in products:
            cat_original = p.get('categoria')
            if not cat_original:
                cat_original = p.get('categoría')
            if cat_original and isinstance(cat_original, str):
                cat_clean = self._normalize_category(cat_original)
                if cat_clean in mapping:
                    enriched = mapping[cat_clean]
                    # Siempre asignar confianza
                    confianza = enriched.get('confianza', 0.0)
                    p['confianza_ia'] = confianza
                    if confianza > 0:
                        productos_actualizados += 1
                    if enriched.get('categoria_razonada'):
                        p['categoria'] = enriched['categoria_razonada']
                        if 'categoría' in p:
                            p['categoría'] = enriched['categoria_razonada']
                    if enriched.get('linea_producto'):
                        p['linea_producto'] = enriched['linea_producto']
                else:
                    p['confianza_ia'] = 0.0

        print(f"✅ Productos actualizados (con confianza > 0): {productos_actualizados} de {len(products)}")
        st.write(f"📊 **Productos con confianza > 0: {productos_actualizados}**")
        return products

    def _generate_mapping(self, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        """Genera mapping sin usar caché (para pruebas)."""
        if self.simulate:
            print("🔄 Usando simulación (sin IA)")
            return self._simulate_mapping(categories)
        else:
            print("🤖 Llamando a Gemini...")
            prompt = self._build_prompt(categories)
            response = self._call_llm(prompt)
            return self._parse_response(response, categories)

    def _simulate_mapping(self, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        mapping = {}
        for cat in categories:
            cat_upper = cat
            linea = None
            categoria_razonada = cat
            lineas_keywords = ['CLASSIC', 'PROFESSIONAL', 'EXPERT', 'PREMIUM', 'BASIC', 'CAR EXPERT']
            for kw in lineas_keywords:
                if kw in cat_upper:
                    linea = kw.capitalize()
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
            print("✅ Llamada a Gemini exitosa")
            return response.text
        except Exception as e:
            print(f"❌ Error en llamada a Gemini: {e}. Cambiando a modo simulación.")
            self.simulate = True
            return "{}"

    def _parse_response(self, response: str, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        try:
            data = json.loads(response)
            if not isinstance(data, dict):
                raise ValueError("La respuesta no es un diccionario JSON")
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
