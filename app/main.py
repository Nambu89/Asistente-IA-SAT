from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import sys
from pathlib import Path

# Configurar rutas
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Importar módulos de la aplicación
from app.core.settings import Settings
from app.api.routes import router as api_router

# Inicializar FastAPI
app = FastAPI(
    title="Svaniano - Asistente técnico",
    description="Asistente técnico especializado en productos del Grupo SVAN",
    version="1.0.0"
)

# Configuración
settings = Settings()

# Montar archivos estáticos y templates
app.mount("/static", StaticFiles(directory=str(root_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(root_dir / "templates"))

# Incluir rutas de la API
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)