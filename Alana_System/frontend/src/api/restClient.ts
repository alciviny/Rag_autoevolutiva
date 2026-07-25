export const fetchTelemetry = async (namespace: string) => {
    const res = await fetch(`/api/graph/hubs?namespace=${namespace}`);
    if (!res.ok) throw new Error('Failed to fetch telemetry');
    return res.json();
};

export const fetchSpatial = async (namespace: string) => {
    const res = await fetch(`/api/spatial/data?namespace=${namespace}`);
    if (!res.ok) throw new Error('Failed to fetch spatial data');
    return res.json();
};

export const fetchExperiences = async (namespace: string) => {
    const res = await fetch(`/api/experiences?namespace=${namespace}`);
    if (!res.ok) throw new Error('Failed to fetch experiences');
    return res.json();
};

export const fetchGraphData = async (namespace: string, file?: string) => {
    let url = `/api/graph/data?namespace=${namespace}`;
    if (file) url += `&file=${encodeURIComponent(file)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch graph data');
    return res.json();
};

export const fetchGraphFiles = async (namespace: string) => {
    const res = await fetch(`/api/graph/files?namespace=${namespace}`);
    if (!res.ok) throw new Error('Failed to fetch graph files');
    return res.json();
};

export const uploadIngestionFile = async (file: File, namespace: string, mode: string = "fast"): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`/api/ingestion/upload?namespace=${namespace}&mode=${mode}`, {
        method: 'POST',
        body: formData
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || err.message || 'Upload failed');
    }
    return res.json();
};

export const sendVoiceCommandApi = async (blob: Blob, namespace: string): Promise<any> => {
    const formData = new FormData();
    formData.append('audio', blob, 'command.webm');
    const res = await fetch(`/api/iot/voice?namespace=${namespace}`, {
        method: 'POST',
        body: formData
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || err.message || 'Voice command failed');
    }
    return res.json();
};
