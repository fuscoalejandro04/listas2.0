from typing import List, Optional
from .models import RowInfo

class HeaderCandidateGenerator:
    """
    Genera una lista de filas candidatas a ser encabezado, basándose en el inicio de la tabla.
    """

    @staticmethod
    def generate_candidates(rows_info: List[RowInfo], table_start: Optional[int]) -> List[int]:
        """
        Retorna una lista de índices de fila (base 0) que son candidatos a encabezado.
        Prioriza la fila inmediatamente anterior al inicio de la tabla,
        pero también incluye alternativas cercanas.
        """
        if table_start is None:
            # Si no se detectó tabla, usar las primeras 10 filas
            return list(range(min(10, len(rows_info))))

        candidates = set()

        # Fila inmediatamente anterior al inicio de la tabla (si existe)
        if table_start > 0:
            candidates.add(table_start - 1)

        # También considerar la misma fila que table_start (por si la tabla empieza con encabezados)
        candidates.add(table_start)

        # Filas cercanas (hasta 3 filas arriba/abajo)
        for offset in range(-3, 4):
            row = table_start + offset
            if 0 <= row < len(rows_info):
                candidates.add(row)

        # Si no hay candidatos, agregar algunas filas por defecto
        if not candidates:
            candidates.update(range(min(5, len(rows_info))))

        return sorted(candidates)
