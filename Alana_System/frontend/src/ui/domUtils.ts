export const getEl = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const htmlEscapes: Record<string, string> = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
};
export const escapeHtml = (value: unknown): string => String(value ?? '').replace(/[&<>"']/g, char => htmlEscapes[char]);

export const appendTerminalLine = (
    terminal: HTMLElement,
    type: string,
    content: string,
    prefix?: string
) => {
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    
    if (prefix) {
        const strong = document.createElement('strong');
        strong.textContent = prefix;
        line.appendChild(strong);
    }

    const safeContent = escapeHtml(content);
    const htmlContent = safeContent
        .replace(/### (.*)/g, '<h3 class="terminal-header">$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.*)/g, '<div class="terminal-list-item">• $1</div>')
        .replace(/\n/g, '<br>');

    const contentSpan = document.createElement('span');
    contentSpan.innerHTML = htmlContent;
    line.appendChild(contentSpan);

    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
};

export const showFeedbackResult = (
    messageBox: HTMLElement,
    messageText: HTMLElement,
    feedbackArea: HTMLElement,
    progressBar: HTMLElement,
    dropZone: HTMLElement,
    fileInput: HTMLInputElement,
    type: 'success' | 'error',
    text: string
) => {
    feedbackArea.classList.add('hidden');
    progressBar.classList.remove('loading');
    dropZone.style.pointerEvents = 'auto';
    dropZone.style.opacity = '1';

    messageBox.className = `message-box ${type}`;
    messageText.textContent = text;
    fileInput.value = '';
};
