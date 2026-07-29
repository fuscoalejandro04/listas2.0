from typing import List, Optional
from .models import RowInfo

class TableRegionDetector:
    """
    Detecta la región tabular en una hoja a partir de los datos escaneados.
    Busca una zona donde los tipos de datos sean homogéneos a lo largo de las columnas.
    """

    @staticmethod
    def detect_table_start(rows_info: List[RowInfo]) -> Optional[int]:
        """
        Retorna el índice de la primera fila que pertenece a la tabla de datos.
        Se basa en la consistencia de tipos de datos a lo largo de las columnas.
        """
        if not rows_info or len(rows_info) < 2:
            return None

        # Definir un umbral de homogeneidad: al menos un 70% de las columnas deben tener el mismo tipo
        # entre filas consecutivas (dentro de una ventana de 5 filas).
        window_size = 5
        best_score = -1
        best_start_row = None

        for start_idx in range(len(rows_info) - window_size + 1):
            window = rows_info[start_idx:start_idx + window_size]
            # Para cada columna, calcular la moda de tipos dentro de la ventana
            # y medir cuántas columnas son consistentes.
            col_types = {}
            for col in range(window[0].max_col):
                types = []
                for row in window:
                    if col < len(row.cells):
                        cell_type = row.cells[col].cell_type
                        if cell_type != CellType.EMPTY:
                            types.append(cell_type)
                if types:
                    # Moda (tipo más frecuente)
                    from collections import Counter
                    counter = Counter(types)
                    most_common = counter.most_common(1)[0][0]
                    # Proporción de celdas con ese tipo en la columna
                    ratio = counter[most_common] / len(types)
                    col_types[col] = (most_common, ratio)

            # Puntuación: promedio de ratios de consistencia
            if col_types:
                avg_ratio = sum(r for _, r in col_types.values()) / len(col_types)
                # Penalizar si hay muchas columnas vacías
                non_empty_cols = sum(1 for col, (_, r) in col_types.items() if r > 0.5)
                score = avg_ratio * (non_empty_cols / max(1, len(window[0].cells)))
                if score > best_score:
                    best_score = score
                    best_start_row = start_idx

        # Si la mejor puntuación es baja, considerar que no hay región clara
        if best_score < 0.3:
            return None

        return best_start_row
