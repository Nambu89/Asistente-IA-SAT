document.addEventListener('DOMContentLoaded', function() {
    // Elementos del DOM
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const clearChatBtn = document.getElementById('clear-chat');
    const confirmModal = document.getElementById('confirm-modal');
    const cancelClearBtn = document.getElementById('cancel-clear');
    const confirmClearBtn = document.getElementById('confirm-clear');
    const attachFileBtn = document.getElementById('attach-file');
    const fileInput = document.getElementById('file-input');
    const attachmentsPreview = document.getElementById('attachments-preview');
    const takePhotoBtn = document.getElementById('take-photo');
    const cameraPreview = document.getElementById('camera-preview');
    const cameraView = document.getElementById('camera-view');
    const capturePhotoBtn = document.getElementById('capture-photo');
    const retakePhotoBtn = document.getElementById('retake-photo');
    const cancelPhotoBtn = document.getElementById('cancel-photo');
    const photoCanvas = document.getElementById('photo-canvas');
    const searchButton = document.getElementById('search-button');
    const searchBar = document.getElementById('search-bar');
    const searchInput = document.getElementById('search-input');
    const searchPrev = document.getElementById('search-prev');
    const searchNext = document.getElementById('search-next');
    const searchClose = document.getElementById('search-close');
    const searchStats = document.getElementById('search-stats');
    const searchCurrent = document.getElementById('search-current');
    const searchTotal = document.getElementById('search-total');

    // Estado de la aplicación
    let attachments = [];
    let stream = null;
    let searchResults = [];
    let currentResult = -1;

    // Inicialización
    function init() {
        clearChat();
        setupEventListeners();
        initFeedbackSystem();
        initSearch();
    }

    // Configurar event listeners
    function setupEventListeners() {
        // Envío de mensajes
        sendButton.addEventListener('click', handleSubmit);
        
        // Tecla Enter para enviar
        userInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
            }
        });

        // Gestión del chat
        clearChatBtn.addEventListener('click', showConfirmModal);
        cancelClearBtn.addEventListener('click', hideConfirmModal);
        confirmClearBtn.addEventListener('click', clearChat);
        
        // Gestión de archivos
        attachFileBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelect);

        // Eventos para la cámara
        takePhotoBtn.addEventListener('click', startCamera);
        capturePhotoBtn.addEventListener('click', capturePhoto);
        retakePhotoBtn.addEventListener('click', retakePhoto);
        cancelPhotoBtn.addEventListener('click', stopCamera);

        // Manejo mejorado del teclado virtual
        userInput.addEventListener('focus', () => {
            if (window.innerWidth <= 640) {
                setTimeout(() => {
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }, 300);
            }
        });

        // Prevenir zoom en iOS
        userInput.addEventListener('focus', (e) => {
            if (window.innerWidth <= 640) {
                e.target.style.fontSize = '16px';
            }
        });

        userInput.addEventListener('blur', (e) => {
            if (window.innerWidth <= 640) {
                e.target.style.fontSize = '';
            }
        });

        // Ajuste automático de altura del textarea
        userInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            const maxHeight = window.innerWidth <= 640 ? 100 : 150;
            if (this.scrollHeight > maxHeight) {
                this.style.height = maxHeight + 'px';
                this.style.overflowY = 'auto';
            } else {
                this.style.overflowY = 'hidden';
            }
        });
    }

    // Sistema de feedback
    function initFeedbackSystem() {
        // Delegación de eventos para botones de feedback
        chatMessages.addEventListener('click', function(e) {
            // Comprobar si el clic fue en un botón de feedback
            if (e.target.closest('.feedback-button')) {
                const button = e.target.closest('.feedback-button');
                const messageDiv = button.closest('.bot-message');
                const messageId = messageDiv.dataset.messageId;
                const feedbackForm = messageDiv.querySelector('.feedback-form');
                const feedbackType = button.classList.contains('thumbs-up') ? 'positive' : 'negative';
                
                // Toggle formulario de feedback
                if (button.classList.contains('thumbs-down')) {
                    feedbackForm.classList.toggle('hidden');
                    // Si se muestra el formulario, enfoca el textarea
                    if (!feedbackForm.classList.contains('hidden')) {
                        feedbackForm.querySelector('.feedback-comment').focus();
                    }
                } else {
                    // Si es thumbs-up, enviar feedback positivo directamente
                    submitFeedback(messageId, 5, "");
                    // Visual feedback
                    button.classList.add('text-green-500');
                    setTimeout(() => {
                        button.classList.remove('text-green-500');
                        button.classList.add('text-gray-600');
                        button.disabled = true;
                    }, 1500);
                }
            }
            
            // Cancelar feedback
            if (e.target.closest('.feedback-cancel')) {
                const feedbackForm = e.target.closest('.feedback-form');
                feedbackForm.classList.add('hidden');
            }
            
            // Enviar feedback
            if (e.target.closest('.feedback-submit')) {
                const messageDiv = e.target.closest('.bot-message');
                const messageId = messageDiv.dataset.messageId;
                const commentText = messageDiv.querySelector('.feedback-comment').value;
                
                submitFeedback(messageId, 1, commentText);
                
                // Ocultar formulario y mostrar confirmación
                messageDiv.querySelector('.feedback-form').classList.add('hidden');
                const thumbsDown = messageDiv.querySelector('.thumbs-down');
                thumbsDown.classList.add('text-red-500');
                setTimeout(() => {
                    thumbsDown.classList.remove('text-red-500');
                    thumbsDown.classList.add('text-gray-600');
                    thumbsDown.disabled = true;
                }, 1500);
            }
        });
        
        // Función para enviar feedback al servidor
        async function submitFeedback(messageId, rating, comment) {
            try {
                const response = await fetch('/api/feedback', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message_id: messageId,
                        rating: rating,
                        comment: comment
                    })
                });
                
                if (!response.ok) {
                    console.error('Error al enviar feedback');
                }
            } catch (error) {
                console.error('Error al enviar feedback:', error);
            }
        }
    }

    // Sistema de búsqueda
    function initSearch() {
        // Mostrar/ocultar barra de búsqueda
        searchButton.addEventListener('click', () => {
            searchBar.classList.toggle('hidden');
            if (!searchBar.classList.contains('hidden')) {
                searchInput.focus();
            }
        });
        
        // Cerrar búsqueda
        searchClose.addEventListener('click', () => {
            searchBar.classList.add('hidden');
            clearSearch();
        });
        
        // Realizar búsqueda
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.trim().toLowerCase();
            if (query.length < 2) {
                clearSearch();
                return;
            }
            
            // Buscar en los mensajes
            searchResults = [];
            const allMessages = chatMessages.querySelectorAll('.user-message, .bot-message');
            
            allMessages.forEach((message, index) => {
                const text = message.textContent.toLowerCase();
                if (text.includes(query)) {
                    searchResults.push({
                        element: message,
                        index: index
                    });
                }
            });
            
            // Actualizar estadísticas
            if (searchResults.length > 0) {
                searchStats.classList.remove('hidden');
                searchTotal.textContent = searchResults.length;
                currentResult = 0;
                searchCurrent.textContent = currentResult + 1;
                
                // Habilitar botones de navegación
                searchPrev.disabled = false;
                searchNext.disabled = false;
                
                // Resaltar primer resultado
                highlightResult(currentResult);
            } else {
                searchStats.classList.remove('hidden');
                searchTotal.textContent = 0;
                searchCurrent.textContent = 0;
                searchPrev.disabled = true;
                searchNext.disabled = true;
            }
        });
        
        // Navegación de resultados
        searchPrev.addEventListener('click', () => {
            if (searchResults.length === 0) return;
            
            currentResult = (currentResult - 1 + searchResults.length) % searchResults.length;
            searchCurrent.textContent = currentResult + 1;
            highlightResult(currentResult);
        });
        
        searchNext.addEventListener('click', () => {
            if (searchResults.length === 0) return;
            
            currentResult = (currentResult + 1) % searchResults.length;
            searchCurrent.textContent = currentResult + 1;
            highlightResult(currentResult);
        });
        
        // Limpiar búsqueda
        function clearSearch() {
            // Eliminar resaltados anteriores
            const highlighted = chatMessages.querySelectorAll('.search-highlight');
            highlighted.forEach(el => {
                el.classList.remove('search-highlight', 'bg-yellow-200');
            });
            
            searchResults = [];
            currentResult = -1;
            searchStats.classList.add('hidden');
            searchPrev.disabled = true;
            searchNext.disabled = true;
        }
        
        // Resaltar resultado actual
        function highlightResult(index) {
            // Eliminar resaltados anteriores
            const highlighted = chatMessages.querySelectorAll('.search-highlight');
            highlighted.forEach(el => {
                el.classList.remove('search-highlight', 'bg-yellow-200');
            });
            
            // Resaltar nuevo resultado
            if (index >= 0 && index < searchResults.length) {
                const result = searchResults[index];
                result.element.classList.add('search-highlight', 'bg-yellow-200');
                
                // Desplazarse a la vista
                result.element.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        }
        
        // Búsqueda con Enter
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (searchResults.length > 0) {
                    currentResult = (currentResult + 1) % searchResults.length;
                    searchCurrent.textContent = currentResult + 1;
                    highlightResult(currentResult);
                }
            }
            
            // Cerrar búsqueda con Escape
            if (e.key === 'Escape') {
                searchBar.classList.add('hidden');
                clearSearch();
            }
        });
    }

    // Gestión del chat
    function clearChat() {
        chatMessages.innerHTML = '';
        hideConfirmModal();
        addMessage('¡Hola! Soy el Asistente Técnico de SVAN. ¿En qué puedo ayudarte hoy?', 'bot');
    }

    function showConfirmModal() {
        confirmModal.classList.remove('hidden');
    }

    function hideConfirmModal() {
        confirmModal.classList.add('hidden');
    }

    // Gestión de archivos
    function handleFileSelect(e) {
        const files = Array.from(e.target.files);
        files.forEach(file => {
            // Aumentar límite para imágenes a 10MB
            const maxSize = file.type.startsWith('image/') ? 10 * 1024 * 1024 : 5 * 1024 * 1024;
            if (file.size > maxSize) {
                alert(`El archivo es demasiado grande. Máximo ${maxSize / (1024 * 1024)}MB.`);
                return;
            }
            attachments.push(file);
            showAttachmentPreview(file);
        });
        e.target.value = '';
    }

    function showAttachmentPreview(file) {
        const preview = document.createElement('div');
        preview.className = 'attachment-preview';
        
        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';
        
        const fileName = document.createElement('div');
        fileName.className = 'file-name';
        fileName.textContent = file.name;
        
        const fileSize = document.createElement('div');
        fileSize.className = 'file-size';
        fileSize.textContent = formatFileSize(file.size);
        
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-attachment';
        removeBtn.innerHTML = '<i class="fas fa-times"></i>';
        removeBtn.onclick = () => {
            attachments = attachments.filter(f => f !== file);
            preview.remove();
            if (attachments.length === 0) {
                attachmentsPreview.classList.add('hidden');
            }
        };
        
        fileInfo.appendChild(fileName);
        fileInfo.appendChild(fileSize);
        preview.appendChild(fileInfo);
        preview.appendChild(removeBtn);
        
        attachmentsPreview.appendChild(preview);
        attachmentsPreview.classList.remove('hidden');
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Gestión de mensajes
    function addMessage(message, type) {
        if (type === 'user') {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'user-message p-4 message-appear';
            messageDiv.textContent = message;
            chatMessages.appendChild(messageDiv);
        } else if (type === 'bot') {
            // Usar plantilla para mensajes del bot
            const template = document.getElementById('bot-message-template');
            const messageDiv = template.content.cloneNode(true).firstElementChild;
            messageDiv.classList.add('message-appear');
            
            // Generar ID único para este mensaje
            const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            messageDiv.dataset.messageId = messageId;
            
            // Configurar el contenido del mensaje
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false
            });
            
            messageDiv.querySelector('.message-content').innerHTML = marked.parse(message);
            
            // Configurar enlaces
            messageDiv.querySelectorAll('a').forEach(link => {
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener noreferrer');
            });
            
            // Configurar bloques de código
            messageDiv.querySelectorAll('pre code').forEach(block => {
                block.className = 'language-plaintext';
            });

            messageDiv.querySelectorAll('pre').forEach(el => {
                el.classList.add('bg-gray-900', 'text-white', 'p-4', 'rounded-md', 'overflow-x-auto');
            });
            
            chatMessages.appendChild(messageDiv);
            
            // Disparar evento de respuesta recibida para posibles acciones
            document.dispatchEvent(new CustomEvent('botResponseReceived'));
        } else if (type === 'error') {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'error-message p-4 message-appear';
            messageDiv.textContent = message;
            chatMessages.appendChild(messageDiv);
        }
        
        // Scroll suave en móviles
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }

    function showLoadingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'bot-message p-4';
        loadingDiv.id = 'loading-indicator';
        loadingDiv.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Procesando...';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function hideLoadingIndicator() {
        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.remove();
        }
    }

    // Funciones de la cámara
    async function startCamera() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { 
                    facingMode: 'environment',
                    width: { ideal: 1920 },
                    height: { ideal: 1080 }
                },
                audio: false
            });
            cameraView.srcObject = stream;
            cameraPreview.classList.remove('hidden');
            capturePhotoBtn.classList.remove('hidden');
            retakePhotoBtn.classList.add('hidden');
            document.body.classList.add('camera-active');
        } catch (err) {
            console.error('Error al acceder a la cámara:', err);
            alert('No se pudo acceder a la cámara. Por favor, asegúrate de dar los permisos necesarios.');
        }
    }

    function stopCamera() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
        cameraPreview.classList.add('hidden');
        photoCanvas.classList.add('hidden');
        document.body.classList.remove('camera-active');
    }

    async function capturePhoto() {
        const context = photoCanvas.getContext('2d');
        photoCanvas.width = cameraView.videoWidth;
        photoCanvas.height = cameraView.videoHeight;
        context.drawImage(cameraView, 0, 0, photoCanvas.width, photoCanvas.height);
        
        // Convertir a archivo
        photoCanvas.toBlob(async (blob) => {
            const file = new File([blob], `foto_${Date.now()}.jpg`, { type: 'image/jpeg' });
            
            // Añadir al array de adjuntos
            attachments.push(file);
            showAttachmentPreview(file);
            
            // Mostrar/ocultar botones
            capturePhotoBtn.classList.add('hidden');
            retakePhotoBtn.classList.remove('hidden');
            
            // Intentar detectar códigos de error en la imagen
            try {
                // Mostrar indicador de procesamiento
                const loadingMsg = document.createElement('div');
                loadingMsg.className = 'text-sm text-white bg-black bg-opacity-50 p-2 rounded';
                loadingMsg.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Analizando imagen...';
                loadingMsg.id = 'ocr-loading';
                document.querySelector('.camera-controls').appendChild(loadingMsg);
                
                // Procesar con Tesseract.js para encontrar texto
                const result = await Tesseract.recognize(
                    blob,
                    'spa', // español
                    { 
                        logger: m => console.log(m),
                        errorLimit: 100 // más tolerante con errores
                    }
                );
                
                // Buscar patrones de códigos de error comunes (E01, E02, F01, etc.)
                const text = result.data.text;
                const errorCodes = text.match(/[EF][0-9]{2,3}/g) || [];
                
                // Si se encontraron códigos de error
                if (errorCodes.length > 0) {
                    // Remover indicador de carga
                    document.getElementById('ocr-loading').remove();
                    
                    // Mostrar códigos encontrados
                    const foundMsg = document.createElement('div');
                    foundMsg.className = 'text-sm text-white bg-green-800 bg-opacity-70 p-2 rounded';
                    foundMsg.innerHTML = `<i class="fas fa-check mr-2"></i> Detectados códigos: ${errorCodes.join(', ')}`;
                    document.querySelector('.camera-controls').appendChild(foundMsg);
                    
                    // Prepopular el input con una consulta sobre el código
                    userInput.value = `¿Qué significa el código de error ${errorCodes[0]}?`;
                    
                    // Desaparecer el mensaje después de 3 segundos
                    setTimeout(() => {
                        foundMsg.remove();
                        stopCamera(); // Cerrar cámara automáticamente
                    }, 3000);
                } else {
                    // Si no se encontraron códigos
                    document.getElementById('ocr-loading').remove();
                    
                    const notFoundMsg = document.createElement('div');
                    notFoundMsg.className = 'text-sm text-white bg-gray-800 bg-opacity-70 p-2 rounded';
                    notFoundMsg.innerHTML = `<i class="fas fa-info-circle mr-2"></i> No se detectaron códigos de error`;
                    document.querySelector('.camera-controls').appendChild(notFoundMsg);
                    
                    // Desaparecer el mensaje después de 3 segundos
                    setTimeout(() => {
                        notFoundMsg.remove();
                    }, 3000);
                }
            } catch (error) {
                console.error('Error al analizar imagen:', error);
                // Remover indicador de carga si existe
                const loadingEl = document.getElementById('ocr-loading');
                if (loadingEl) loadingEl.remove();
            }
        }, 'image/jpeg', 0.8);
    }

    function retakePhoto() {
        // Eliminar la última foto
        if (attachments.length > 0) {
            attachments.pop();
            const previews = attachmentsPreview.getElementsByClassName('attachment-preview');
            if (previews.length > 0) {
                previews[previews.length - 1].remove();
            }
        }
        
        // Restablecer la vista de la cámara
        capturePhotoBtn.classList.remove('hidden');
        retakePhotoBtn.classList.add('hidden');
    }

    // Envío de mensajes
    async function handleSubmit() {
        const message = userInput.value.trim();
        if (!message && attachments.length === 0) return;

        if (message) {
            addMessage(message, 'user');
        }
        userInput.value = '';
        userInput.style.height = 'auto';
        showLoadingIndicator();

        try {
            const formData = new FormData();
            if (message) formData.append('message', message);
            attachments.forEach(file => formData.append('attachments', file));

            const response = await fetch('/fullchat', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            hideLoadingIndicator();

            if (data.error) {
                addMessage(`Error: ${data.error}`, 'error');
            } else {
                addMessage(data.response, 'bot');
            }

            // Limpiar adjuntos y cámara
            attachments = [];
            attachmentsPreview.innerHTML = '';
            attachmentsPreview.classList.add('hidden');
            stopCamera();
        } catch (error) {
            hideLoadingIndicator();
            addMessage('Lo siento, ha ocurrido un error. Por favor, intenta de nuevo.', 'error');
        }
    }

    // Iniciar la aplicación
    init();
});