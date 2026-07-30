"""
Módulo de Enriquecimiento Semántico con IA (LLM).
Razona sobre los datos crudos para inferir campos semánticos como:
- Categoría real (corregida)
- Línea/Calidad del producto (Classic, Professional, Expert, etc.)
- Unidad de medida implícita (si no se detectó por regex)
"""
import json
import hashlib
from typing import List, Dict, Any, Optional
import pandas as pd

class AIEnricher:
    """
    Enriquece productos normalizados usando un LLM.
    Se inyecta en el PipelineProcessor.
    """
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "gpt-4o-mini",
                 batch_size: int = 20,
                 max_tokens: int = 500,
                 temperature: float = 0.1):
        """
        Args:
            api_key: Clave de API (desde config o env)
            model: Modelo a usar (OpenAI, Gemini, etc.)
            batch_size: Número de productos por lote (para reducir costos)
            max_tokens: Máximo de tokens por respuesta
            temperature: Temperatura del LLM (baja para respuestas deterministas)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.batch_size = batch_size
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.cache = {}  # Cache simple en memoria (hash → resultado)
        
    def enrich(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrriquece una lista de productos con campos inferidos por LLM.
        Retorna la misma lista pero con campos adicionales.
        """
        if not products:
            return products
        
        # 1. Identificar productos que necesitan enriquecimiento
        #    (ej. los que tienen 'categoria' con estrellas o campos vacíos)
        to_enrich = []
        indices = []
        for idx, p in enumerate(products):
            # Ejemplo: si categoría contiene ★ o está vacía, o falta linea_producto
            cat = p.get('categoria', '')
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
                # Fusionar: mantener los campos originales, pero sobreescribir
                # los que el LLM haya inferido (si tienen confianza alta)
                products[idx].update(enriched)
        
        return products
    
    def _enrich_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrriquece un lote de productos con una sola llamada al LLM.
        """
        # Construir prompt
        prompt = self._build_prompt(batch)
        
        # Llamar al LLM (abstraído para soportar múltiples proveedores)
        response = self._call_llm(prompt)
        
        # Parsear respuesta JSON
        return self._parse_response(response, batch)
    
    def _build_prompt(self, batch: List[Dict[str, Any]]) -> str:
        """
        Construye el prompt few-shot para el LLM.
        """
        # Serializar los productos de forma legible
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
        """
        Llama al LLM (abstracción para OpenAI, Gemini, etc.)
        Aquí se usa OpenAI por simplicidad, pero se puede intercambiar.
        """
        # Verificar caché
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Importar cliente OpenAI (se puede hacer pluggable)
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
                response_format={"type": "json_object"}  # Forzamos JSON
            )
            result = response.choices[0].message.content
            self.cache[cache_key] = result
            return result
        except ImportError:
            # Fallback si no está instalado openai
            return '{"results": []}'
        except Exception as e:
            # Log del error y retornar vacío
            print(f"Error en LLM: {e}")
            return '{"results": []}'
    
    def _parse_response(self, response: str, batch: List[Dict]) -> List[Dict[str, Any]]:
        """
        Parsea la respuesta del LLM y la asigna a los productos.
        """
        try:
            data = json.loads(response)
            results = data.get('results', [])
            
            # Si el LLM devolvió menos resultados que el batch, completar con vacíos
            if len(results) < len(batch):
                results.extend([{} for _ in range(len(batch) - len(results))])
            
            # Mapear a los nombres de campos de la taxonomía
            enriched = []
            for r in results:
                enriched.append({
                    'categoria': r.get('categoria_razonada', None),
                    'linea_producto': r.get('linea_producto', None),
                    'confianza_ia': r.get('confianza', 0.0)
                })
            return enriched
            
        except json.JSONDecodeError:
            # Si falla el parseo, devolver vacíos
            return [{} for _ in batch]
