"""
Módulo de Importadores - Adaptadores para leer datos desde diferentes fuentes.
Soporte inicial: Excel (.xlsx, .xls) y CSV.
"""
import pandas as pd
from typing import Union
from pathlib import Path

class Importer:
    """Clase base para importadores (por si queremos extender en el futuro)."""
    @staticmethod
    def read(file_path: Union[str, Path]) -> pd.DataFrame:
        """Lee un archivo y devuelve un DataFrame. Detecta extensión automáticamente."""
        path = Path(file_path)
        if path.suffix in ['.xlsx', '.xls']:
            return pd.read_excel(path, engine='openpyxl' if path.suffix == '.xlsx' else 'xlrd')
        elif path.suffix == '.csv':
            # Intenta detectar separador automáticamente
            return pd.read_csv(path, encoding='utf-8', sep=None, engine='python')
        else:
            raise ValueError(f"Formato no soportado: {path.suffix}")

    @staticmethod
    def read_from_bytes(data: bytes, filename: str) -> pd.DataFrame:
        """Lee desde bytes (útil para archivos subidos por Streamlit)."""
        import io
        if filename.endswith('.xlsx'):
            return pd.read_excel(io.BytesIO(data), engine='openpyxl')
        elif filename.endswith('.xls'):
            return pd.read_excel(io.BytesIO(data), engine='xlrd')
        elif filename.endswith('.csv'):
            return pd.read_csv(io.BytesIO(data), encoding='utf-8', sep=None, engine='python')
        else:
            raise ValueError(f"Formato no soportado: {filename}")
