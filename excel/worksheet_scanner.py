class WorksheetScanner:
    def __init__(self, worksheet, max_rows=100, max_cols=30):
        self.worksheet = worksheet
        self.max_rows = max_rows
        self.max_cols = max_cols

    def scan(self) -> List[RowInfo]:
        rows_info = []
        # Obtener el número real de columnas en la hoja (o usar max_cols)
        actual_max_col = min(self.max_cols, self.worksheet.max_column or 1)
        
        for row_idx in range(1, min(self.max_rows, self.worksheet.max_row) + 1):
            cells = []
            non_empty = text_count = number_count = date_count = empty_count = 0
            max_col = 0
            for col_idx in range(1, actual_max_col + 1):
                try:
                    cell = self.worksheet.cell(row=row_idx, column=col_idx)
                    value = cell.value
                except Exception:
                    # Si hay error al leer la celda, la tratamos como vacía
                    value = None
                
                is_merged = False
                cell_type = TypeClassifier.classify(value)
                cell_info = CellInfo(
                    row=row_idx - 1,
                    col=col_idx - 1,
                    value=str(value) if value is not None else None,
                    cell_type=cell_type,
                    is_merged=is_merged
                )
                cells.append(cell_info)
                if cell_type != CellType.EMPTY:
                    non_empty += 1
                    max_col = max(col_idx, max_col)
                    if cell_type == CellType.TEXT:
                        text_count += 1
                    elif cell_type == CellType.NUMBER:
                        number_count += 1
                    elif cell_type == CellType.DATE:
                        date_count += 1
                else:
                    empty_count += 1
            
            # Asegurar que max_col nunca sea None (si no hay celdas, es 0)
            if max_col is None:
                max_col = 0
                
            row_info = RowInfo(
                index=row_idx - 1,
                cells=cells,
                non_empty_count=non_empty,
                text_count=text_count,
                number_count=number_count,
                date_count=date_count,
                empty_count=empty_count,
                max_col=max_col
            )
            rows_info.append(row_info)
        return rows_info
