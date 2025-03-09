import openai
import logging
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import aiofiles
import asyncio
from fastapi import UploadFile
from app.core.settings import Settings
from app.services.pdf_services import PDFService
from app.models.chat_models import Message
from fastapi import HTTPException
import base64

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.settings = Settings()
        self.client = openai.OpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.pdf_service = PDFService()
        # Inicializar el contexto de conversación vacío
        self.conversation_context = {
            'current_model': None,
            'current_error': None,
            'history': [],
            'attachments': []
        }
        self.chat_log_path = Path("logs/chat_history.json")
        self.chat_log_path.parent.mkdir(exist_ok=True)
        # Comentamos temporalmente la carga del historial para empezar fresco
        # self._load_chat_history()

    def _load_chat_history(self):
        """Cargar historial de chat desde archivo"""
        try:
            if self.chat_log_path.exists():
                with open(self.chat_log_path, 'r', encoding='utf-8') as f:
                    self.conversation_context = json.load(f)
        except Exception as e:
            logger.error(f"Error al cargar historial: {e}")

    async def _save_chat_history(self):
        """Guardar historial de chat en archivo"""
        try:
            async with aiofiles.open(self.chat_log_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.conversation_context, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"Error al guardar historial: {e}")

    def _extract_model_number(self, text: str) -> Optional[str]:
        """
        Extrae el número de modelo del texto usando patrones específicos.
        Primera letra: Marca (S: SVAN, W: WONDER, A: ASPES, H: HYUNDAI)
        Siguientes letras: Tipo de producto
        """
        patterns = [
            # Patrones generales
            r'[SWAH][LCDHVMKTI]\d{4}[A-Z0-9]*',  # Patrones básicos (ej: SL8401)
            r'[SWAH][A-Z]{2,3}\d{4,5}[A-Z0-9]*', # Patrones con prefijos más largos (ej: SVVE02120S)
            
            # Patrones específicos
            r'[SA]CP[DEPT]\d{3,4}[A-Z0-9]*',      # Campanas (ej: SCPT600A1IX)
            r'[SWA]VN\d{4}[A-Z0-9]*',             # Vinotecas
            r'[SWAH]TV\d{4}[A-Z0-9]*',            # Televisores
            r'[SA]AAP\d{3,4}[A-Z0-9]*',           # Portátiles
            r'SSRS[A-Z0-9]+',                      # Solar
            r'DW\d{2}F\d{2}[A-Z0-9]*'             # Otros formatos específicos
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.upper())
            if match:
                return match.group(0)
        return None

    def _extract_error_code(self, text: str) -> Optional[str]:
        """
        Extrae códigos de error del texto.
        Patrones soportados:
        - F01, f01 (Errores tipo F)
        - E01, e01 (Errores tipo E)
        - Error 01, ERROR 01
        - C01, c01 (Errores tipo C)
        - H01, h01 (Errores tipo H)
        - d01, D01 (Errores tipo D)
        - Err 01, ERR 01
        - Error F01, error f01
        - Código 01, codigo 01
        """
        patterns = [
            # Errores tipo letra + número
            r'[FfEeCcHhDd](\d{2,3})',           # F01, E01, C01, H01, D01
            
            # Errores con palabra "Error"
            r'[Ee]rror\s*(\d{2,3})',            # Error 01
            r'[Ee]rror\s*[FfEeCcHhDd](\d{2,3})', # Error F01
            
            # Errores tipo ERR
            r'[Ee][Rr][Rr]\s*(\d{2,3})',        # ERR 01, Err 01
            r'[Ee][Rr][Rr]\s*[FfEeCcHhDd](\d{2,3})', # ERR F01
            
            # Códigos genéricos
            r'[Cc][óo]digo\s*(\d{2,3})',        # Código 01, Codigo 01
            r'[Cc][óo]d\.\s*(\d{2,3})',         # Cód. 01, Cod. 01
            
            # Errores específicos de display
            r'[Dd]isplay\s*[Ee]rror\s*(\d{2,3})', # Display Error 01
            r'[Dd]isp\.\s*[Ee]rr\.\s*(\d{2,3})'   # Disp. Err. 01
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).zfill(2)  # Asegura que el código tenga 2 dígitos
        return None

    def _get_brand_and_type(self, model: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Determina la marca y el tipo de electrodoméstico basado en el modelo.
        Retorna una tupla (marca, tipo).
        """
        if not model or len(model) < 2:
            return None, None

        brands = {
            'S': 'SVAN',
            'W': 'WONDER',
            'A': 'ASPES',
            'H': 'HYUNDAI'
        }

        product_types = {
            # Lavado y Secado
            'L': 'lavadora',
            'LS': 'lavadora secadora',
            'LCS': 'lavadora carga superior',
            
            # Frío
            'C': 'combi',
            'CV': 'congelador vertical',
            'CH': 'congelador horizontal',
            'CVH': 'congelador horeca',
            'F': 'frigorífico',
            'FP': 'frigorífico peltier',
            
            # Cocción
            'H': 'horno',
            'V': 'vitrocerámica',
            'M': 'microondas',
            'MW': 'microondas',
            'MWI': 'microondas integrado',
            'K': 'campana',
            'KG': 'cocina gas',
            'KV': 'cocina vitrocerámica',
            'KI': 'cocina integrada',
            'KMW': 'cocina mixta',
            
            # Campanas
            'CPD': 'campana decorativa',
            'CPE': 'campana extraíble',
            'CPP': 'campana piramidal',
            'CPT': 'campana tipo t',
            
            # Calefacción y Climatización
            'CE': 'calentador estanco',
            'VE': 'ventilación',
            'CA': 'calefactor',
            'CR': 'calefactor radiador',
            
            # Otros
            'VN': 'vinoteca',
            'J': 'lavavajillas',
            'LV': 'lavavajillas',
            'JI': 'lavavajillas integrado',
            'T': 'termo',
            'TV': 'televisor',
            'I': 'inducción'
        }

        brand = brands.get(model[0].upper())
        
        # Intentar encontrar el tipo de producto
        product_type = None
        if len(model) >= 3:
            # Primero intentar con 3 letras
            type_code = model[1:4].upper()
            if type_code in product_types:
                product_type = product_types[type_code]
            else:
                # Intentar con 2 letras
                type_code = model[1:3].upper()
                if type_code in product_types:
                    product_type = product_types[type_code]
                else:
                    # Intentar con 1 letra
                    type_code = model[1].upper()
                    if type_code in product_types:
                        product_type = product_types[type_code]
        
        return brand, product_type

    async def get_chat_response(self, message: str) -> str:
        try:
            # Extraer información del mensaje
            new_model = self._extract_model_number(message)
            error_code = self._extract_error_code(message)
            
            # Actualizar contexto
            if new_model:
                self.conversation_context['current_model'] = new_model
                brand, appliance_type = self._get_brand_and_type(new_model)
                if brand and appliance_type:
                    logger.info(f"Detectado: {brand} {appliance_type} - Modelo: {new_model}")

            if error_code:
                self.conversation_context['current_error'] = error_code
            
            # Obtener contexto relevante de los manuales
            relevant_context = await self.pdf_service.get_relevant_context(
                message, 
                self.conversation_context['current_model']
            )
            
            # Construir mensajes para el chat
            messages = [
                {"role": "system", "content": self.settings.SYSTEM_PROMPT},
                {"role": "system", "content": "IMPORTANTE: Tienes la capacidad de analizar imágenes. Cuando los usuarios pregunten si puedes procesar o analizar imágenes, debes responder que SÍ y explicar tus capacidades de análisis visual."}
            ]
            
            # Añadir información del modelo actual si existe
            if self.conversation_context['current_model']:
                brand, appliance_type = self._get_brand_and_type(self.conversation_context['current_model'])
                model_info = [f"Modelo actual: {self.conversation_context['current_model']}"]
                
                if brand and appliance_type:
                    model_info.append(f"Marca: {brand}")
                    model_info.append(f"Tipo: {appliance_type}")
                
                messages.append({
                    "role": "system", 
                    "content": "\n".join(model_info)
                })
            
            # Añadir información sobre imágenes adjuntas recientes y sus análisis
            recent_images = [
                attachment for attachment in self.conversation_context['attachments']
                if attachment['type'] == 'image' and attachment['processed'] and attachment.get('analysis')
            ]
            
            if recent_images:
                # Añadir el análisis más reciente primero
                latest_image = recent_images[-1]
                messages.append({
                    "role": "system",
                    "content": f"Análisis de la imagen más reciente:\n{latest_image['analysis']}"
                })
                
                # Añadir contexto de imágenes anteriores si existen
                for img in reversed(recent_images[:-1]):
                    messages.append({
                        "role": "system",
                        "content": f"Análisis previo de imagen:\n{img['analysis']}"
                    })
            
            # Añadir contexto relevante si existe
            if relevant_context:
                messages.append({
                    "role": "system",
                    "content": f"Información relevante del manual técnico:\n{relevant_context}"
                })
            
            # Añadir historial reciente (últimos 5 mensajes)
            messages.extend(self.conversation_context['history'][-5:])
            
            # Añadir el mensaje actual
            messages.append({"role": "user", "content": message})
            
            # Obtener respuesta de OpenAI
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            assistant_response = response.choices[0].message.content
            
            # Actualizar historial
            self.conversation_context['history'].append(
                {"role": "user", "content": message}
            )
            self.conversation_context['history'].append(
                {"role": "assistant", "content": assistant_response}
            )
            
            # Guardar historial actualizado
            await self._save_chat_history()
            
            return assistant_response
            
        except Exception as e:
            logger.error(f"Error al obtener respuesta del chat: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _extract_model_characteristics(self, model: str) -> Dict[str, str]:
        """
        Extrae características específicas del modelo basado en su nomenclatura.
        """
        characteristics = {}
        
        # Detectar capacidad en lavadoras
        if 'L' in model[1:3]:
            capacity_match = re.search(r'L(\d{2})', model)
            if capacity_match:
                characteristics['Capacidad'] = f"{int(capacity_match.group(1))/10}kg"

        # Detectar características No Frost
        if 'ENF' in model:
            characteristics['Sistema'] = 'No Frost'
            if 'ENFX' in model:
                characteristics['Versión'] = 'No Frost Premium'

        # Detectar tipo de motor en lavadoras
        if 'AIDV' in model:
            characteristics['Motor'] = 'Inverter Digital'
            if 'AIDVB' in model:
                characteristics['Motor'] = 'Inverter Digital Premium'

        # Detectar características digitales
        if 'DGX' in model or 'DGN' in model:
            characteristics['Panel'] = 'Digital'

        # Detectar tipo de display
        if 'DTD' in model or 'DDTD' in model:
            characteristics['Display'] = 'Digital Touch'

        # Detectar acabados específicos
        if 'PB' in model:
            characteristics['Acabado'] = 'Premium Black'
        elif 'IX' in model:
            characteristics['Acabado'] = 'Inox'

        # Detectar características de congeladores
        if 'EDC' in model:
            characteristics['Tipo'] = 'Horizontal'

        # Detectar características de TV
        if 'TV' in model:
            size_match = re.search(r'TV(\d{2})', model)
            if size_match:
                characteristics['Pantalla'] = f"{size_match.group(1)} pulgadas"

        return characteristics

    async def process_attachment(self, file_path: Path) -> None:
        """Procesa un archivo adjunto y actualiza el contexto de la conversación"""
        try:
            attachment_info = {
                'path': str(file_path),
                'timestamp': datetime.now().isoformat(),
                'processed': False,
                'type': None,
                'analysis': None
            }
            
            file_type = file_path.suffix.lower()
            
            if file_type in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                attachment_info['type'] = 'image'
                
                try:
                    logger.info(f"Intentando analizar imagen con gpt-4o-mini: {file_path}")
                    with open(file_path, "rb") as image_file:
                        image_data = image_file.read()
                        base64_image = base64.b64encode(image_data).decode('utf-8')
                        
                        response = self.client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Analiza esta imagen técnica y describe detalladamente:\n"
                                                   "1. Si es un diagrama o esquema, describe su tipo y propósito\n"
                                                   "2. Los componentes principales y sus conexiones\n"
                                                   "3. Cualquier anotación o etiqueta importante\n"
                                                   "4. Si hay códigos de error o información técnica relevante"
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/{file_type[1:]};base64,{base64_image}",
                                                "detail": "high"
                                            }
                                        }
                                    ]
                                }
                            ],
                            max_tokens=500
                        )
                        
                        attachment_info['analysis'] = response.choices[0].message.content
                        attachment_info['processed'] = True
                        logger.info("Análisis de imagen completado con éxito")
                        
                        # Añadir el análisis al contexto de la conversación inmediatamente
                        self.conversation_context['history'].append({
                            "role": "system",
                            "content": f"Análisis de la imagen adjunta ({file_path.name}):\n{attachment_info['analysis']}"
                        })
                        
                except Exception as e:
                    logger.error(f"Error procesando la imagen: {str(e)}")
                    attachment_info['analysis'] = f"Error al procesar la imagen: {str(e)}"
                    raise HTTPException(status_code=500, detail=f"Error al procesar la imagen: {str(e)}")
                
            elif file_type == '.pdf':
                attachment_info['type'] = 'pdf'
                context = await self.pdf_service.process_pdf(file_path)
                attachment_info['context'] = context
                attachment_info['processed'] = True
            
            self.conversation_context['attachments'].append(attachment_info)
            await self._save_chat_history()
            
        except Exception as e:
            logger.error(f"Error procesando archivo adjunto: {e}")
            raise

    async def clear_history(self) -> None:
        """Limpia el historial de conversación"""
        self.conversation_context = {
            'current_model': None,
            'current_error': None,
            'history': [],
            'attachments': []
        }
        await self._save_chat_history()