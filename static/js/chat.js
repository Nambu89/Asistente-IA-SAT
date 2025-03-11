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

    // Estado de la aplicación
    let attachments = [];
    let stream = null;

    // Inicialización
    function init() {
        clearChat();
        setupEventListeners();
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

        // Nuevos eventos para la cámara
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
        const messageDiv = document.createElement('div');
        messageDiv.className = `p-4 ${type === 'user' ? 'user-message' : 'bot-message'}`;
        
        if (type === 'bot') {
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false
            });
            
            messageDiv.innerHTML = marked.parse(message);
            
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
                el.classList.add('bg-gray-100', 'p-4', 'rounded-md', 'overflow-x-auto');
            });
        } else {
            messageDiv.textContent = message;
        }
        
        chatMessages.appendChild(messageDiv);
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

    function capturePhoto() {
        const context = photoCanvas.getContext('2d');
        photoCanvas.width = cameraView.videoWidth;
        photoCanvas.height = cameraView.videoHeight;
        context.drawImage(cameraView, 0, 0, photoCanvas.width, photoCanvas.height);
        
        // Convertir a archivo
        photoCanvas.toBlob(blob => {
            const file = new File([blob], `foto_${Date.now()}.jpg`, { type: 'image/jpeg' });
            attachments.push(file);
            showAttachmentPreview(file);
            
            // Mostrar/ocultar botones
            capturePhotoBtn.classList.add('hidden');
            retakePhotoBtn.classList.remove('hidden');
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