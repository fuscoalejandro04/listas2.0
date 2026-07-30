"""
Módulo de Enriquecimiento Semántico con IA (LLM) - Optimizado por Deduplicación.
Razona sobre los valores únicos de 'categoria' para inferir:
- Categoría real (corregida semánticamente)
- Línea/Calidad del producto (Classic, Professional, Expert, etc.)
El enfoque reduce drásticamente el número de llamadas a la API (de N productos a U categorías únicas).
"""
import json
import hashlib
import os
from typing import List, Dict, Any, Optional, Set, Tuple


class AIEnricher:
    """
    Enriquece productos normalizados usando un LLM, pero operando sobre valores únicos
    de 'categoria' para minimizar costos y latencia.
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = "gpt-4o-mini",
                 max_tokens: int = 1000,
                 temperature: float = 0.1,
                 simulate: bool = False):
        """
        Args:
            api_key: Clave de API (desde config o env). Si es None, intenta usar OPENAI_API_KEY.
            model: Modelo a usar (OpenAI, Gemini, etc.)
            max_tokens: Máximo de tokens por respuesta (para el diccionario completo)
            temperature: Temperatura del LLM (baja para respuestas deterministas)
            simulate: Si True, no llama a la API real y devuelve datos simulados.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.simulate = simulate or not self.api_key
        self.cache = {}  # Cache: hash(lista_categorias) -> diccionario_mapeo

        if self.simulate:
            print("⚠️ AIEnricher en modo SIMULACIÓN (sin API key). Los enriquecimientos serán ficticios.")

    def enrich(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enriquece los productos operando sobre valores únicos de 'categoria'.
        Retorna la misma lista de productos pero con campos actualizados.
        """
        if not products:
            return products

        # 1. Extraer valores únicos de 'categoria' (ignorando None, vacíos y strings solo de espacio)
        categoria_set: Set[str] = set()
        for p in products:
            cat = p.get('categoria')
            if cat and isinstance(cat, str) and cat.strip():
                categoria_set.add(cat.strip())

        # Si no hay categorías, no hay nada que enriquecer
        if not categoria_set:
            return products

        # 2. Obtener el diccionario de mapeo para los valores únicos
        mapping = self._get_mapping_for_categories(list(categoria_set))

        # 3. Aplicar el mapeo a cada producto (O(1) por producto)
        for p in products:
            cat_original = p.get('categoria')
            if cat_original and isinstance(cat_original, str):
                cat_clean = cat_original.strip()
                if cat_clean in mapping:
                    enriched = mapping[cat_clean]
                    p['categoria'] = enriched.get('categoria_razonada')
                    p['linea_producto'] = enriched.get('linea_producto')
                    p['confianza_ia'] = enriched.get('confianza', 0.0)
                # Si no está en el mapeo (por alguna razón), dejar como estaba

        return products

    def _get_mapping_for_categories(self, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene el mapeo semántico para la lista de categorías únicas.
        Retorna un diccionario: {categoria_original: {"categoria_razonada": str, "linea_producto": str, "confianza": float}}
        """
        # Ordenar para estabilidad del caché
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

            # Detectar líneas de producto
            lineas_keywords = ['CLASSIC', 'PROFESSIONAL', 'EXPERT', 'PREMIUM', 'BASIC', 'CAR EXPERT']
            for kw in lineas_keywords:
                if kw in cat_upper:
                    linea = kw.capitalize()
                    # Remover la palabra clave de la categoría
                    categoria_razonada = cat_upper.replace(kw, '').strip()
                    break

            # Si no se detectó línea, intentar por 'PRO' o 'BL' en modelo (no tenemos modelo aquí, pero podemos dejar)
            # Si queda vacía, usar la original
            if not categoria_razonada:
                categoria_razonada = cat

            mapping[cat] = {
                "categoria_razonada": categoria_razonada,
                "linea_producto": linea,
                "confianza": 0.85  # simulado
            }
        return mapping

    def _build_prompt(self, categories: List[str]) -> str:
        """
        Construye el prompt para el LLM. Pide un diccionario de traducción.
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
        Llama al LLM con manejo de errores y caché.
        """
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Eres un experto en clasificación de productos industriales. Siempre respondes en JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}  # Forzar JSON
            )
            return response.choices[0].message.content
        except ImportError:
            print("⚠️ OpenAI no está instalado. Cambiando a modo simulación.")
            self.simulate = True
            return "{}"
        except Exception as e:
            print(f"Error en LLM: {e}. Cambiando a modo simulación.")
            self.simulate = True
            return "{}"

    def _parse_response(self, response: str, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Parsea la respuesta del LLM y la valida contra la lista de categorías original.
        Si falta alguna categoría, la rellena con un valor por defecto (sin cambios).
        """
        try:
            data = json.loads(response)
            # Verificar que data sea un diccionario
            if not isinstance(data, dict):
                raise ValueError("La respuesta no es un diccionario JSON")

            # Asegurar que todas las categorías estén presentes
            for cat in categories:
                if cat not in data:
                    # Si falta, mantener la categoría original sin cambios
                    data[cat] = {
                        "categoria_razonada": cat,
                        "linea_producto": None,
                        "confianza": 0.0
                    }
                else:
                    # Validar que los campos esperados existan
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
            print(f"⚠️ Error al parsear respuesta del LLM: {e}. Usando simulación.")
            return self._simulate_mapping(categories)
