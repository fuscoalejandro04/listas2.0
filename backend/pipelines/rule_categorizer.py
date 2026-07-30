"""
Módulo de Categorización por Reglas - Enriquecimiento local y determinista.
Deduce línea de producto y categoría limpia a partir de valores de 'categoria'.
Las reglas se cargan desde un archivo JSON para facilitar su gestión.
"""
import json
import os
from typing import List, Dict, Any, Optional, Set
from pathlib import Path


class RuleCategorizer:
    """
    Categorizador local que opera sobre valores únicos de 'categoria'.
    Deduce:
    - categoria_razonada: categoría limpia (sin estrellas ni líneas)
    - linea_producto: línea de calidad (CLASSIC, PROFESSIONAL, etc.)
    """
    
    # Ruta al archivo de configuración de líneas
    _CONFIG_PATH = Path(__file__).resolve().parent.parent / "infrastructure" / "knowledge" / "lineas_producto.json"
    
    def __init__(self):
        """Carga la lista de líneas conocidas desde el archivo JSON."""
        self.lineas_conocidas = self._cargar_lineas()
        
    def _cargar_lineas(self) -> List[str]:
        """Carga la lista de líneas desde el archivo JSON."""
        try:
            if self._CONFIG_PATH.exists():
                with open(self._CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Archivo no existe, crear con valores por defecto
                return self._crear_archivo_por_defecto()
        except (json.JSONDecodeError, IOError):
            # Si hay error, usar lista por defecto y crear archivo limpio
            return self._crear_archivo_por_defecto()
    
    def _crear_archivo_por_defecto(self) -> List[str]:
        """Crea el archivo con líneas por defecto y lo retorna."""
        default = [
            "PROFESSIONAL",
            "EXPERT",
            "CLASSIC",
            "PREMIUM",
            "BASIC",
            "CAR EXPERT"
        ]
        self._guardar_lineas(default)
        return default
    
    def _guardar_lineas(self, lineas: List[str]) -> None:
        """Guarda la lista de líneas en el archivo JSON."""
        # Asegurar que el directorio existe
        self._CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self._CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(lineas, f, indent=2, ensure_ascii=False)
    
    def agregar_linea(self, nueva_linea: str) -> bool:
        """
        Agrega una nueva línea de producto al sistema.
        Retorna True si se agregó, False si ya existía.
        """
        linea_upper = nueva_linea.strip().upper()
        if not linea_upper:
            return False
        if linea_upper in self.lineas_conocidas:
            return False
        self.lineas_conocidas.append(linea_upper)
        self._guardar_lineas(self.lineas_conocidas)
        return True
    
    def eliminar_linea(self, linea: str) -> bool:
        """
        Elimina una línea de producto del sistema.
        Retorna True si se eliminó, False si no existía.
        """
        linea_upper = linea.strip().upper()
        if linea_upper not in self.lineas_conocidas:
            return False
        self.lineas_conocidas.remove(linea_upper)
        self._guardar_lineas(self.lineas_conocidas)
        return True
    
    def obtener_lineas(self) -> List[str]:
        """Retorna la lista actual de líneas conocidas."""
        return self.lineas_conocidas.copy()
    
    def enrich(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enriquece los productos operando sobre valores únicos de 'categoria'.
        Retorna la misma lista de productos pero con campos actualizados.
        """
        if not products:
            return products
        
        # 1. Extraer valores únicos de 'categoria'
        categoria_set: Set[str] = set()
        for p in products:
            cat = p.get('categoria')
            if cat and isinstance(cat, str) and cat.strip():
                categoria_set.add(cat.strip())
        
        if not categoria_set:
            return products
        
        # 2. Obtener el mapeo para los valores únicos
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
                    p['confianza_ia'] = enriched.get('confianza', 1.0)
        
        return products
    
    def _get_mapping_for_categories(self, categories: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Genera un diccionario de mapeo semántico para cada categoría única.
        """
        mapping = {}
        for cat in categories:
            cat_upper = cat.upper()
            linea = None
            categoria_razonada = cat
            
            # Detectar línea de producto
            for kw in self.lineas_conocidas:
                kw_upper = kw.upper()
                if kw_upper in cat_upper:
                    linea = kw  # Mantener el formato original de la línea
                    # Remover la palabra clave de la categoría
                    categoria_razonada = cat_upper.replace(kw_upper, '').strip()
                    break
            
            # Si queda vacía, usar la original
            if not categoria_razonada:
                categoria_razonada = cat
            
            mapping[cat] = {
                "categoria_razonada": categoria_razonada,
                "linea_producto": linea,
                "confianza": 1.0  # Determinista
            }
        return mapping
