from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.chat_services import ChatService

router = APIRouter()
templates = Jinja2Templates(directory="templates")
chat_service = ChatService()

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@router.post("/chat")
async def chat_endpoint(message: str = Form(...)):
    # Si quieres imprimir para debug
    print(f"Mensaje recibido: {message}")
    response = await chat_service.get_chat_response(message)
    print(f"Respuesta: {response}")
    return response
