import { IngestionJob, AgentEvent } from './types';
import { SystemStream } from './api/systemStream';
import { AgentSocket } from './api/agentSocket';
import { 
    fetchTelemetry, 
    fetchSpatial, 
    fetchExperiences, 
    fetchGraphData, 
    fetchGraphFiles,
    uploadIngestionFile, 
    sendVoiceCommandApi 
} from './api/restClient';
import { getEl, appendTerminalLine, showFeedbackResult } from './ui/domUtils';
import { setupTabs } from './ui/tabs';
import { GraphRenderer } from './ui/graphRenderer';
import { setupDragAndDrop } from './ui/dragDrop';
import { AudioRecorder } from './media/audioRecorder';

document.addEventListener('DOMContentLoaded', () => {
    const dropZone = getEl('drop-zone');
    const fileInput = getEl<HTMLInputElement>('file-input');
    const feedbackArea = getEl('feedback-area');
    const progressBar = getEl('progress-bar');
    const statusText = getEl('status-text');
    const messageBox = getEl('message-box');
    const messageText = getEl('message-text');
    const jobsList = getEl('jobs-list');

    const runMissionBtn = getEl<HTMLButtonElement>('run-mission-btn');
    const missionInput = getEl<HTMLTextAreaElement>('mission-input');
    const agentDisplay = getEl('agent-display');
    const agentThought = getEl('agent-thought');
    const agentTerminal = getEl('agent-terminal');
    const approvalPanel = getEl('approval-panel');
    const approveBtn = getEl('approve-btn');
    const rejectBtn = getEl('reject-btn');
    const approvalText = getEl('approval-text');
    const voiceBtn = getEl('voice-btn');
    const systemTasksList = getEl('system-tasks-list');
    const namespaceSelect = getEl<HTMLSelectElement>('namespace-select');
    const graphFileSelect = getEl<HTMLSelectElement>('graph-file-select');
    const artifactGallery = getEl('artifact-gallery');
    const toggleLogBtn = getEl<HTMLButtonElement>('toggle-log-btn');
    const logText = getEl('log-text');

    // --- Monitor Toggle ---
    toggleLogBtn?.addEventListener('click', () => {
        if (logText.style.display === 'none') {
            logText.style.display = 'block';
            toggleLogBtn.textContent = 'Ocultar 🔽';
        } else {
            logText.style.display = 'none';
            toggleLogBtn.textContent = 'Mostrar 🔼';
        }
    });

    const toolIndicators: Record<string, HTMLElement | null> = {
        'research': getEl('tool-research'),
        'python_runner': getEl('tool-simulation'),
        'validate_theory': getEl('tool-simulation'),
        'navigate_graph': getEl('tool-graph'),
        'autonomous_analyst': getEl('tool-graph')
    };

    let currentNamespace = namespaceSelect.value;
    const graphRenderer = new GraphRenderer('knowledge-graph');

    namespaceSelect.addEventListener('change', () => {
        currentNamespace = namespaceSelect.value;
        agentSocket.updateNamespace(currentNamespace);
        systemStream.connect(currentNamespace);
        if (getEl('knowledge-tab').classList.contains('active')) {
            if (graphFileSelect) graphFileSelect.value = "";
            loadGraph();
        }
    });

    // --- Tabs ---
    setupTabs({
        onLoadGraph: loadGraph,
        onLoadTelemetry: loadTelemetry,
        onLoadSpatial: loadSpatial,
        onLoadExperiences: loadExperiences
    });

    // --- Graph & Data Loaders ---
    async function loadGraphFiles() {
        if (!graphFileSelect) return;
        try {
            const data = await fetchGraphFiles(currentNamespace);
            const currentVal = graphFileSelect.value;
            graphFileSelect.innerHTML = '<option value="">Todos os Documentos</option>';
            if (data.files) {
                data.files.forEach((f: string) => {
                    if (f && f !== 'INFERENCE_ENGINE' && f !== 'AGENT_DISCOVERY') {
                        const opt = document.createElement('option');
                        opt.value = f;
                        opt.textContent = f;
                        graphFileSelect.appendChild(opt);
                    }
                });
            }
            if (Array.from(graphFileSelect.options).some(o => o.value === currentVal)) {
                graphFileSelect.value = currentVal;
            }
        } catch(e) {
            console.error('Failed to load graph files', e);
        }
    }

    async function loadGraph() {
        graphRenderer.showLoading();
        try {
            await loadGraphFiles();
            const selectedFile = graphFileSelect?.value || '';
            const data = await fetchGraphData(currentNamespace, selectedFile);
            graphRenderer.render(data);
        } catch (e) {
            console.error(e);
            graphRenderer.showError();
        }
    }

    graphFileSelect?.addEventListener('change', () => {
        loadGraph();
    });

    async function loadTelemetry() {
        const container = getEl('telemetry-display');
        try {
            const data = await fetchTelemetry(currentNamespace);
            if (!data.hubs || data.hubs.length === 0) {
                container.innerHTML = '<div class="empty-jobs">Aguardando telemetria ativa...</div>';
                return;
            }
            container.innerHTML = data.hubs.map((hub: any) => `
                <div class="telemetry-card-mini">
                    <span class="telemetry-label">Conexões: ${hub.total}</span>
                    <span class="telemetry-value">${hub.entity}</span>
                    <span class="telemetry-unit">Ativo</span>
                </div>
            `).join('');
        } catch (e) { console.error(e); }
    }

    async function loadSpatial() {
        const container = getEl('spatial-map');
        try {
            const data = await fetchSpatial(currentNamespace);
            if (!data.entities || data.entities.length === 0) {
                container.innerHTML = '<div class="empty-jobs">Nenhuma entidade com localização rastreada.</div>';
                return;
            }
            container.innerHTML = data.entities.map((ent: any) => `
                <div class="spatial-node">
                    <span class="spatial-location">${ent.last_location}</span>
                    <span class="spatial-name">${ent.name}</span>
                    <span class="job-footer">Tipo: ${ent.type} | Visto: ${new Date(ent.last_seen).toLocaleTimeString()}</span>
                </div>
            `).join('');
        } catch (e) { console.error(e); }
    }

    async function loadExperiences() {
        const container = getEl('experience-timeline');
        try {
            const data = await fetchExperiences(currentNamespace);
            if (!data.experiences || data.experiences.length === 0) {
                container.innerHTML = '<div class="empty-jobs">Nenhuma experiência registrada nesta linha do tempo.</div>';
                return;
            }
            container.innerHTML = data.experiences.map((exp: any) => `
                <div class="timeline-item">
                    <div class="timeline-header">
                        <span class="timeline-mission">${exp.mission_name}</span>
                        <span class="timeline-date">${new Date(exp.timestamp).toLocaleDateString()}</span>
                    </div>
                    <p>${exp.task_description}</p>
                    <div class="timeline-strategy">
                        <strong>ESTRATÉGIA VENCEDORA:</strong><br>
                        ${exp.winning_strategy}
                    </div>
                </div>
            `).join('');
        } catch (e) { console.error(e); }
    }

    getEl('refresh-graph-btn')?.addEventListener('click', loadGraph);

    // --- Ingestion (Drag & Drop) ---
    setupDragAndDrop(dropZone, fileInput, async (file) => {
        messageBox.classList.add('hidden');
        feedbackArea.classList.remove('hidden');
        progressBar.classList.add('loading');
        statusText.textContent = `Ingestão em curso: ${file.name}...`;
        dropZone.style.pointerEvents = 'none';
        dropZone.style.opacity = '0.5';

        try {
            const modeSelect = getEl<HTMLSelectElement>('ingestion-mode');
            const mode = modeSelect ? modeSelect.value : 'fast';
            const data = await uploadIngestionFile(file, currentNamespace, mode);
            showFeedbackResult(messageBox, messageText, feedbackArea, progressBar, dropZone, fileInput, 'success', data.message || 'Processado com sucesso!');
        } catch (err: any) {
            showFeedbackResult(messageBox, messageText, feedbackArea, progressBar, dropZone, fileInput, 'error', err.message || 'Erro na comunicação com a IA.');
        }
    });

    const renderJobs = (jobs: IngestionJob[]) => {
        jobsList.innerHTML = ''; 
        if (jobs.length === 0) {
            jobsList.innerHTML = '<div class="empty-jobs">Nenhum processo ativo no momento.</div>';
            return;
        }

        jobs.forEach(job => {
            const progress = job.total_batches > 0 ? Math.round((job.completed_batches / job.total_batches) * 100) : 0;
            const statusClass = job.status.toLowerCase();
            const jobItem = document.createElement('div');
            jobItem.className = 'job-item';
            jobItem.innerHTML = `
                <div class="job-info">
                    <span class="job-filename">${job.filename}</span>
                    <span class="job-badge ${statusClass}">${job.status}</span>
                </div>
                <div class="job-progress-container">
                    <div class="job-progress-bar" style="width: ${progress}%"></div>
                </div>
                <div class="job-footer">
                    <span>${progress}% Concluído</span>
                    <span>${job.completed_batches}/${job.total_batches} Blocos</span>
                </div>
            `;
            jobsList.appendChild(jobItem);
        });
    };

    // --- Agent Socket ---
    const agentSocket = new AgentSocket({
        onEvent: (event: AgentEvent) => {
            const { type, data } = event;
            switch (type) {
                case 'thought':
                    const agentPrefix = data.agent ? `[${data.agent}]: ` : '';
                    agentThought.textContent = `${agentPrefix}${data.content || ''}`;
                    appendTerminalLine(agentTerminal, 'thought', data.content || '', agentPrefix);
                    break;
                case 'tool_start':
                    appendTerminalLine(agentTerminal, 'tool-start', `${data.name}...`, '[AÇÃO]: ');
                    if (data.name && toolIndicators[data.name]) {
                        toolIndicators[data.name]?.classList.add('active');
                    }
                    break;
                case 'tool_result':
                    Object.values(toolIndicators).forEach(t => t?.classList.remove('active'));
                    appendTerminalLine(agentTerminal, 'result', data.result || '');
                    break;
                case 'awaiting_approval':
                    approvalText.textContent = `Autorizar: ${data.command}?`;
                    approvalPanel.classList.remove('hidden');
                    break;
                case 'mission_complete':
                    showFeedbackResult(messageBox, messageText, feedbackArea, progressBar, dropZone, fileInput, 'success', 'Missão Completa');
                    break;
            }
        },
        onClose: () => {
            runMissionBtn.disabled = false;
            runMissionBtn.textContent = 'NOVA MISSÃO';
        }
    }, currentNamespace);

    const startAgentMission = (mission: string) => {
        agentDisplay.classList.remove('hidden');
        agentThought.textContent = 'Iniciando...';
        agentTerminal.innerHTML = '';
        appendTerminalLine(agentTerminal, 'system', 'Conectando...', '> ');

        runMissionBtn.disabled = true;
        agentSocket.connect(mission);
    };

    runMissionBtn.addEventListener('click', () => {
        const mission = missionInput.value.trim();
        if (!mission) return alert('Descreva a missão.');
        startAgentMission(mission);
    });

    approveBtn.addEventListener('click', () => {
        agentSocket.approve();
        approvalPanel.classList.add('hidden');
    });

    rejectBtn.addEventListener('click', () => {
        agentSocket.reject();
        approvalPanel.classList.add('hidden');
    });

    // --- Audio Recorder ---
    const audioRecorder = new AudioRecorder({
        onStart: () => {
            voiceBtn.classList.add('recording');
        },
        onStop: async (blob) => {
            voiceBtn.classList.remove('recording');
            appendTerminalLine(agentTerminal, 'system', 'Processando áudio...', '> ');
            try {
                const data = await sendVoiceCommandApi(blob, currentNamespace);
                if (data.intent === 'MISSION' && data.transcription) {
                    missionInput.value = data.transcription;
                    startAgentMission(data.transcription);
                } else {
                    appendTerminalLine(agentTerminal, 'result', data.answer || 'Não entendi o comando.');
                }
            } catch (err) {
                appendTerminalLine(agentTerminal, 'error', 'Erro ao processar voz.');
            }
        },
        onError: (err) => {
            alert('Erro ao acessar microfone. Verifique as permissões.');
            console.error(err);
        }
    });

    voiceBtn.addEventListener('click', () => {
        audioRecorder.toggleRecording();
    });

    // --- System Stream (SSE replacing setInterval) ---
    const systemStream = new SystemStream({
        onTasksUpdate: (tasks) => {
            systemTasksList.innerHTML = '';
            if (tasks.length === 0) {
                systemTasksList.innerHTML = '<div class="empty-jobs">Nenhuma operação de background em execução.</div>';
                return;
            }
            tasks.forEach(task => {
                const item = document.createElement('div');
                item.className = 'system-task-item';
                item.innerHTML = `
                    <div class="task-meta">
                        <h4>${task.name}</h4>
                        <span>ID: ${task.id.split('-')[0]} • Retries: ${task.retries}</span>
                    </div>
                    <div class="status-badge ${task.status}">${task.status}</div>
                `;
                systemTasksList.appendChild(item);
            });
        },
        onArtifactsUpdate: (artifacts) => {
            if (artifacts.length === 0) {
                artifactGallery.innerHTML = '<div class="empty-artifacts">Nenhum artefato gerado nesta sessão.</div>';
                return;
            }
            artifactGallery.innerHTML = '';
            artifacts.forEach(art => {
                const item = document.createElement('div');
                item.className = 'artifact-item';
                const isImage = /\.(jpg|jpeg|png|webp|gif)$/i.test(art.name);
                const icon = isImage ? '' : `<div class="file-icon">📄</div>`;
                item.innerHTML = `
                    ${isImage ? `<img src="${art.url}" class="artifact-preview" alt="${art.name}">` : icon}
                    <div class="artifact-info">
                        <a href="${art.url}" target="_blank">${art.name}</a>
                        <div>${(art.size / 1024).toFixed(1)} KB</div>
                    </div>
                `;
                artifactGallery.appendChild(item);
            });
        },
        onJobsUpdate: (jobs) => {
            renderJobs(jobs);
        },
        onLogsUpdate: (logs) => {
            const logTextEl = getEl('log-text');
            if (logTextEl) logTextEl.innerHTML = logs;
        },
        onError: (err) => {
            console.error('SSE Stream Error', err);
        }
    });

    systemStream.connect(currentNamespace);
});
