import { escapeHtml } from './domUtils';

export class GraphRenderer {
    private network: any = null;
    private container: HTMLElement;
    private renderVersion = 0;

    constructor(containerId: string) {
        const el = document.getElementById(containerId);
        if (!el) throw new Error(`Container ${containerId} not found`);
        this.container = el;
    }

    public async render(data: any) {
        const renderVersion = ++this.renderVersion;
        this.network?.destroy();
        this.network = null;
        if (!data.nodes || data.nodes.length === 0) {
            this.container.innerHTML = '<div class="empty-jobs">Nenhum conhecimento estruturado neste namespace.</div>';
            return;
        }

        this.container.innerHTML = '';
        const safeData = {
            ...data,
            nodes: data.nodes.map((node: any) => ({
                ...node,
                title: node.title ? escapeHtml(node.title) : undefined,
            })),
        };
        try {
            const { Network } = await import('vis-network/standalone');
            if (renderVersion !== this.renderVersion) return;
            this.network = new Network(this.container, safeData, {
                nodes: {
                    shape: 'dot',
                    size: 16,
                    font: { color: '#fff', size: 12 },
                    borderWidth: 2,
                    shadow: true
                },
                edges: {
                    color: { inherit: 'from' },
                    arrows: { to: { enabled: true, scaleFactor: 0.5 } },
                    font: { size: 10, color: '#a1a1aa', align: 'middle' }
                },
                physics: {
                    stabilization: true,
                    barnesHut: { gravitationalConstant: -2000 }
                }
            });
        } catch (error) {
            console.error('Falha ao carregar a visualização do grafo.', error);
            if (renderVersion === this.renderVersion) this.showError();
        }
    }

    public showLoading() {
        this.renderVersion++;
        this.network?.destroy();
        this.network = null;
        this.container.innerHTML = '<div class="empty-jobs">Carregando rede neural...</div>';
    }

    public showError() {
        this.renderVersion++;
        this.network?.destroy();
        this.network = null;
        this.container.innerHTML = '<div class="job-error">Erro ao carregar grafo de conhecimento.</div>';
    }
}
