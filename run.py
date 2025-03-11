import os
import sys
from pathlib import Path

# Añadir el directorio raíz al PYTHONPATH
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))
os.environ["PYTHONPATH"] = str(root_dir)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=5000,
        reload=True,
        reload_dirs=[str(root_dir)]
    ) 