declare const vis: any;

export class GraphRenderer {
    private network: any = null;
    private container: HTMLElement;

    constructor(containerId: string) {
        const el = document.getElementById(containerId);
        if (!el) throw new Error(`Container ${containerId} not found`);
        this.container = el;
    }

    public render(data: any) {
        if (!data.nodes || data.nodes.length === 0) {
            this.container.innerHTML = '<div class="empty-jobs">Nenhum conhecimento estruturado neste namespace.</div>';
            return;
        }

        this.container.innerHTML = '';
        if (this.network) {
            this.network.destroy();
        }

        const visObj = (window as any).vis;
        if (!visObj) {
            console.error("vis.js library not loaded.");
            this.showError();
            return;
        }

        this.network = new visObj.Network(this.container, data, {
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
    }

    public showLoading() {
        this.container.innerHTML = '<div class="empty-jobs">Carregando rede neural...</div>';
    }

    public showError() {
        this.container.innerHTML = '<div class="job-error">Erro ao carregar grafo de conhecimento.</div>';
    }
}
