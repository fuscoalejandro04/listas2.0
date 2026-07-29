from typing import Optional
from .models import HeaderDetectionResult

class ConfidenceCalculator:
    """
    Convierte los scores de los candidatos en un objeto HeaderDetectionResult
    con el mejor candidato y un nivel de confianza.
    """

    @staticmethod
    def calculate(
        candidates_scores: dict,  # {row_index: score}
        table_start: Optional[int],
        strategy: str = "bottom_up+schema"
    ) -> Optional[HeaderDetectionResult]:
        """
        Elige el candidato con mayor score y calcula la confianza.
        """
        if not candidates_scores:
            return None

        best_row = max(candidates_scores, key=candidates_scores.get)
        best_score = candidates_scores[best_row]

        # La confianza es una combinación del score y la diferencia con el segundo mejor.
        sorted_scores = sorted(candidates_scores.values(), reverse=True)
        if len(sorted_scores) >= 2:
            margin = sorted_scores[0] - sorted_scores[1]
        else:
            margin = 1.0

        # Confianza base: el score en sí, ajustado por el margen
        confidence = best_score * 0.7 + (margin * 0.3)
        confidence = max(0.0, min(1.0, confidence))

        # Si el mejor score es muy bajo, considerar que no hay detección confiable
        if best_score < 0.3:
            confidence = 0.0

        return HeaderDetectionResult(
            header_row=best_row,
            table_start=table_start,
            confidence=confidence,
            strategy=strategy,
            diagnostics={
                'scores': candidates_scores,
                'best_score': best_score,
                'margin': margin,
            }
        )
