import re
from pathlib import Path
from typing import Optional, Dict
from app.core.settings import Settings
from app.utils.pdf_helpers import extract_text_from_pdf

class PDFService:
    def __init__(self):
        self.settings = Settings()
        self.pdf_dir = self.settings.PDF_DIR
        self.pdf_cache: Dict[str, str] = {}
        self._load_existing_pdfs()

    def _load_existing_pdfs(self):
        """Carga todos los PDFs existentes en el directorio Manuales"""
        self.pdf_dir.mkdir(exist_ok=True)
        for pdf_path in self.pdf_dir.glob("*.pdf"):
            if pdf_path.stem not in self.pdf_cache:
                self.pdf_cache[pdf_path.stem] = extract_text_from_pdf(pdf_path)

    async def get_manual_content(self, model_number: str) -> Optional[str]:
        """Busca el contenido del manual basado en el número de modelo"""
        # Busca archivo que coincida con el modelo
        matches = [k for k in self.pdf_cache.keys() if model_number.lower() in k.lower()]
        if matches:
            return self.pdf_cache[matches[0]]
        return None

    async def get_relevant_context(self, query: str, model_number: Optional[str] = None) -> Optional[str]:
        """Busca contenido relevante en los PDFs basado en la consulta y modelo"""
        error_pattern = re.compile(r'([Ee]rror|[Ff])\s*(\d+)')
        error_match = error_pattern.search(query)
        error_code = error_match.group(2) if error_match else None
        
        # Si tenemos modelo y código de error, buscar específicamente en ese manual
        if model_number and error_code:
            # Normalizar el modelo (quitar espacios y convertir a mayúsculas)
            model_number = model_number.strip().upper()
            
            # Buscar el manual específico
            for manual_name, content in self.pdf_cache.items():
                if model_number in manual_name.upper():
                    # Buscar específicamente la sección del error
                    error_section = self._extract_error_section(content, error_code)
                    if error_section:
                        return f"Información específica del manual {manual_name} para el error F{error_code}:\n{error_section}"
    
        return None

    def _extract_error_section(self, content: str, error_code: str) -> Optional[str]:  # Indentado al mismo nivel
            """Extrae secciones específicas relacionadas con el código de error"""
            paragraphs = content.split('\n\n')
            error_info = []
            
            error_patterns = [
                f"F{error_code}",
                f"f{error_code}",
                f"Error {error_code}",
                f"error {error_code}"
            ]
            
            for paragraph in paragraphs:
                if any(pattern in paragraph for pattern in error_patterns):
                    error_info.append(paragraph.strip())
            
            if error_info:
                return "\n\n".join(error_info)
            return None