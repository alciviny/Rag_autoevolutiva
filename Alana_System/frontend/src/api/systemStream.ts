import { IngestionJob, BackgroundTask } from '../types';

export type SystemStreamCallbacks = {
    onTasksUpdate: (tasks: BackgroundTask[]) => void;
    onArtifactsUpdate: (artifacts: any[]) => void;
    onJobsUpdate: (jobs: IngestionJob[]) => void;
    onLogsUpdate: (logs: string) => void;
    onError: (error: any) => void;
};

export class SystemStream {
    private eventSource: EventSource | null = null;
    private callbacks: SystemStreamCallbacks;

    constructor(callbacks: SystemStreamCallbacks) {
        this.callbacks = callbacks;
    }

    public connect(namespace: string) {
        if (this.eventSource) this.eventSource.close();
        
        this.eventSource = new EventSource(`/api/system/stream?namespace=${namespace}`);
        
        this.eventSource.addEventListener('tasks', (e: MessageEvent) => {
            try {
                const data = JSON.parse(e.data);
                if (data.tasks) this.callbacks.onTasksUpdate(data.tasks);
            } catch (err) { console.error('Parse error tasks', err); }
        });

        this.eventSource.addEventListener('artifacts', (e: MessageEvent) => {
            try {
                const data = JSON.parse(e.data);
                if (data.artifacts) this.callbacks.onArtifactsUpdate(data.artifacts);
            } catch (err) { console.error('Parse error artifacts', err); }
        });

        this.eventSource.addEventListener('jobs', (e: MessageEvent) => {
            try {
                const data = JSON.parse(e.data);
                if (data.jobs) this.callbacks.onJobsUpdate(data.jobs);
            } catch (err) { console.error('Parse error jobs', err); }
        });

        this.eventSource.addEventListener('logs', (e: MessageEvent) => {
            try {
                const data = JSON.parse(e.data);
                if (data.logs) this.callbacks.onLogsUpdate(data.logs);
            } catch (err) { console.error('Parse error logs', err); }
        });

        this.eventSource.addEventListener('error', (e: Event) => {
            this.callbacks.onError(e);
            console.error('System stream error', e);
        });
    }

    public disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}
