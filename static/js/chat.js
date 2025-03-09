document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chat-form');
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const manualUploadForm = document.getElementById('manual-upload-form');
    const uploadStatus = document.getElementById('upload-status');

    // Función para añadir mensajes al chat
    function addMessage(message, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `p-4 message-appear ${
            type === 'user' ? 'user-message' : 
            type === 'bot' ? 'bot-message' : 
            'error-message'
        }`;
        
        // Procesar el mensaje como markdown si es del bot
        if (type === 'bot') {
            // Convertir ** a negrita y otros elementos markdown
            const formattedMessage = message
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Negrita
                .replace(/\*(.*?)\*/g, '<em>$1</em>')             // Cursiva
                .replace(/###(.*?)\n/g, '<h3 class="text-lg font-bold my-2">$1</h3>') // Títulos
                .replace(/\n/g, '<br>');                          // Saltos de línea
            
            messageDiv.innerHTML = formattedMessage;
        } else {
            const textP = document.createElement('p');
            textP.textContent = message;
            messageDiv.appendChild(textP);
        }
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Función para mostrar el indicador de carga
    function showLoadingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'loading-indicator bot-message p-4';
        loadingDiv.id = 'loading-indicator';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Función para ocultar el indicador de carga
    function hideLoadingIndicator() {
        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.remove();
        }
    }

    // Manejar el envío de mensajes
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = userInput.value.trim();
        if (!message) return;

        // Añadir mensaje del usuario
        addMessage(message, 'user');
        userInput.value = '';

        // Mostrar indicador de carga
        showLoadingIndicator();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `message=${encodeURIComponent(message)}`
            });

            const data = await response.json();
            hideLoadingIndicator();

            if (data.error) {
                addMessage(`Error: ${data.error}`, 'error');
            } else {
                addMessage(data.response, 'bot');
            }
        } catch (error) {
            hideLoadingIndicator();
            addMessage('Lo siento, ha ocurrido un error. Por favor, intenta de nuevo.', 'error');
        }
    });

    // Manejar la subida de manuales
    manualUploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('manual-file');
        const file = fileInput.files[0];

        if (!file) {
            uploadStatus.textContent = 'Por favor, selecciona un archivo PDF';
            uploadStatus.className = 'mt-2 text-sm text-red-500';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        uploadStatus.textContent = 'Subiendo manual...';
        uploadStatus.className = 'mt-2 text-sm text-blue-500';

        try {
            const response = await fetch('/api/upload-manual', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.error) {
                uploadStatus.textContent = `Error: ${data.error}`;
                uploadStatus.className = 'mt-2 text-sm text-red-500';
            } else {
                uploadStatus.textContent = data.message;
                uploadStatus.className = 'mt-2 text-sm text-green-500';
                fileInput.value = '';  // Limpiar el input
            }
        } catch (error) {
            uploadStatus.textContent = 'Error al subir el archivo';
            uploadStatus.className = 'mt-2 text-sm text-red-500';
        }
    });

    // Habilitar envío con Enter
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });
});