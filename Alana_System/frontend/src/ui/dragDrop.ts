export const setupDragAndDrop = (
    dropZone: HTMLElement,
    fileInput: HTMLInputElement,
    onFileSelected: (file: File) => void
) => {
    const preventDefaults = (e: Event) => {
        e.preventDefault();
        e.stopPropagation();
    };

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    dropZone.addEventListener('dragenter', () => dropZone.classList.add('dragover'));
    dropZone.addEventListener('dragover', () => dropZone.classList.add('dragover'));
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    
    dropZone.addEventListener('drop', (e: DragEvent) => {
        dropZone.classList.remove('dragover');
        const files = e.dataTransfer?.files;
        if (files && files.length > 0) {
            onFileSelected(files[0]);
        }
    });

    dropZone.addEventListener('click', (event) => {
        if (event.target !== fileInput) fileInput.click();
    });
    dropZone.addEventListener('keydown', (event: KeyboardEvent) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            fileInput.click();
        }
    });
    
    fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files.length > 0) {
            onFileSelected(fileInput.files[0]);
        }
    });
};
