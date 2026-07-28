import { AgentEvent } from '../types';

export type AgentSocketCallbacks = {
    onEvent: (event: AgentEvent) => void;
    onClose: () => void;
};

export class AgentSocket {
    private socket: WebSocket | null = null;
    private callbacks: AgentSocketCallbacks;
    private currentNamespace: string;

    constructor(callbacks: AgentSocketCallbacks, namespace: string) {
        this.callbacks = callbacks;
        this.currentNamespace = namespace;
    }

    public updateNamespace(namespace: string) {
        this.currentNamespace = namespace;
    }

    public connect(mission: string) {
        if (this.socket) {
            this.socket.close();
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/agent?namespace=${this.currentNamespace}`;
        
        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            this.socket?.send(JSON.stringify({ mission, namespace: this.currentNamespace }));
        };

        this.socket.onmessage = (e) => {
            try {
                const event: AgentEvent = JSON.parse(e.data);
                this.callbacks.onEvent(event);
            } catch (err) {
                console.error("Agent websocket message error", err);
            }
        };

        this.socket.onclose = () => {
            this.callbacks.onClose();
        };
    }
}
