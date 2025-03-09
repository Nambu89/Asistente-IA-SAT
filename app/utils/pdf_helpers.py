import PyPDF2
from pathlib import Path
from typing import Optional

def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extrae el texto de un archivo PDF.
    
    Args:
        pdf_path (Path): Ruta al archivo PDF
        
    Returns:
        str: Texto extraído del PDF
    """
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        print(f"Error al procesar el PDF {pdf_path}: {e}")
        return ""