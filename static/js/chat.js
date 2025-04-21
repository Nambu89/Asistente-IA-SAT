document.addEventListener('DOMContentLoaded', function() {
    // ==================== ELEMENTOS DEL DOM ====================
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
    const toggleDarkModeBtn = document.getElementById('toggle-dark-mode');
    const themeToggleIcon = document.getElementById('theme-toggle-icon');
    const imageViewerModal = document.getElementById('image-viewer');
    const imageViewerImg = document.getElementById('image-viewer-img');
    const imageViewerClose = document.getElementById('image-viewer-close');
    const imageViewerDownload = document.getElementById('image-viewer-download');
    const imageViewerCaption = document.getElementById('image-viewer-caption');
    const API_BASE_URL = window.API_URL || 'https://svania.azurewebsites.net';

    // ==================== ESTADO DE LA APLICACIÓN ====================
    let attachments = [];
    let stream = null;
    let searchResults = [];
    let currentResult = -1;
    let isDarkMode = localStorage.getItem('darkMode') === 'true';
    let lastResponseHadImages = false;
    let availableImagesInLastResponse = [];
    let isProcessing = false;
    let typingTimer = null;
    let isUserTyping = false;

    // ==================== INICIALIZACIÓN ====================
    function init() {
        checkDarkMode();
        clearChat();
        setupEventListeners();
        initFeedbackSystem();
        initSearch();
        initImageViewer();
        checkBrowserSupport();
        // Asegurarse de que el modal esté oculto al inicio
        console.log("Inicializando: ocultando modal de confirmación");
        hideConfirmModal();
    }

    // Detector global de tecla Escape para cerrar modales y cámara
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            // Si la cámara está abierta
            if (!cameraPreview.classList.contains('hidden')) {
                console.log('Escape global - cerrando cámara');
                stopCamera();
            }
            
            // También cerrar otros modales si están abiertos
            if (!confirmModal.classList.contains('hidden')) {
                hideConfirmModal();
            }
            
            if (!imageViewerModal.classList.contains('hidden')) {
                closeImageViewer();
            }
        }
    });

    // Verificar características del navegador
    function checkBrowserSupport() {
        // Verificar soporte para Camera API
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            takePhotoBtn.classList.add('hidden');
            console.warn('Este navegador no soporta acceso a la cámara');
        }
        
        // Verificar soporte para almacenamiento local
        if (!window.localStorage) {
            console.warn('Este navegador no soporta localStorage');
        }
    }

    // Comprobar y aplicar el modo oscuro si está activado
    function checkDarkMode() {
        if (isDarkMode) {
            document.documentElement.classList.add('dark');
            if (themeToggleIcon) {
                themeToggleIcon.classList.remove('fa-moon');
                themeToggleIcon.classList.add('fa-sun');
            }
        } else {
            document.documentElement.classList.remove('dark');
            if (themeToggleIcon) {
                themeToggleIcon.classList.remove('fa-sun');
                themeToggleIcon.classList.add('fa-moon');
            }
        }
    }

    // ==================== EVENT LISTENERS ====================
    function setupEventListeners() {
        // Envío de mensajes
        sendButton.addEventListener('click', handleSubmit);
        
        // Tecla Enter para enviar
        userInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
            }
            if (e.key === 'Enter' && e.shiftKey) {
                // Permitir salto de línea con Shift+Enter
                const start = this.selectionStart;
                const end = this.selectionEnd;
                const value = this.value;
                this.value = value.substring(0, start) + '\n' + value.substring(end);
                this.selectionStart = this.selectionEnd = start + 1;
                
                // Ajustar altura
                autoResizeTextarea(this);
                e.preventDefault();
            }
        });

        // Detección de escritura del usuario
        userInput.addEventListener('input', function() {
            isUserTyping = true;
            clearTimeout(typingTimer);
            
            // 500ms después de que el usuario deje de escribir
            typingTimer = setTimeout(function() {
                isUserTyping = false;
            }, 500);
            
            // Ajuste automático de altura
            autoResizeTextarea(this);
        });

        // Gestión del chat
        clearChatBtn.addEventListener('click', showConfirmModal);
        cancelClearBtn.addEventListener('click', hideConfirmModal);
        confirmClearBtn.addEventListener('click', clearChat);
        
        // Gestión de archivos
        attachFileBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelect);

        // Eventos para la cámara
        if (takePhotoBtn) {
            takePhotoBtn.addEventListener('click', startCamera);
        }
        if (capturePhotoBtn) {
            capturePhotoBtn.addEventListener('click', capturePhoto);
        }
        if (retakePhotoBtn) {
            retakePhotoBtn.addEventListener('click', retakePhoto);
        }
        if (cancelPhotoBtn) {
            cancelPhotoBtn.addEventListener('click', stopCamera);
        }

        // Cambio de tema
        if (toggleDarkModeBtn) {
            toggleDarkModeBtn.addEventListener('click', toggleDarkMode);
        }

        // Visor de imágenes
        if (imageViewerClose) {
            imageViewerClose.addEventListener('click', closeImageViewer);
        }
        if (imageViewerModal) {
            imageViewerModal.addEventListener('click', function(e) {
                if (e.target === this) {
                    closeImageViewer();
                }
            });
        }
        if (imageViewerDownload) {
            imageViewerDownload.addEventListener('click', downloadCurrentImage);
        }

        // Interceptar clics en los mensajes para manejar solicitudes de imágenes
        chatMessages.addEventListener('click', handleChatMessagesClick);

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
    }

    // Función para redimensionar automáticamente el textarea
    function autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
        const maxHeight = window.innerWidth <= 640 ? 100 : 150;
        if (textarea.scrollHeight > maxHeight) {
            textarea.style.height = maxHeight + 'px';
            textarea.style.overflowY = 'auto';
        } else {
            textarea.style.overflowY = 'hidden';
        }
    }

    // Cambiar entre modo claro y oscuro
    function toggleDarkMode() {
        isDarkMode = !isDarkMode;
        localStorage.setItem('darkMode', isDarkMode);
        checkDarkMode();
    }

    // Gestionar clics en los mensajes (para manejo de imágenes y enlaces)
    function handleChatMessagesClick(e) {
        // Si se hace clic en un enlace para solicitar imágenes
        if (e.target.matches('.request-image-link') || e.target.closest('.request-image-link')) {
            e.preventDefault();
            const link = e.target.closest('.request-image-link');
            const reference = link.dataset.reference;
            requestImage(reference);
            return;
        }
        
        // Si se hace clic en una imagen para ampliarla
        if (e.target.matches('.manual-image') || e.target.closest('.manual-image')) {
            const img = e.target.closest('.manual-image');
            openImageViewer(img.src, img.alt);
            return;
        }
        
        // Delegación de eventos para botones de feedback
        if (e.target.closest('.feedback-button')) {
            handleFeedbackButtonClick(e);
        }
    }

    // ==================== SISTEMA DE IMÁGENES ====================
    function initImageViewer() {
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && !imageViewerModal.classList.contains('hidden')) {
                closeImageViewer();
            }
        });

        // Asegurar que el visor de imágenes esté inicialmente oculto
        if (imageViewerModal) {
            imageViewerModal.classList.add('hidden');
        }
    }

    function openImageViewer(src, caption) {
        // Mostrar indicador de carga
        imageViewerImg.src = '';
        imageViewerImg.classList.add('opacity-0');
        const loader = document.createElement('div');
        loader.className = 'loading-indicator absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2';
        imageViewerModal.appendChild(loader);
        
        // Actualizar la imagen y mostrar el visor
        imageViewerModal.classList.remove('hidden');
        document.body.classList.add('overflow-hidden'); // Prevenir scroll del body

        // Cargar la imagen
        const img = new Image();
        img.onload = function() {
            imageViewerImg.src = src;
            imageViewerImg.classList.remove('opacity-0');
            if (loader) {
                loader.remove();
            }
        };
        img.onerror = function() {
            if (loader) {
                loader.remove();
            }
            imageViewerImg.src = '/static/images/image-error.svg';
            imageViewerImg.classList.remove('opacity-0');
        };
        img.src = src;

        // Actualizar el pie de foto si existe
        if (imageViewerCaption) {
            imageViewerCaption.textContent = caption || 'Imagen del manual';
        }

        // Actualizar el enlace de descarga
        if (imageViewerDownload) {
            imageViewerDownload.setAttribute('data-src', src);
        }
    }

    function closeImageViewer() {
        imageViewerModal.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
    }

    function downloadCurrentImage() {
        const src = this.getAttribute('data-src');
        if (!src) return;

        // Crear un enlace temporal para descargar
        const a = document.createElement('a');
        a.href = src;
        a.download = 'imagen-manual-' + Date.now() + '.jpg';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    async function requestImage(reference) {
        try {
            // Mostrar indicador de carga en el mensaje
            const loadingIndicator = document.createElement('div');
            loadingIndicator.className = 'relative flex justify-center my-4';
            loadingIndicator.innerHTML = '<div class="loading-indicator"></div>';
            chatMessages.appendChild(loadingIndicator);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // Solicitar la imagen al servidor
            const response = await fetch(`${API_BASE_URL}/request-image`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `reference=${encodeURIComponent(reference)}`
            });
            
            // Eliminar indicador de carga
            loadingIndicator.remove();
            
            if (!response.ok) {
                throw new Error('Error al solicitar la imagen');
            }
            
            const data = await response.json();
            
            if (data.error) {
                addMessage(`Lo siento, no he podido encontrar la imagen para ${reference}.`, 'bot');
                return;
            }
            
            if (data.image_urls && data.image_urls.length > 0) {
                // Crear un mensaje con las imágenes
                const messageDiv = document.createElement('div');
                messageDiv.className = 'bot-message p-4 message-appear';
                
                let content = `<p>Aquí está la imagen para ${reference}:</p>
                               <div class="image-container grid grid-cols-1 md:grid-cols-2 gap-4 my-3">`;
                
                data.image_urls.forEach(url => {
                    content += `
                    <div class="image-wrapper">
                        <img src="${url}" alt="${reference}" class="manual-image max-w-full rounded-lg cursor-pointer hover:opacity-90 transition-opacity" loading="lazy">
                        <div class="mt-1 text-sm text-center text-gray-600 dark:text-gray-300">${data.reference}</div>
                    </div>`;
                });
                
                content += '</div>';
                
                messageDiv.innerHTML = content;
                chatMessages.appendChild(messageDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
                
                // Añadir evento para ampliar las imágenes
                messageDiv.querySelectorAll('.manual-image').forEach(img => {
                    img.addEventListener('click', function() {
                        openImageViewer(this.src, this.alt);
                    });
                });
            } else {
                addMessage(`Lo siento, no he podido encontrar la imagen para ${reference}.`, 'bot');
            }
        } catch (error) {
            console.error('Error al solicitar imagen:', error);
            addMessage('Ha ocurrido un error al buscar la imagen solicitada.', 'bot');
        }
    }

    // ==================== SISTEMA DE FEEDBACK ====================
    function initFeedbackSystem() {
        // Ya implementada en el código original
        chatMessages.addEventListener('click', function(e) {
            handleFeedbackButtonClick(e);
        });
    }
    
    function handleFeedbackButtonClick(e) {
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
                    button.classList.add('text-gray-600', 'dark:text-gray-400');
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
                thumbsDown.classList.add('text-gray-600', 'dark:text-gray-400');
                thumbsDown.disabled = true;
            }, 1500);
        }
    }
    
    async function submitFeedback(messageId, rating, comment) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/feedback`, {
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

    // ==================== SISTEMA DE BÚSQUEDA ====================
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
    
    function clearSearch() {
        // Eliminar resaltados anteriores
        const highlighted = chatMessages.querySelectorAll('.search-highlight');
        highlighted.forEach(el => {
            el.classList.remove('search-highlight', 'bg-yellow-200', 'dark:bg-yellow-800');
        });
        
        searchResults = [];
        currentResult = -1;
        searchStats.classList.add('hidden');
        searchPrev.disabled = true;
        searchNext.disabled = true;
    }
    
    function highlightResult(index) {
        // Eliminar resaltados anteriores
        const highlighted = chatMessages.querySelectorAll('.search-highlight');
        highlighted.forEach(el => {
            el.classList.remove('search-highlight', 'bg-yellow-200', 'dark:bg-yellow-800');
        });
        
        // Resaltar nuevo resultado
        if (index >= 0 && index < searchResults.length) {
            const result = searchResults[index];
            result.element.classList.add('search-highlight', 'bg-yellow-200', 'dark:bg-yellow-800');
            
            // Desplazarse a la vista
            result.element.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }
    }

    // ==================== GESTIÓN DE LA CÁMARA ====================
    async function startCamera() {
        try {
            // Verificar si el navegador soporta la API
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                alert('Tu navegador no soporta acceso a la cámara');
                return;
            }
            
            // Verificar si ya hay una sesión de cámara activa
            if (stream) {
                stopCamera();
            }
            
            // Solicitar acceso a la cámara trasera si está disponible
            stream = await navigator.mediaDevices.getUserMedia({
                video: { 
                    facingMode: 'environment',
                    width: { ideal: 1920 },
                    height: { ideal: 1080 }
                },
                audio: false
            });
            
            // Configurar vista previa
            cameraView.srcObject = stream;
            cameraPreview.classList.remove('hidden');
            capturePhotoBtn.classList.remove('hidden');
            retakePhotoBtn.classList.add('hidden');
            document.body.classList.add('camera-active');
            
            // Añadir botón de emergencia para cerrar
            const emergencyBtn = document.createElement('button');
            emergencyBtn.id = 'emergency-close-camera';
            emergencyBtn.innerHTML = '<i class="fas fa-times"></i>';
            emergencyBtn.addEventListener('click', function() {
                console.log('Botón de emergencia apretado');
                stopCamera();
            });
            cameraPreview.appendChild(emergencyBtn);
            
            // Evento para cuando la transmisión esté lista
            cameraView.onloadedmetadata = function() {
                cameraView.play();
            };
        } catch (err) {
            console.error('Error al acceder a la cámara:', err);
            
            // Mensaje de error más detallado para el usuario
            if (err.name === 'NotAllowedError') {
                alert('No se ha permitido el acceso a la cámara. Por favor, acepta los permisos para utilizar esta función.');
            } else if (err.name === 'NotFoundError') {
                alert('No se ha encontrado ninguna cámara en tu dispositivo.');
            } else {
                alert('Error al acceder a la cámara: ' + err.message);
            }
        }
    }
    
    function stopCamera() {
        console.log("Intento de parar la cámara");
        
        // Detener todas las pistas de video
        if (stream) {
            const tracks = stream.getTracks();
            console.log(`Parando ${tracks.length} pistas de video`);
            
            tracks.forEach(track => {
                console.log(`Parando pista: ${track.kind}`);
                track.stop();
            });
            stream = null;
        } else {
            console.log("No hay stream activo para detener");
        }
        
        // Eliminar botón de emergencia si existe
        const emergencyBtn = document.getElementById('emergency-close-camera');
        if (emergencyBtn) {
            emergencyBtn.remove();
        }
        
        // Ocultar elementos de la cámara
        if (cameraPreview) {
            cameraPreview.classList.add('hidden');
        }
        
        if (photoCanvas) {
            photoCanvas.classList.add('hidden');
        }
        
        // Eliminar clase que bloquea el scroll
        document.body.classList.remove('camera-active');
        
        // Limpiar fuente de video
        if (cameraView) {
            cameraView.srcObject = null;
        }
        
        console.log("Cámara cerrada completamente");
    }

    async function capturePhoto() {
        // Verificar que la cámara está activa
        if (!stream || !cameraView.videoWidth) {
            alert('La cámara no está lista. Por favor, intentalo de nuevo.');
            return;
        }
        
        try {
            // Obtener contexto del canvas y configurar dimensiones
            const context = photoCanvas.getContext('2d');
            photoCanvas.width = cameraView.videoWidth;
            photoCanvas.height = cameraView.videoHeight;
            
            // Dibujar el frame actual en el canvas
            context.drawImage(cameraView, 0, 0, photoCanvas.width, photoCanvas.height);
            
            // Convertir canvas a blob
            photoCanvas.toBlob(async (blob) => {
                // Crear archivo a partir del blob
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
                        autoResizeTextarea(userInput);
                        
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
            }, 'image/jpeg', 0.85); // Calidad 85% para mejor balance tamaño/calidad
        } catch (error) {
            console.error('Error al capturar foto:', error);
            alert('Error al capturar la foto. Por favor, intentalo de nuevo.');
        }
    }

    function retakePhoto() {
        // Eliminar la última foto
        if (attachments.length > 0) {
            attachments.pop();
            const previews = attachmentsPreview.getElementsByClassName('attachment-preview');
            if (previews.length > 0) {
                previews[previews.length - 1].remove();
            }
            
            // Ocultar previsualizaciones si no quedan adjuntos
            if (attachments.length === 0) {
                attachmentsPreview.classList.add('hidden');
            }
        }
        
        // Restablecer la vista de la cámara
        capturePhotoBtn.classList.remove('hidden');
        retakePhotoBtn.classList.add('hidden');
    }

    // ==================== GESTIÓN DE ARCHIVOS ====================
    function handleFileSelect(e) {
        const files = Array.from(e.target.files);
        
        if (files.length === 0) return;
        
        let fileErrors = [];
        files.forEach(file => {
            // Validar tipo de archivo
            const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf', 'text/plain'];
            if (!validTypes.includes(file.type)) {
                fileErrors.push(`Tipo de archivo no soportado: ${file.name}`);
                return;
            }
            
            // Validar tamaño
            const maxSize = file.type.startsWith('image/') ? 10 * 1024 * 1024 : 5 * 1024 * 1024;
            if (file.size > maxSize) {
                fileErrors.push(`El archivo ${file.name} es demasiado grande (máximo ${maxSize/(1024*1024)}MB)`);
                return;
            }
            
            attachments.push(file);
            showAttachmentPreview(file);
        });
        
        // Mostrar errores si los hay
        if (fileErrors.length > 0) {
            alert('Se encontraron problemas con algunos archivos:\n' + fileErrors.join('\n'));
        }
        
        // Limpiar input para permitir seleccionar el mismo archivo
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
        
        // Si es una imagen, mostrar una miniatura
        if (file.type.startsWith('image/')) {
            const thumbnail = document.createElement('img');
            thumbnail.className = 'attachment-thumbnail';
            thumbnail.alt = file.name;
            
            // Crear URL para la miniatura
            const reader = new FileReader();
            reader.onload = function(e) {
                thumbnail.src = e.target.result;
            };
            reader.readAsDataURL(file);
            
            preview.appendChild(thumbnail);
        } else {
            // Para otros tipos de archivo, mostrar un icono
            const icon = document.createElement('div');
            icon.className = 'attachment-icon';
            
            if (file.type === 'application/pdf') {
                icon.innerHTML = '<i class="fas fa-file-pdf"></i>';
            } else if (file.type === 'text/plain') {
                icon.innerHTML = '<i class="fas fa-file-alt"></i>';
            } else {
                icon.innerHTML = '<i class="fas fa-file"></i>';
            }
            
            preview.appendChild(icon);
        }
        
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

    // ==================== GESTIÓN DEL CHAT ====================
    function clearChat() {
        chatMessages.innerHTML = '';
        hideConfirmModal();
        addMessage('¡Hola! Soy SvanIA, el Asistente Técnico de SVAN. ¿En qué puedo ayudarte hoy?', 'bot');
        
        // Limpiar adjuntos
        attachments = [];
        attachmentsPreview.innerHTML = '';
        attachmentsPreview.classList.add('hidden');
        
        // Limpiar estado
        lastResponseHadImages = false;
        availableImagesInLastResponse = [];
    }

    function showConfirmModal() {
        console.log("Mostrando modal de confirmación");
        confirmModal.classList.remove('hidden');
    }

    function hideConfirmModal() {
        console.log("Ocultando modal de confirmación");
        confirmModal.classList.add('hidden');
    }

    function addMessage(message, type) {
        if (type === 'user') {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'user-message p-4 message-appear';
            
            // Convertir saltos de línea a <br> para preservar formato
            const formattedMessage = message.replace(/\n/g, '<br>');
            messageDiv.innerHTML = formattedMessage;
            
            chatMessages.appendChild(messageDiv);
        } else if (type === 'bot') {
            // Verificar si hay referencias a imágenes en el mensaje
            const hasImageReferences = checkForImageReferences(message);
            
            // Usar plantilla para mensajes del bot
            const template = document.getElementById('bot-message-template');
            const messageDiv = template.content.cloneNode(true).firstElementChild;
            messageDiv.classList.add('message-appear');
            
            // Generar ID único para este mensaje
            const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            messageDiv.dataset.messageId = messageId;
            
            // Configurar el contenido del mensaje con marked.js
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false
            });
            
            // Procesar enlaces a imágenes si los hay
            if (hasImageReferences) {
                // Reemplazar referencias a figuras con enlaces clicables
                message = processImageReferences(message);
            }
            
            // Renderizar markdown a HTML
            messageDiv.querySelector('.message-content').innerHTML = marked.parse(message);
            
            // Configurar enlaces externos
            messageDiv.querySelectorAll('a:not(.request-image-link)').forEach(link => {
                if (link.href && link.href.startsWith('http')) {
                    link.setAttribute('target', '_blank');
                    link.setAttribute('rel', 'noopener noreferrer');
                }
            });
            
            // Configurar bloques de código con highlight.js si está disponible
            if (window.hljs) {
                messageDiv.querySelectorAll('pre code').forEach(block => {
                    hljs.highlightElement(block);
                });
            } else {
                // Estilo básico si no está highlight.js
                messageDiv.querySelectorAll('pre code').forEach(block => {
                    block.className = 'language-plaintext';
                });
            }

            messageDiv.querySelectorAll('pre').forEach(el => {
                // Añadir clases para modo oscuro
                el.classList.add('bg-gray-900', 'dark:bg-black', 'text-white', 'p-4', 'rounded-md', 'overflow-x-auto');
                
                // Añadir botón para copiar código
                const copyBtn = document.createElement('button');
                copyBtn.className = 'copy-code-btn absolute top-2 right-2 text-white bg-blue-600 hover:bg-blue-700 rounded p-1 text-xs opacity-70 hover:opacity-100';
                copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
                copyBtn.addEventListener('click', function() {
                    const code = this.parentElement.querySelector('code').innerText;
                    navigator.clipboard.writeText(code).then(() => {
                        // Cambiar icono temporalmente para indicar éxito
                        const originalHTML = this.innerHTML;
                        this.innerHTML = '<i class="fas fa-check"></i>';
                        setTimeout(() => {
                            this.innerHTML = originalHTML;
                        }, 1500);
                    });
                });
                
                // Hacer el elemento pre relativo para posicionar el botón
                el.style.position = 'relative';
                el.appendChild(copyBtn);
            });
            
            chatMessages.appendChild(messageDiv);
            
            // Disparar evento de respuesta recibida para posibles acciones
            document.dispatchEvent(new CustomEvent('botResponseReceived', {
                detail: { messageId: messageId, content: message }
            }));
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

    function checkForImageReferences(message) {
        // Patrones para detectar referencias a imágenes
        const imagePatterns = [
            /fig(?:ura)?\s*\d+/i,
            /diagrama\s*\d+/i,
            /esquema\s*\d+/i,
            /imagen\s*\d+/i,
            /figure\s*\d+/i
        ];
        
        return imagePatterns.some(pattern => pattern.test(message));
    }

    function processImageReferences(message) {
        // Patrones para detectar y reemplazar referencias a imágenes
        const patterns = [
            {
                regex: /(fig(?:ura)?\s*\.?\s*(\d+))/gi,
                replacement: '<a href="#" class="request-image-link text-blue-600 dark:text-blue-400 underline" data-reference="$1">$1</a>'
            },
            {
                regex: /(diagrama\s*\.?\s*(\d+))/gi,
                replacement: '<a href="#" class="request-image-link text-blue-600 dark:text-blue-400 underline" data-reference="$1">$1</a>'
            },
            {
                regex: /(esquema\s*\.?\s*(\d+))/gi,
                replacement: '<a href="#" class="request-image-link text-blue-600 dark:text-blue-400 underline" data-reference="$1">$1</a>'
            },
            {
                regex: /(imagen\s*\.?\s*(\d+))/gi,
                replacement: '<a href="#" class="request-image-link text-blue-600 dark:text-blue-400 underline" data-reference="$1">$1</a>'
            }
        ];
        
        // Aplicar cada patrón
        patterns.forEach(pattern => {
            message = message.replace(pattern.regex, pattern.replacement);
        });
        
        return message;
    }

    function showLoadingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'bot-message p-4 flex items-center';
        loadingDiv.id = 'loading-indicator';
        
        // Crear indicador de carga animado
        const loadingIcon = document.createElement('div');
        loadingIcon.className = 'loading-indicator mr-2';
        
        const loadingText = document.createElement('span');
        loadingText.className = 'text-gray-700 dark:text-gray-300';
        loadingText.textContent = 'Procesando consulta...';
        
        loadingDiv.appendChild(loadingIcon);
        loadingDiv.appendChild(loadingText);
        
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        // Añadir temporizador para actualizar texto si tarda demasiado
        setTimeout(() => {
            const indicator = document.getElementById('loading-indicator');
            if (indicator) {
                const textSpan = indicator.querySelector('span');
                if (textSpan) {
                    textSpan.textContent = 'Esto está llevando más tiempo de lo esperado...';
                }
            }
        }, 8000);
    }

    function hideLoadingIndicator() {
        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            // Animación de desvanecimiento
            loadingIndicator.classList.add('fade-out');
            setTimeout(() => {
                loadingIndicator.remove();
            }, 300);
        }
    }

    // Funciones de detección de inactividad
    function setupInactivityDetection() {
        let inactivityTimeout;
        const INACTIVITY_TIME = 20 * 60 * 1000; // 20 minutos
        
        function resetInactivityTimer() {
            clearTimeout(inactivityTimeout);
            inactivityTimeout = setTimeout(suggestHelp, INACTIVITY_TIME);
        }
        
        function suggestHelp() {
            // Solo sugerir ayuda si el usuario no está escribiendo actualmente
            if (!isUserTyping && !isProcessing) {
                addMessage("¿Necesitas ayuda adicional? Puedo asistirte con cualquier otra consulta sobre electrodomésticos del Grupo SVAN.", "bot");
            }
        }
        
        // Reiniciar el temporizador en interacciones del usuario
        document.addEventListener('click', resetInactivityTimer);
        document.addEventListener('keydown', resetInactivityTimer);
        
        // Iniciar el temporizador
        resetInactivityTimer();
    }

    // ==================== ENVÍO DE MENSAJES ====================
    async function handleSubmit() {
        const message = userInput.value.trim();
        if (!message && attachments.length === 0) return;
        
        // Evitar envíos duplicados
        if (isProcessing) return;
        isProcessing = true;

        try {
            if (message) {
                console.log("Valor del input antes del envío:", message);
                addMessage(message, 'user');
            } else if (attachments.length > 0) {
                console.log("Enviando adjuntos sin mensaje de texto");
                addMessage("Te envío una imagen para analizar", 'user');
            }
            
            console.log("Limpiando input...");
            userInput.value = '';
            userInput.style.height = 'auto';
            showLoadingIndicator();

            const formData = new FormData();
            if (message) formData.append('message', message);
            attachments.forEach(file => formData.append('attachments', file));

            const response = await fetch(`${API_BASE_URL}/fullchat`, {
                method: 'POST',
                body: formData,
                // Tiempo de espera ampliado para consultas complejas
                timeout: 60000 // 60 segundos
            });

            console.log("Respuesta del backend:", response.status);
            // Verificar si la solicitud fue realizada con éxito
            if (!response.ok) {
                throw new Error(`Error en la solicitud: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();
            console.log("Datos recibidos:", data);
            hideLoadingIndicator();

            if (data.error) {
                addMessage(`Error: ${data.error}`, 'error');
            } else {
                // Procesar y mostrar la respuesta
                addMessage(data.response, 'bot');
                
                // Guardar información sobre imágenes si las hay
                lastResponseHadImages = data.has_images || data.images_available || false;
                availableImagesInLastResponse = data.images || [];
                
                // Si hay imágenes disponibles pero no se mostraron, sugerir verlas
                if (data.images_available && !data.has_images) {
                    // La respuesta ya incluye información sobre imágenes disponibles
                    console.log("Hay imágenes disponibles para mostrar");
                }
                
                // Si se enviaron imágenes junto con la respuesta, mostrarlas
                if (data.has_images && data.images && data.images.length > 0) {
                    showResponseImages(data.images);
                }
            }

            // Limpiar adjuntos
            attachments = [];
            attachmentsPreview.innerHTML = '';
            attachmentsPreview.classList.add('hidden');
            
            // Asegurar que la cámara está desactivada
            stopCamera();
        } catch (error) {
            console.error('Error al enviar el mensaje:', error);
            hideLoadingIndicator();
            
            // Mensaje de error más amigable según el tipo de error
            if (error.name === 'AbortError' || error.message.includes('timeout')) {
                addMessage('La consulta ha tardado demasiado tiempo. Por favor, intentalo con una consulta más corta o específica.', 'error');
            } else if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
                addMessage('No se pudo conectar con el servidor. Por favor, comprueba tu conexión a internet.', 'error');
            } else {
                addMessage('Ha ocurrido un error al procesar tu consulta. Por favor, intentalo de nuevo en unos momentos.', 'error');
            }
        } finally {
            isProcessing = false;
        }
    }

    function showResponseImages(images) {
        // Crear un mensaje con las imágenes
        const messageDiv = document.createElement('div');
        messageDiv.className = 'bot-message p-4 message-appear';
        
        let content = `<p>Aquí están las imágenes relacionadas:</p>
                       <div class="image-container grid grid-cols-1 md:grid-cols-2 gap-4 my-3">`;
        
        images.forEach(image => {
            image.urls.forEach(url => {
                content += `
                <div class="image-wrapper">
                    <img src="${url}" alt="${image.description || image.reference}" class="manual-image max-w-full rounded-lg cursor-pointer hover:opacity-90 transition-opacity" loading="lazy">
                    <div class="mt-1 text-sm text-center text-gray-600 dark:text-gray-300">${image.reference}</div>
                </div>`;
            });
        });
        
        content += '</div>';
        
        messageDiv.innerHTML = content;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        // Añadir eventos para ampliar las imágenes
        messageDiv.querySelectorAll('.manual-image').forEach(img => {
            img.addEventListener('click', function() {
                openImageViewer(this.src, this.alt);
            });
        });
    }

    // Función para agregar detección de errores de red
    function setupErrorHandling() {
        window.addEventListener('online', () => {
            console.log('Conexión recuperada');
            addMessage('Conexión a internet recuperada.', 'bot');
        });
        
        window.addEventListener('offline', () => {
            console.log('Conexión perdida');
            addMessage('Se ha perdido la conexión a internet. Algunas funciones pueden no estar disponibles hasta que se restablezca.', 'error');
        });
    }

    // Función para cargar scripts de manera dinámica si son necesarios
    function loadDynamicScripts() {
        // Cargar highlight.js si no está disponible
        if (!window.hljs) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/default.min.css';
            document.head.appendChild(link);
            
            const script = document.createElement('script');
            script.src = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js';
            script.onload = function() {
                // Inicializar highlight.js y aplicarlo a los bloques de código existentes
                hljs.highlightAll();
            };
            document.head.appendChild(script);
        }
    }

    // ==================== INICIALIZACIÓN ====================
    // Cargar scripts dinámicos si son necesarios
    loadDynamicScripts();
    
    // Iniciar la aplicación
    init();
    
    // Configurar detección de inactividad
    setupInactivityDetection();
    
    // Configurar manejo de errores de red
    setupErrorHandling();
    
    // Optimizaciones para dispositivos móviles
    if ('serviceWorker' in navigator && window.innerWidth <= 768) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/js/sw.js').then(
                registration => console.log('ServiceWorker registrado con éxito'),
                error => console.log('Error al registrar ServiceWorker:', error)
            );
        });
    }
});