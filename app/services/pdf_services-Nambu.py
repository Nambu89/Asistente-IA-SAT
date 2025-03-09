import re
import PyPDF2
import os
from pathlib import Path
import logging
from typing import Optional, Dict, List
from app.core.settings import Settings
from app.utils.pdf_helpers import extract_text_from_pdf
import json
import numpy as np
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFService:
    def __init__(self):
        self.settings = Settings()
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.pdf_dir = self.settings.PDF_DIR
        self.embeddings_file = Path("data/embeddings.json")
        self.embeddings_file.parent.mkdir(exist_ok=True)
        self.embeddings_cache: Dict[str, dict] = self._load_embeddings()
        self.pdf_cache: Dict[str, str] = {}
        self._load_existing_pdfs()

    def _load_existing_pdfs(self):
        """Carga todos los PDFs existentes en el directorio Manuales"""
        self.pdf_dir.mkdir(exist_ok=True)
        for pdf_path in self.pdf_dir.glob("*.pdf"):
            if pdf_path.stem not in self.pdf_cache:
                self.pdf_cache[pdf_path.stem] = extract_text_from_pdf(pdf_path)

    def _load_embeddings(self) -> Dict[str, dict]:
        """Cargar embeddings desde archivo"""
        if self.embeddings_file.exists():
            try:
                with open(self.embeddings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando embeddings: {e}")
                return {}
        return {}
    
    def _save_embeddings(self):
        """Guardar embeddings en archivo"""
        try:
            with open(self.embeddings_file, 'w', encoding='utf-8') as f:
                json.dump(self.embeddings_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando embeddings: {e}")

    async def process_pdf(self, pdf_path: Path) -> Optional[str]:
        """Procesa un PDF y extrae su texto"""
        try:
            if not pdf_path.exists():
                logger.error(f"PDF no encontrado: {pdf_path}")
                return None

            # Si ya tenemos embeddings para este PDF y no ha cambiado, usar caché
            if str(pdf_path) in self.embeddings_cache:
                stats = pdf_path.stat()
                if stats.st_mtime == self.embeddings_cache[str(pdf_path)].get('last_modified'):
                    logger.info(f"Usando embeddings en caché para {pdf_path}")
                    return "PDF procesado desde caché"

            # Extraer texto del PDF
            text_chunks = []
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text = page.extract_text()
                    # Dividir en chunks de aproximadamente 1000 caracteres
                    chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
                    text_chunks.extend(chunks)

            # Generar embeddings para cada chunk
            embeddings = []
            for chunk in text_chunks:
                response = self.client.embeddings.create(
                    model="text-embedding-ada-002",
                    input=chunk
                )
                embeddings.append(response.data[0].embedding)

            # Guardar en caché
            self.embeddings_cache[str(pdf_path)] = {
                'chunks': text_chunks,
                'embeddings': embeddings,
                'last_modified': pdf_path.stat().st_mtime
            }
            self._save_embeddings()

            return "PDF procesado correctamente"

        except Exception as e:
            logger.error(f"Error procesando PDF {pdf_path}: {e}")
            return None

    async def get_relevant_context(self, query: str, model_number: Optional[str] = None) -> str:
        """Obtiene contexto relevante de los PDFs basado en la consulta"""
        try:
            # Obtener embedding de la consulta
            query_response = self.client.embeddings.create(
                model="text-embedding-ada-002",
                input=query
            )
            query_embedding = query_response.data[0].embedding

            relevant_chunks = []
            # Buscar en todos los PDFs o solo en los del modelo específico
            for pdf_path, data in self.embeddings_cache.items():
                if model_number and model_number not in Path(pdf_path).stem:
                    continue

                chunks = data['chunks']
                embeddings = data['embeddings']

                # Calcular similitud coseno
                for chunk, emb in zip(chunks, embeddings):
                    similarity = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb))
                    if similarity > 0.7:  # Umbral de similitud
                        relevant_chunks.append((chunk, similarity))

            # Ordenar por similitud y tomar los más relevantes
            relevant_chunks.sort(key=lambda x: x[1], reverse=True)
            top_chunks = relevant_chunks[:3]  # Tomar los 3 más relevantes

            if not top_chunks:
                return ""

            context = "\n".join(chunk for chunk, _ in top_chunks)
            return context

        except Exception as e:
            logger.error(f"Error obteniendo contexto: {e}")
            return ""

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