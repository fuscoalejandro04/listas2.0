import yaml
from pydantic import BaseModel, Field
from typing import List, Optional
from backend.config import settings

class FieldDefinition(BaseModel):
    name: str
    data_type: str  # 'string', 'float', 'int', 'date', 'boolean'
    required: bool = False
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)

class Taxonomy(BaseModel):
    fields: List[FieldDefinition]
    
    def get_field_by_name(self, name: str) -> Optional[FieldDefinition]:
        for field in self.fields:
            if field.name == name:
                return field
        return None
    
    def get_all_aliases(self) -> List[str]:
        """Retorna todos los sinónimos conocidos para el detector."""
        aliases = []
        for field in self.fields:
            aliases.extend(field.aliases)
        return aliases

    @classmethod
    def load_from_yaml(cls) -> "Taxonomy":
        with open(settings.TAXONOMY_PATH, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
        return cls(**data)

# Cargamos la taxonomía al iniciar el módulo (Singleton en memoria)
TAXONOMY = Taxonomy.load_from_yaml()
