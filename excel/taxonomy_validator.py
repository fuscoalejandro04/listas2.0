from typing import List, Tuple
from backend.pipelines.detectors import ColumnMapper

class TaxonomyValidator:
    """
    Evalúa qué tan bien una fila candidata a encabezado se mapea a la taxonomía.
    """

    def __init__(self):
        self.mapper = ColumnMapper(confidence_threshold=0.0)

    def validate(self, headers: List[str]) -> Tuple[float, float]:
        """
        Retorna (score_mapeo, score_confianza_promedio)
        score_mapeo: proporción de columnas mapeadas (0..1)
        score_confianza_promedio: promedio de confianza de los mapeos (0..1)
        """
        if not headers:
            return 0.0, 0.0

        # Crear un DataFrame ficticio con esos encabezados para mapear
        import pandas as pd
        dummy = pd.DataFrame([headers], columns=headers)
        mapping = self.mapper.map_columns(dummy)

        mapped = 0
        total_conf = 0.0
        for col, (field, conf) in mapping.items():
            if field is not None:
                mapped += 1
                total_conf += conf

        total = len(mapping)
        if total == 0:
            return 0.0, 0.0

        score_mapeo = mapped / total
        score_conf = total_conf / max(1, mapped)
        return score_mapeo, score_conf
