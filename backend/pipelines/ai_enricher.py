"""
Módulo de Enriquecimiento Semántico con IA (LLM).
Razona sobre los datos crudos para inferir campos semánticos como:
- Categoría real (corregida)
- Línea/Calidad del producto (Classic, Professional, Expert, etc.)
"""
import json
import hashlib
import os  # 🔥 IMPORTS FALTANTE
from typing import List, Dict, Any, Optional


class AIEnricher:
    """
    Enriquece productos normalizados usando un LLM.
    Se inyecta en el PipelineProcessor.
    
    Modo simulación: si no hay API key, devuelve valores de ejemplo para pruebas.
    """
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "gpt-4o-mini",
                 batch_size: int = 20,
                 max_tokens: int = 500,
                 temperature: float = 0.1,
                 simulate: bool = False):
        """
        Args:
            api_key: Clave de API (desde config o env). Si es None, intenta usar OPENAI_API_KEY.
            model: Modelo a usar (OpenAI, Gemini, etc.)
            batch_size: Número de productos por lote (para reducir costos)
            max_tokens: Máximo de tokens por respuesta
            temperature: Temperatura del LLM (baja para respuestas deterministas)
            simulate: Si True, no llama a la API real y devuelve datos simulados.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.batch_size = batch_size
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.simulate = simulate or not self.api_key  # Si no hay key, activar simulación
        self.cache = {}  # Cache simple en memoria (hash → resultado)
        
        if self.simulate:
            print("⚠️ AIEnricher en modo SIMULACIÓN (sin API key). Los enriquecimientos serán ficticios.")
        
    def enrich(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enriquece una lista de productos con campos inferidos por LLM.
        Retorna la misma lista pero con campos adicionales.
        """
        if not products:
            return products
        
        # 1. Identificar productos que necesitan enriquecimiento
        to_enrich = []
        indices = []
        for idx, p in enumerate(products):
            cat = p.get('categoria', '')
            # Si categoría tiene estrellas, está vacía, o no tiene linea_producto
            if (not cat or '★' in cat or '⭐' in cat or 
                not p.get('linea_producto')):
                to_enrich.append(p)
                indices.append(idx)
        
        if not to_enrich:
            return products
        
        # 2. Procesar en lotes
        enriched_results = []
        for i in range(0, len(to_enrich), self.batch_size):
            batch = to_enrich[i:i + self.batch_size]
            batch_result = self._enrich_batch(batch)
            enriched_results.extend(batch_result)
        
        # 3. Aplicar los resultados enriquecidos a los productos originales
        for idx, enriched in zip(indices, enriched_results):
            if enriched:
                products[idx].update(enriched)
        
        return products
    
    def _enrich_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enriquece un lote con una sola llamada al LLM."""
        if self.simulate:
            return self._simulate_enrichment(batch)
        
        prompt = self._build_prompt(batch)
        response = self._call_llm(prompt)
        return self._parse_response(response, batch)
    
    def _simulate_enrichment(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Simula el enriquecimiento sin llamar a la API.
        Útil para pruebas sin costo.
        """
        results = []
        for p in batch:
            categoria_original = p.get('categoria', '')
            # Detectar línea de producto a partir de palabras clave en la categoría original
            linea = None
            categoria_razonada = categoria_original
            
            # Limpiar estrellas y palabras de línea
            for palabra in ['CLASSIC', 'PROFESSIONAL', 'EXPERT', 'PREMIUM', 'BASIC']:
                if palabra in categoria_original.upper():
                    linea = palabra.capitalize()
                    categoria_razonada = categoria_original.replace('★', '').replace('⭐', '').strip()
                    # Remover la palabra de línea de la categoría
                    categoria_razonada = categoria_razonada.replace(palabra, '').replace(palabra.capitalize(), '').strip()
                    break
            
            # Si no se detectó línea, intentar inferir por modelo o descripción
            if not linea:
                modelo = p.get('modelo', '')
                if 'PRO' in modelo.upper() or 'BL' in modelo.upper():
                    linea = 'Professional'
                elif 'TC' in modelo.upper():
                    linea = 'Classic'
            
            results.append({
                'categoria': categoria_razonada if categoria_razonada else None,
                'linea_producto': linea,
                'confianza_ia': 0.85  # simulado
            })
        return results
    
    def _build_prompt(self, batch: List[Dict[str, Any]]) -> str:
        """Construye el prompt few-shot para el LLM."""
        products_text = []
        for idx, p in enumerate(batch):
            text = f"""
Producto {idx+1}:
- Código: {p.get('codigo', 'N/A')}
- Nombre: {p.get('nombre_articulo', 'N/A')}
- Modelo: {p.get('modelo', 'N/A')}
- Categoría original: {p.get('categoria', 'N/A')}
- Descripción: {p.get('descripcion', '')[:100]}...
"""
            products_text.append(text)
        
        prompt = f"""
Eres un sistema de enriquecimiento de datos para catálogos de productos industriales.
Analiza cada producto y deduce:
1. **Categoría real**: la categoría semántica correcta (ej. Taladros, Amoladoras, Sierras, Accesorios, etc.)
   - Si la "Categoría original" tiene estrellas (★) o palabras como "CLASSIC", "PROFESSIONAL", "EXPERT", ignóralas para la categoría.
2. **Línea/Calidad** (linea_producto): si el producto tiene una línea comercial explícita (ej. "CLASSIC", "PROFESSIONAL", "EXPERT", "PREMIUM"), extráela.
3. **Confianza**: un número entre 0 y 1 que indique qué tan seguro estás de tu inferencia.

Devuelve ÚNICAMENTE un JSON válido con la siguiente estructura:
{{
  "results": [
    {{
      "categoria_razonada": "string",
      "linea_producto": "string | null",
      "confianza": float
    }},
    ...
  ]
}}

Productos a analizar:
{''.join(products_text)}

Ejemplo de entrada:
- Código: 4259838, Nombre: TALADRO PERCUTOR, Modelo: TC-ID 1000, Categoría original: ★★★★★ PROFESSIONAL, Descripción: Potencia 1000W...
Salida esperada:
{{
  "results": [
    {{
      "categoria_razonada": "Taladros",
      "linea_producto": "PROFESSIONAL",
      "confianza": 0.95
    }}
  ]
}}
"""
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """Llama al LLM con caché."""
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Eres un experto en clasificación de productos industriales."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            result = response.choices[0].message.content
            self.cache[cache_key] = result
            return result
        except ImportError:
            print("⚠️ OpenAI no está instalado. Cambiando a modo simulación.")
            self.simulate = True
            return '{"results": []}'
        except Exception as e:
            print(f"Error en LLM: {e}. Cambiando a modo simulación.")
            self.simulate = True
            return '{"results": []}'
    
    def _parse_response(self, response: str, batch: List[Dict]) -> List[Dict[str, Any]]:
        """Parsea la respuesta del LLM."""
        try:
            data = json.loads(response)
            results = data.get('results', [])
            if len(results) < len(batch):
                results.extend([{} for _ in range(len(batch) - len(results))])
            
            enriched = []
            for r in results:
                enriched.append({
                    'categoria': r.get('categoria_razonada', None),
                    'linea_producto': r.get('linea_producto', None),
                    'confianza_ia': r.get('confianza', 0.0)
                })
            return enriched
        except json.JSONDecodeError:
            print("⚠️ Error al parsear respuesta del LLM. Usando simulación.")
            return self._simulate_enrichment(batch)
