import pytest
from backend.domain.taxonomy import TAXONOMY, FieldDefinition

def test_taxonomy_loaded():
    assert len(TAXONOMY.fields) > 0

def test_field_aliases():
    codigo = TAXONOMY.get_field_by_name("codigo")
    assert codigo is not None
    assert "sku" in codigo.aliases

def test_product_model_validation():
    from backend.domain.product import Product
    # Datos válidos
    p = Product(
        codigo="PROD-001",
        nombre_articulo="Tornillo T1",
        precio_lista=150.50
    )
    assert p.precio_lista == 150.50
    
    # Datos inválidos (precio negativo)
    with pytest.raises(ValueError):
        Product(codigo="X", nombre_articulo="Y", precio_lista=-10)
