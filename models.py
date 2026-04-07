from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class ImageModel:
    id: Optional[int]
    file_path: str
    thumbnail_path: str
    width: int
    height: int
    date_added: datetime

@dataclass
class CollectionModel:
    id: Optional[int]
    name: str
    description: str

@dataclass
class TagModel:
    id: Optional[int]
    name: str
