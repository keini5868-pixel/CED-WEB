"""Registry de módulos Capa 3."""

from app.modules.base_module import BaseModule
from app.modules.camera_module import CameraModule
from app.modules.image_gen_module import ImageGenModule
from app.modules.map_module import MapModule
from app.modules.memory_module import MemoryModule
from app.modules.pdf_module import PdfModule
from app.modules.prospection_module import ProspectionModule
from app.modules.publish_module import PublishModule
from app.modules.web_search_module import WebSearchModule

__all__ = [
    "BaseModule",
    "MapModule",
    "CameraModule",
    "PublishModule",
    "ImageGenModule",
    "PdfModule",
    "WebSearchModule",
    "ProspectionModule",
    "MemoryModule",
]
