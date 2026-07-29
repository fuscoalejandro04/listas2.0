"""
Módulo de Validación - Detecta errores y genera reporte de calidad.
"""
import pandas as pd
from typing import List, Dict, Any

class Validator:
    """Aplica reglas de calidad a los datos normalizados."""
    
    @staticmethod
    def validate_ean(ean: str) -> bool:
        """Valida checksum EAN-13 (algoritmo estándar)."""
        if not ean or len(ean) != 13 or not ean.isdigit():
            return False
        # Cálculo de checksum EAN-13
        total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(ean[:12]))
        checksum = (10 - (total % 10)) % 10
        return checksum == int(ean[12])
    
    @staticmethod
    def validate_price(price: float) -> bool:
        """Precio debe ser positivo."""
        return price > 0
    
    def validate_product(self, product: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Valida un producto y retorna una lista de issues.
        Cada issue: {'field': str, 'message': str, 'severity': 'error'|'warning'}
        """
        issues = []
        
        # Campos obligatorios
        if not product.get('codigo', ''):
            issues.append({
                'field': 'codigo',
                'message': 'Código de producto vacío',
                'severity': 'error'
            })
        
        if not product.get('nombre_articulo', ''):
            issues.append({
                'field': 'nombre_articulo',
                'message': 'Nombre del artículo vacío',
                'severity': 'warning'
            })
        
        # Precio
        price = product.get('precio_lista', 0)
        if price <= 0:
            issues.append({
                'field': 'precio_lista',
                'message': f'Precio inválido: {price}',
                'severity': 'error'
            })
        
        # EAN
        ean = product.get('ean', '')
        if ean and not self.validate_ean(ean):
            issues.append({
                'field': 'ean',
                'message': f'EAN inválido: {ean}',
                'severity': 'warning'
            })
        
        return issues
    
    def validate_all(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Valida todos los productos y genera reporte agregado."""
        all_issues = []
        error_count = 0
        warning_count = 0
        
        for idx, product in enumerate(products):
            issues = self.validate_product(product)
            for issue in issues:
                issue['row'] = idx + 1
                all_issues.append(issue)
                if issue['severity'] == 'error':
                    error_count += 1
                else:
                    warning_count += 1
        
        return {
            'total_products': len(products),
            'error_count': error_count,
            'warning_count': warning_count,
            'issues': all_issues,
            'quality_score': self.calculate_quality_score(products, len(all_issues))
        }
    
    @staticmethod
    def calculate_quality_score(products: List[Dict], total_issues: int) -> float:
        """Score de calidad basado en productos válidos vs total."""
        if not products:
            return 0.0
        # Penalización por issues
        penalty = min(total_issues / len(products), 1.0)
        return max(0.0, 1.0 - penalty)
