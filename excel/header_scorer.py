from typing import List, Dict, Any
from .models import RowInfo, CellType
from .taxonomy_validator import TaxonomyValidator
from .style_analyzer import StyleAnalyzer

class HeaderScorer:
    """
    Calcula una puntuación para cada fila candidata a encabezado.
    Combina múltiples métricas en un score normalizado.
    """

    def __init__(self):
        self.taxonomy_validator = TaxonomyValidator()

    def score_candidate(
        self,
        row_info: RowInfo,
        style_info: Dict[str, Any],
        rows_info: List[RowInfo]
    ) -> float:
        """
        Calcula un score compuesto para una fila candidata.
        Mayor score = mejor candidato.
        """
        scores = {}

        # 1. Estabilidad de tipos (similitud con las filas de datos)
        if row_info.index + 1 < len(rows_info):
            next_row = rows_info[row_info.index + 1]
            # Comparar tipos de columna entre la candidata y la siguiente fila
            col_consistency = 0
            total_cols = min(row_info.max_col, next_row.max_col)
            for col in range(total_cols):
                if col < len(row_info.cells) and col < len(next_row.cells):
                    type1 = row_info.cells[col].cell_type
                    type2 = next_row.cells[col].cell_type
                    if type1 == type2 and type1 != CellType.EMPTY:
                        col_consistency += 1
            if total_cols > 0:
                scores['type_stability'] = col_consistency / total_cols
            else:
                scores['type_stability'] = 0.0
        else:
            scores['type_stability'] = 0.0

        # 2. Proporción de texto vs números (los encabezados suelen tener más texto)
        total_non_empty = row_info.non_empty_count
        if total_non_empty > 0:
            text_ratio = row_info.text_count / total_non_empty
            number_ratio = row_info.number_count / total_non_empty
            # Queremos alto texto, bajo números
            scores['text_density'] = text_ratio * 0.8 - number_ratio * 0.2
        else:
            scores['text_density'] = 0.0

        # 3. Evitar filas con muchos valores vacíos (títulos combinados)
        if row_info.max_col > 0:
            empty_ratio = row_info.empty_count / row_info.max_col
            scores['empty_penalty'] = 1.0 - empty_ratio
        else:
            scores['empty_penalty'] = 0.0

        # 4. Estilos visuales (negrita, color, borde)
        style_score = 0.0
        if style_info.get('bold_count', 0) > 0:
            style_score += 0.3
        if style_info.get('colored_count', 0) > 0:
            style_score += 0.3
        if style_info.get('has_bottom_border', False):
            style_score += 0.4
        scores['style'] = style_score

        # 5. Taxonomía (mapeo a la taxonomía)
        if row_info.max_col > 0:
            headers = [row_info.cells[col].value for col in range(row_info.max_col) if col < len(row_info.cells)]
            if headers:
                mapeo_score, conf_score = self.taxonomy_validator.validate(headers)
                scores['taxonomy'] = (mapeo_score * 0.7 + conf_score * 0.3)
            else:
                scores['taxonomy'] = 0.0
        else:
            scores['taxonomy'] = 0.0

        # Pesos para cada métrica (ajustables)
        weights = {
            'type_stability': 0.25,
            'text_density': 0.20,
            'empty_penalty': 0.15,
            'style': 0.15,
            'taxonomy': 0.25,
        }

        # Calcular score final (normalizado)
        final_score = 0.0
        for key, value in scores.items():
            # Clamp entre 0 y 1
            value = max(0.0, min(1.0, value))
            final_score += value * weights.get(key, 0.1)

        return final_score
