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
    sendVoiceCommandApi,
    fetchMissions,
    fetchMissionReport
} from './api/restClient';
import { getEl, appendTerminalLine, showFeedbackResult, escapeHtml } from './ui/domUtils';
import { setupTabs } from './ui/tabs';
import { GraphRenderer } from './ui/graphRenderer';
import { setupDragAndDrop } from './ui/dragDrop';
import { AudioRecorder } from './media/audioRecorder';

const safeArtifactUrl = (value: unknown): string => {
    try {
        const url = new URL(String(value || ''), window.location.origin);
        return url.origin === window.location.origin && url.pathname.startsWith('/data/artifacts/')
            ? `${url.pathname}${url.search}`
            : '#';
    } catch {
        return '#';
    }
};

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
    let graphLoadGeneration = 0;

    namespaceSelect.addEventListener('change', () => {
        currentNamespace = namespaceSelect.value;
        agentSocket.updateNamespace(currentNamespace);
        systemStream.connect(currentNamespace);
        if (getEl('knowledge-tab').classList.contains('active')) {
            if (graphFileSelect) graphFileSelect.value = "";
            loadGraph();
        }
    });

    setupTabs({
        onLoadGraph: loadGraph,
        onLoadTelemetry: loadTelemetry,
        onLoadSpatial: loadSpatial,
        onLoadExperiences: loadExperiences,
        onLoadReports: loadReports
    });

    // --- Graph & Data Loaders ---
    async function loadGraphFiles(namespace: string, generation: number) {
        if (!graphFileSelect) return;
        try {
            const data = await fetchGraphFiles(namespace);
            if (generation !== graphLoadGeneration) return;
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
        const generation = ++graphLoadGeneration;
        const namespace = currentNamespace;
        graphRenderer.showLoading();
        try {
            await loadGraphFiles(namespace, generation);
            if (generation !== graphLoadGeneration) return;
            const selectedFile = graphFileSelect?.value || '';
            const data = await fetchGraphData(namespace, selectedFile);
            if (generation === graphLoadGeneration) await graphRenderer.render(data);
        } catch (e) {
            if (generation !== graphLoadGeneration) return;
            console.error(e);
            graphRenderer.showError();
        }
    }

    graphFileSelect?.addEventListener('change', () => {
        loadGraph();
    });

    async function loadTelemetry() {
        try {
            const data = await fetchTelemetry(currentNamespace);
            renderTelemetry(data.readings || []);
        } catch (e) { console.error(e); }
    }

    function renderTelemetry(readings: any[]) {
        const container = getEl('telemetry-display');
        if (!readings.length) {
            container.innerHTML = '<div class="empty-jobs">Nenhuma leitura de sensor registrada.</div>';
            return;
        }
        container.innerHTML = readings.map(reading => `
            <div class="telemetry-card-mini">
                <span class="telemetry-label">${escapeHtml(reading.entity_name)}</span>
                <span class="telemetry-value">${escapeHtml(reading.raw_reading || (reading.value ?? '—'))}</span>
                <span class="telemetry-unit">${escapeHtml(reading.unit || '')} · ${escapeHtml(reading.timestamp)}</span>
            </div>
        `).join('');
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
                <span class="spatial-location">${escapeHtml(ent.last_location)}</span>
                    <span class="spatial-name">${escapeHtml(ent.name)}</span>
                    <span class="job-footer">Tipo: ${escapeHtml(ent.type)} | Visto: ${escapeHtml(new Date(ent.last_seen).toLocaleTimeString())}</span>
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
                        <span class="timeline-mission">${escapeHtml(exp.mission_name)}</span>
                        <span class="timeline-date">${escapeHtml(new Date(exp.timestamp).toLocaleDateString())}</span>
                    </div>
                    <p>${escapeHtml(exp.task_description)}</p>
                    <div class="timeline-strategy">
                        <strong>ESTRATÉGIA VENCEDORA:</strong><br>
                        ${escapeHtml(exp.winning_strategy)}
                    </div>
                </div>
            `).join('');
        } catch (e) { console.error(e); }
    }

    // --- Reports Loaders ---
    async function loadReports() {
        const folderList = getEl('missions-folder-list');
        folderList.innerHTML = '<div class="empty-jobs">Carregando relatórios...</div>';
        try {
            const data = await fetchMissions(currentNamespace);
            if (!data.missions || data.missions.length === 0) {
                folderList.innerHTML = '<div class="empty-jobs">Nenhum relatório encontrado.</div>';
                return;
            }
            folderList.innerHTML = data.missions.map((m: any) => `
                <div class="system-task-item" style="cursor: pointer;" data-id="${escapeHtml(m.id)}">
                    <div class="task-meta">
                        <h4>📁 ${new Date(m.timestamp).toLocaleString()}</h4>
                    <span>${escapeHtml(String(m.mission || '').substring(0, 50))}...</span>
                    </div>
                </div>
            `).join('');

            // Adicionar evento de clique em cada pasta
            folderList.querySelectorAll('.system-task-item').forEach(el => {
                el.addEventListener('click', async (e) => {
                    const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
                    if (id) {
                        await loadReportDetails(id);
                        // Highlight selected
                        folderList.querySelectorAll('.system-task-item').forEach(i => (i as HTMLElement).style.borderLeft = "none");
                        (e.currentTarget as HTMLElement).style.borderLeft = "3px solid var(--accent-primary)";
                    }
                });
            });
        } catch (e) { console.error(e); }
    }

    async function loadReportDetails(id: string) {
        const reportBody = getEl('report-content-body');
        reportBody.innerHTML = '<div class="empty-artifacts">Carregando detalhes...</div>';
        try {
            const data = await fetchMissionReport(id, currentNamespace);
            reportBody.innerHTML = `
                <h3 style="margin-top: 0;">Objetivo</h3>
                <p style="white-space: pre-wrap; font-family: monospace; font-size: 13px; color: var(--text-secondary); background: var(--bg-secondary); padding: 10px; border-radius: 4px;">${escapeHtml(data.mission)}</p>
                
                <h3 style="margin-top: 15px;">Plano de Ação</h3>
                <p style="white-space: pre-wrap; font-family: monospace; font-size: 13px; color: var(--text-secondary); background: var(--bg-secondary); padding: 10px; border-radius: 4px;">${escapeHtml(data.plan)}</p>
                
                <h3 style="margin-top: 15px;">Solução Implementada (Engenharia)</h3>
                <p style="white-space: pre-wrap; font-family: monospace; font-size: 13px; color: var(--text-secondary); background: var(--bg-secondary); padding: 10px; border-radius: 4px;">${escapeHtml(data.solution)}</p>
                
                <h3 style="margin-top: 15px;">Parecer da Auditoria</h3>
                <p style="white-space: pre-wrap; font-family: monospace; font-size: 13px; color: var(--text-secondary); background: var(--bg-secondary); padding: 10px; border-radius: 4px;">${escapeHtml(data.audit)}</p>
            `;
        } catch (e) {
            reportBody.innerHTML = '<div class="empty-artifacts">Erro ao carregar relatório.</div>';
            console.error(e);
        }
    }

    async function loadQuickReport() {
        try {
            const data = await fetchMissions(currentNamespace);
            if (data.missions && data.missions.length > 0) {
                // Pega a primeira missão (mais recente)
                const latestMissionId = data.missions[0].id;
                const report = await fetchMissionReport(latestMissionId, currentNamespace);
                
                const quickCard = getEl('mission-quick-report');
                const quickContent = getEl('quick-report-content');
                if (!quickCard || !quickContent) return;
                
                quickCard.style.display = 'block';
                quickContent.innerHTML = `
                    <h3 style="margin-top: 0; font-size: 14px; color: var(--text-primary);">Parecer do Auditor</h3>
                    <p style="white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; background: var(--bg-secondary); padding: 10px; border-radius: 6px; border: 1px solid var(--border-color);">${escapeHtml(report.audit)}</p>
                    
                    <h3 style="font-size: 14px; color: var(--text-primary); margin-top: 15px;">Solução de Engenharia</h3>
                    <p style="white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; background: var(--bg-secondary); padding: 10px; border-radius: 6px; border: 1px solid var(--border-color); max-height: 400px; overflow-y: auto;">${escapeHtml(report.solution)}</p>
                `;
            }
        } catch(e) {
            console.error("Failed to load quick report", e);
        }
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
                    <span class="job-filename">${escapeHtml(job.filename)}</span>
                    <span class="job-badge ${escapeHtml(statusClass)}">${escapeHtml(job.status)}</span>
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
    let agentMissionActive = false;
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
                case 'mission_complete':
                    agentMissionActive = false;
                    runMissionBtn.textContent = 'INICIAR MISSÃO';
                    showFeedbackResult(messageBox, messageText, feedbackArea, progressBar, dropZone, fileInput, 'success', 'Missão Completa');
                    loadQuickReport(); // Mostra o relatório diretamente na tela de missões
                    if (getEl('reports-tab').classList.contains('active')) {
                        loadReports();
                    }
                    break;
                case 'mission_failed':
                    agentMissionActive = false;
                    runMissionBtn.textContent = 'INICIAR MISSÃO';
                    showFeedbackResult(messageBox, messageText, feedbackArea, progressBar, dropZone, fileInput, 'error', data.message || 'Missão reprovada na auditoria.');
                    loadQuickReport();
                    break;
                case 'mission_cancelled':
                    agentMissionActive = false;
                    runMissionBtn.textContent = 'INICIAR MISSÃO';
                    showFeedbackResult(messageBox, messageText, feedbackArea, progressBar, dropZone, fileInput, 'error', data.message || 'Missão cancelada.');
                    break;
            }
        },
        onClose: () => {
            if (agentMissionActive) {
                agentMissionActive = false;
                runMissionBtn.textContent = 'INICIAR MISSÃO';
            }
        }
    }, currentNamespace);

    const startAgentMission = (mission: string) => {
        agentDisplay.classList.remove('hidden');
        agentThought.textContent = 'Iniciando...';
        agentTerminal.innerHTML = '';
        appendTerminalLine(agentTerminal, 'system', 'Conectando...', '> ');
        
        // Esconde o relatório rápido da missão anterior
        const quickCard = getEl('mission-quick-report');
        if (quickCard) quickCard.style.display = 'none';

        agentMissionActive = true;
        runMissionBtn.textContent = 'CANCELAR MISSÃO';
        agentSocket.connect(mission);
    };

    runMissionBtn.addEventListener('click', () => {
        if (agentMissionActive) {
            agentSocket.abort();
            return;
        }
        const mission = missionInput.value.trim();
        if (!mission) return alert('Descreva a missão.');
        startAgentMission(mission);
    });

    // --- Audio Recorder ---
    const audioRecorder = new AudioRecorder({
        onStart: () => {
            voiceBtn.classList.add('recording');
            voiceBtn.setAttribute('aria-pressed', 'true');
            voiceBtn.setAttribute('aria-label', 'Parar gravação de comando');
        },
        onStop: async (blob) => {
            voiceBtn.classList.remove('recording');
            voiceBtn.setAttribute('aria-pressed', 'false');
            voiceBtn.setAttribute('aria-label', 'Gravar comando de voz');
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
            voiceBtn.classList.remove('recording');
            voiceBtn.setAttribute('aria-pressed', 'false');
            voiceBtn.setAttribute('aria-label', 'Gravar comando de voz');
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
                        <h4>${escapeHtml(task.name)}</h4>
                        <span>ID: ${escapeHtml(String(task.id || '').split('-')[0])} • Retries: ${escapeHtml(task.retries)}</span>
                    </div>
                    <div class="status-badge ${escapeHtml(task.status)}">${escapeHtml(task.status)}</div>
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
                const artifactUrl = safeArtifactUrl(art.url);
                const safeName = escapeHtml(art.name);
                const isImage = artifactUrl !== '#' && /\.(jpg|jpeg|png|webp|gif)$/i.test(String(art.name));
                const icon = isImage ? '' : `<div class="file-icon">📄</div>`;
                item.innerHTML = `
                    ${isImage ? `<img src="${escapeHtml(artifactUrl)}" class="artifact-preview" alt="${safeName}">` : icon}
                    <div class="artifact-info">
                        <a href="${escapeHtml(artifactUrl)}" target="_blank" rel="noopener noreferrer">${safeName}</a>
                        <div>${escapeHtml((Number(art.size) / 1024 || 0).toFixed(1))} KB</div>
                    </div>
                `;
                artifactGallery.appendChild(item);
            });
        },
        onJobsUpdate: (jobs) => {
            renderJobs(jobs);
        },
        onTelemetryUpdate: (readings) => renderTelemetry(readings),
        onLogsUpdate: (logs) => {
            const logTextEl = getEl('log-text');
            if (logTextEl) logTextEl.textContent = String(logs || '').replace(/<br\s*\/?\s*>/gi, '\n');
        },
        onError: (err) => {
            console.error('SSE Stream Error', err);
        }
    });

    systemStream.connect(currentNamespace);
});
