import { getEl } from './domUtils';

type TabCallbacks = {
    onLoadGraph: () => void;
    onLoadTelemetry: () => void;
    onLoadSpatial: () => void;
    onLoadExperiences: () => void;
};

export const setupTabs = (callbacks: TabCallbacks) => {
    const switchTab = (tabId: string) => {
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

        const targetTab = getEl(`${tabId}-tab`);
        if (targetTab) targetTab.classList.add('active');

        const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
        if (btn) btn.classList.add('active');

        if (tabId === 'knowledge') {
            callbacks.onLoadGraph();
        } else if (tabId === 'telemetry') {
            callbacks.onLoadTelemetry();
        } else if (tabId === 'spatial') {
            callbacks.onLoadSpatial();
        } else if (tabId === 'experiences') {
            callbacks.onLoadExperiences();
        }
    };

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            if (tabId) switchTab(tabId);
        });
    });
};
