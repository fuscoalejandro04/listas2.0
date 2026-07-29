class TableRegionDetector:
    @staticmethod
    def detect_table_start(rows_info: List[RowInfo]) -> Optional[int]:
        if not rows_info or len(rows_info) < 2:
            return None
        
        # Filtrar filas con max_col = 0 (vacías) para evitar errores
        valid_rows = [r for r in rows_info if r.max_col > 0 and r.non_empty_count > 0]
        if len(valid_rows) < 2:
            return None
        
        window_size = 5
        best_score = -1
        best_start = None
        
        # Asegurar que no nos salimos del rango
        for start_idx in range(max(0, len(valid_rows) - window_size + 1)):
            window = valid_rows[start_idx:start_idx + window_size]
            if len(window) < 2:
                continue
                
            # Determinar el máximo de columnas en la ventana
            max_cols_in_window = max(r.max_col for r in window)
            if max_cols_in_window == 0:
                continue
                
            col_ratios = {}
            for col in range(max_cols_in_window):
                types = []
                for row in window:
                    if col < len(row.cells):
                        ct = row.cells[col].cell_type
                        if ct != CellType.EMPTY:
                            types.append(ct)
                if types:
                    counter = Counter(types)
                    most_common = counter.most_common(1)[0][0]
                    ratio = counter[most_common] / len(types)
                    col_ratios[col] = (most_common, ratio)
            
            if col_ratios:
                avg_ratio = sum(r for _, r in col_ratios.values()) / len(col_ratios)
                non_empty_cols = sum(1 for col, (_, r) in col_ratios.items() if r > 0.5)
                score = avg_ratio * (non_empty_cols / max(1, len(window[0].cells)))
                if score > best_score:
                    best_score = score
                    best_start = start_idx
        
        if best_score < 0.3:
            return None
        return best_start
