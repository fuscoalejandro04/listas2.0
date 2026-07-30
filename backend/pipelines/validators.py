"""
Módulo de Validación - Detecta errores, genera reporte de calidad y métricas de completitud.
"""
from typing import List, Dict, Any, Optional


class Validator:
    """Aplica reglas de calidad a los datos normalizados."""

    SUPPORTED_CURRENCIES = {'ARS', 'USD', 'EUR', 'U$S', '$'}

    def __init__(self, quality_threshold: float = 0.8, max_price: float = 10_000_000):
        """
        Inicializa el validador con umbrales configurables.
        
        Args:
            quality_threshold: Puntuación mínima (0-1) para considerar los datos válidos.
            max_price: Límite superior razonable para detectar outliers de precio.
        """
        self.quality_threshold = quality_threshold
        self.max_price = max_price

    @staticmethod
    def validate_ean(ean: str) -> bool:
        """Valida checksum EAN-13 (algoritmo estándar)."""
        if not ean or len(ean) != 13 or not ean.isdigit():
            return False
        # Cálculo de checksum EAN-13
        total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(ean[:12]))
        checksum = (10 - (total % 10)) % 10
        return checksum == int(ean[12])

    def validate_price(self, price: float) -> bool:
        """Precio debe ser positivo y no exceder el máximo configurado."""
        return 0 < price <= self.max_price

    def validate_currency(self, currency: str) -> bool:
        """Verifica que la moneda esté en la lista de soportadas."""
        return currency in self.SUPPORTED_CURRENCIES

    def validate_product(self, product: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Valida un producto y retorna una lista de issues.
        Cada issue: {'field': str, 'message': str, 'severity': 'error'|'warning'}
        """
        issues = []

        # --- Campos obligatorios ---
        if not product.get('codigo', ''):
            issues.append({
                'field': 'codigo',
                'message': 'Código de producto vacío',
                'severity': 'error'
            })

        # 🔥 CALIBRACIÓN: nombre_articulo solo es warning si también faltan modelo y descripcion
        nombre = product.get('nombre_articulo', '')
        modelo = product.get('modelo', '')
        descripcion = product.get('descripcion', '')

        if not nombre and not modelo and not descripcion:
            issues.append({
                'field': 'nombre_articulo',
                'message': 'Nombre del artículo, modelo y descripción vacíos',
                'severity': 'warning'
            })
        elif not nombre and (modelo or descripcion):
            # Si falta nombre pero hay modelo o descripcion, no es warning (se puede inferir)
            pass

        # --- Precio ---
        price = product.get('precio_lista')
        if price is None:
            issues.append({
                'field': 'precio_lista',
                'message': 'Precio ausente',
                'severity': 'error'
            })
        elif not self.validate_price(price):
            issues.append({
                'field': 'precio_lista',
                'message': f'Precio inválido: {price} (debe ser > 0 y <= {self.max_price})',
                'severity': 'error'
            })

        # --- EAN ---
        ean = product.get('ean', '')
        if ean and not self.validate_ean(ean):
            issues.append({
                'field': 'ean',
                'message': f'EAN inválido (checksum incorrecto): {ean}',
                'severity': 'warning'
            })

        # --- Moneda ---
        currency = product.get('moneda')
        if currency and not self.validate_currency(currency):
            issues.append({
                'field': 'moneda',
                'message': f'Moneda no soportada: {currency}',
                'severity': 'warning'
            })

        return issues

    def validate_all(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Valida todos los productos y genera reporte agregado."""
        if not products:
            return self._empty_report()

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

        quality_score = self._calculate_quality_score(
            total=len(products),
            errors=error_count,
            warnings=warning_count
        )

        return {
            'total_products': len(products),
            'error_count': error_count,
            'warning_count': warning_count,
            'issues': all_issues,
            'quality_score': quality_score,
            'is_valid': quality_score >= self.quality_threshold,
            'completeness': self._compute_completeness(products),
        }

    # ---------- Métodos auxiliares ----------
    def _calculate_quality_score(self, total: int, errors: int, warnings: int) -> float:
        """
        Calcula el score de calidad penalizando más los errores que los warnings.
        - Cada error resta 2 puntos porcentuales.
        - Cada warning resta 0.5 puntos porcentuales.
        """
        if total == 0:
            return 0.0
        penalty = (errors * 2.0 + warnings * 0.5) / total
        return max(0.0, min(1.0, 1.0 - penalty))

    def _compute_completeness(self, products: List[Dict]) -> Dict[str, float]:
        """
        Calcula el porcentaje de completitud por campo.
        Considera como vacíos: None, '', 'NaN', 'nan'.
        """
        if not products:
            return {}
        field_counts = {}
        for product in products:
            for field, value in product.items():
                if value not in (None, '', 'NaN', 'nan'):
                    field_counts[field] = field_counts.get(field, 0) + 1
        total = len(products)
        return {field: round(count / total, 4) for field, count in field_counts.items()}

    def _empty_report(self) -> Dict[str, Any]:
        """Reporte para lista vacía."""
        return {
            'total_products': 0,
            'error_count': 0,
            'warning_count': 0,
            'issues': [],
            'quality_score': 0.0,
            'is_valid': False,
            'completeness': {},
        }
