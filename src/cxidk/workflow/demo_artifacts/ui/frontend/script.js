// --- JS COMPONENTS ---
const createTag = (value) => {
    const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = value;
    const removeBtn = document.createElement('button'); removeBtn.className = 'remove-tag'; removeBtn.innerHTML = '&times;'; removeBtn.onclick = () => tag.remove();
    tag.appendChild(removeBtn); return tag;
};

function initializeTagInputs(container) {
    container.querySelectorAll('.multi-text-input').forEach(component => {
        const input = component.querySelector('input');
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault(); const value = input.value.trim();
                if (value) { component.insertBefore(createTag(value), input); input.value = ''; }
            }
        });
    });
}

function initializeSliders(container) {
    container.querySelectorAll('.slider-container').forEach(slider => {
        const id = slider.dataset.targetId; const min = parseFloat(slider.dataset.min); const max = parseFloat(slider.dataset.max); const step = parseFloat(slider.dataset.step);
        const isDouble = slider.dataset.end !== undefined;
        
        if (isDouble) {
            const start = parseFloat(slider.dataset.start); const end = parseFloat(slider.dataset.end);
            const decimals = String(step).includes('.') ? String(step).split('.')[1].length : 0;
            slider.innerHTML = `<div class="slider-values"><span>${start.toFixed(decimals)}</span><span>${end.toFixed(decimals)}</span></div><div class="range-slider-input"><div class="track"></div><input type="range" id="${id}_min" min="${min}" max="${max}" step="${step}" value="${start}"><input type="range" id="${id}_max" min="${min}" max="${max}" step="${step}" value="${end}"></div>`;
            const [minInput, maxInput] = slider.querySelectorAll('input'); const [minValSpan, maxValSpan] = slider.querySelectorAll('span');
            minInput.addEventListener('input', () => { if (parseFloat(minInput.value) > parseFloat(maxInput.value)) minInput.value = maxInput.value; minValSpan.textContent = parseFloat(minInput.value).toFixed(decimals); });
            maxInput.addEventListener('input', () => { if (parseFloat(maxInput.value) < parseFloat(minInput.value)) maxInput.value = minInput.value; maxValSpan.textContent = parseFloat(maxInput.value).toFixed(decimals); });
        } else {
            const start = parseFloat(slider.dataset.start);
            const decimals = String(step).includes('.') ? String(step).split('.')[1].length : 0;
            slider.innerHTML = `<div class="slider-values">Value: <span>${start.toFixed(decimals)}</span></div><div class="single-slider-input"><div class="track"></div><input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${start}"></div>`;
            const input = slider.querySelector('input'); const valSpan = slider.querySelector('span');
            input.addEventListener('input', () => { valSpan.textContent = parseFloat(input.value).toFixed(decimals); });
        }
    });
}

function setupCheckboxSliderToggles() {
    document.querySelectorAll('input[type="checkbox"][data-controls-slider]').forEach(checkbox => {
        const sliderId = checkbox.dataset.controlsSlider;
        const form = checkbox.closest('form');
        if (form) {
            const sliderContainer = form.querySelector(`.slider-container[data-target-id="${sliderId}"]`);
            if (sliderContainer) {
                checkbox.addEventListener('change', () => {
                    sliderContainer.style.display = checkbox.checked ? 'block' : 'none';
                });
            }
        }
    });
}

const addVirtualAgentFields = (containerId, prefix = '') => {
    const container = document.getElementById(containerId);
    const uniqueId = Date.now() + Math.floor(Math.random() * 1000);
    const group = document.createElement('div');
    group.className = 'virtual-agent-group';
    
    group.innerHTML = `<button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">Remove</button>
        <div class="form-grid">
            <div><label for="${prefix}va_agent_${uniqueId}">Agent ID</label><input type="text" id="${prefix}va_agent_${uniqueId}" class="va-agent"></div>
            <div><label for="${prefix}va_conv_profile_${uniqueId}">Conv. Profile</label><input type="text" id="${prefix}va_conv_profile_${uniqueId}" class="va-conversation_profile"></div>
            <div><label for="${prefix}va_location_${uniqueId}">Location</label><select id="${prefix}va_location_${uniqueId}" class="va-location"></select></div>
            <div><label for="${prefix}va_type_${uniqueId}">Type</label><select id="${prefix}va_type_${uniqueId}" class="va-type"><option value="deterministic">deterministic</option><option value="generative">generative</option><option value="next-gen">next-gen</option></select></div>
            <div><label for="${prefix}va_env_${uniqueId}">Environment</label><select id="${prefix}va_env_${uniqueId}" class="va-environment"><option value="prod">prod</option><option value="stg">stg</option></select></div>
        </div>
        <div style="margin-top:1rem">
            <label>Topics</label>
            <div class="multi-text-input" data-is-va-topic="true"><input type="text" placeholder="Add & press Enter..."></div>
        </div>`;
    
    container.appendChild(group);
    
    const regionOptions = document.getElementById('gcp-regions-template').innerHTML;
    group.querySelector('.va-location').innerHTML = regionOptions;
    
    initializeTagInputs(group);
    return group;
};

// --- JS UI ---
const showToast = (message, type = 'success') => {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    elements.toastContainer.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        toast.addEventListener('transitionend', () => toast.remove());
    }, 4000);
};

const populateForm = (form, data) => {
    const prefix = form.id.includes('add') ? 'add-' : 'edit-';
    const get = (obj, path, def = '') => { const value = path.split('.').reduce((o, k) => (o || {})[k], obj); return value !== null && value !== undefined ? value : def; };

    // Basic Fields
    form.querySelector(`#${prefix}display_name`).value = get(data, 'display_name');
    form.querySelector(`#${prefix}project_id`).value = get(data, 'project_id');
    form.querySelector(`#${prefix}project_number`).value = get(data, 'project_number');
    form.querySelector(`#${prefix}location`).value = get(data, 'location', 'us-central1');
    form.querySelector(`#${prefix}buckets_audios`).value = get(data, 'buckets.audios');
    form.querySelector(`#${prefix}buckets_transcripts`).value = get(data, 'buckets.transcripts');
    form.querySelector(`#${prefix}buckets_metadata`).value = get(data, 'buckets.metadata');
    form.querySelector(`#${prefix}gen_model`).value = get(data, 'generation_profile.model', 'gemini-2.5-pro');
    form.querySelector(`#${prefix}gen_company_name`).value = get(data, 'generation_profile.company_name');
    
    // Hidden fields for ID tracking in Edit Mode
    if(form.id === 'editProjectForm') {
        document.getElementById('edit-original-project-id').value = get(data, 'project_id');
        document.getElementById('edit-original-display-name').value = get(data, 'display_name');
    }

    // Dropdowns & Checkboxes
    const theme = get(data, 'generation_profile.theme', ['Telecommunications']);
    form.querySelector(`#${prefix}gen_theme`).value = Array.isArray(theme) && theme.length > 0 ? theme[0] : (typeof theme === 'string' ? theme : 'Telecommunications');

    const lang = get(data, 'generation_profile.language', ['en-US']);
    form.querySelector(`#${prefix}gen_language`).value = Array.isArray(lang) && lang.length > 0 ? lang[0] : (typeof lang === 'string' ? lang : 'en-US');
    
    const environments = get(data, 'environments', []);
    const envName = (form.id === 'projectForm') ? 'environments' : `${prefix}environments`;
    form.querySelectorAll(`input[name="${envName}"]`).forEach(checkbox => {
        checkbox.checked = environments.includes(checkbox.value);
    });

    const sentimentJourneys = get(data, 'generation_profile.sentiment_journeys', []);
    const sjName = (form.id === 'projectForm') ? 'gen_sentiment_journeys' : `${prefix}gen_sentiment_journeys`;
    form.querySelectorAll(`input[name="${sjName}"]`).forEach(checkbox => {
        checkbox.checked = sentimentJourneys.includes(checkbox.value);
    });
    
    // Tags
    const tagFields = { gen_topics: get(data, 'generation_profile.topics',[]), gen_prompt_hint: get(data, 'generation_profile.prompt_hint', []) };
    for(const [key, values] of Object.entries(tagFields)) {
        const container = form.querySelector(`.multi-text-input[data-target-id="${prefix}${key}"]`);
        if (container) {
            container.querySelectorAll('.tag').forEach(t => t.remove());
            (Array.isArray(values) ? values : []).forEach(val => container.insertBefore(createTag(val), container.querySelector('input')));
        }
    }
    
    // Sliders
    const setRangeSliderValue = (key, values) => {
        const minInput = form.querySelector(`#${prefix}${key}_min`); const maxInput = form.querySelector(`#${prefix}${key}_max`);
        if(minInput && maxInput && values?.length >= 2) { minInput.value = values[0]; maxInput.value = values[1]; minInput.dispatchEvent(new Event('input')); maxInput.dispatchEvent(new Event('input')); }
    };
    
    const setSingleSliderValue = (key, value) => {
        const targetId = `${prefix}${key}`;
        const input = form.querySelector(`#${targetId}`);
        const checkbox = form.querySelector(`input[data-controls-slider="${targetId}"]`);
        const container = input ? input.closest('.slider-container') : null;

        if (checkbox && container) {
            const numericValue = parseFloat(value);
            // If value exists and is > 0, activate slider. Otherwise hide.
            if (!isNaN(numericValue) && numericValue > 0) {
                checkbox.checked = true;
                container.style.display = 'block';
                input.value = numericValue;
            } else {
                checkbox.checked = false;
                container.style.display = 'none';
                input.value = container.dataset.start;
            }
            if(input) input.dispatchEvent(new Event('input'));
        } else if (input && value !== null && value !== undefined) {
            input.value = value;
            input.dispatchEvent(new Event('input'));
        }
    };

    setRangeSliderValue('gen_temperature', get(data, 'generation_profile.temperature'));
    setRangeSliderValue('gen_topk', get(data, 'generation_profile.topk'));
    setRangeSliderValue('gen_topp', get(data, 'generation_profile.topp'));
    setRangeSliderValue('probabilities_bad_sentiment', get(data, 'generation_profile.probabilities.bad_sentiment'));
    setRangeSliderValue('probabilities_long_conversation', get(data, 'generation_profile.probabilities.long_conversation'));
    setRangeSliderValue('probabilities_bad_performance', get(data, 'generation_profile.probabilities.bad_performance'));
    
    setSingleSliderValue(`max_conversations_per_run_audio`, get(data, 'generation_profile.max_conversations_per_run.audio'));
    setSingleSliderValue(`max_conversations_per_run_chat`, get(data, 'generation_profile.max_conversations_per_run.chat'));
    setSingleSliderValue(`max_conversations_per_run_agentic`, get(data, 'generation_profile.max_conversations_per_run.agentic'));

    // Virtual Agents
    const vaContainerId = `${prefix.replace(/-/g, '_')}virtual_agents_container`;
    const vaContainer = document.getElementById(vaContainerId);

    vaContainer.innerHTML = '';
    (get(data, 'virtual_agents', []) || []).forEach(agentData => {
        const group = addVirtualAgentFields(vaContainerId, prefix);
        group.querySelector('.va-agent').value = get(agentData, 'agent');
        group.querySelector('.va-conversation_profile').value = get(agentData, 'conversation_profile');
        group.querySelector('.va-location').value = get(agentData, 'location', 'global');
        group.querySelector('.va-type').value = get(agentData, 'type', 'deterministic');
        group.querySelector('.va-environment').value = get(agentData, 'environment', 'prod');
        const topicContainer = group.querySelector('.multi-text-input[data-is-va-topic]');
        (get(agentData, 'topics', []) || []).forEach(topic => topicContainer.insertBefore(createTag(topic), topicContainer.querySelector('input')));
    });
};

const renderConfigList = () => {
    elements.projectListContainer.innerHTML = '';
    if (configList.length === 0) {
        elements.projectListContainer.innerHTML = '<div class="card empty-state"><h3>Empty Configuration</h3><p>No configurations found. Add one using the form.</p></div>';
    } else {
        configList.forEach((p, i) => {
            const e = document.createElement('details');
            e.className = 'project-item';
            
            const actionsHtml = `<button class="btn btn-primary" onclick="event.stopPropagation();handleOpenEditModal(${i})">Edit</button>`;

            e.innerHTML = `<summary>
                            <div class="project-item-header">
                                <h3>${p.display_name}<span class="project-id-chip">${p.project_id}</span></h3>
                                <div class="project-item-actions" style="display:flex; gap: 0.5rem;">
                                    ${actionsHtml}
                                </div>
                            </div>
                           </summary>
                           <pre>${JSON.stringify(p, (key, value) => key === 'display_name' ? undefined : value, 2)}</pre>`;
            elements.projectListContainer.appendChild(e);
        });
    }
    elements.projectSummaryContainer.innerHTML = `<ul><li><strong>Total Demo Projects:</strong> <span class="stat-value">${configList.length}</span></li></ul>`;
};

const renderConversationStats = (statsData, oldStatsData = null) => {
    const summaryContainer = elements.conversationSummaryContainer;
    const detailsContainer = elements.conversationDetailsContainer;
    const projects = statsData.projects || {};
    const oldProjects = oldStatsData ? oldStatsData.projects || {} : {};
    const lastRun = statsData.last_run_utc;

    summaryContainer.innerHTML = '';
    detailsContainer.innerHTML = '';

    const formatDelta = (delta) => {
        if (!oldStatsData || delta === 0) return '';
        const sign = delta > 0 ? '+' : '';
        const className = delta > 0 ? 'positive' : 'negative';
        return `<span class="delta ${className}">(${sign}${delta.toLocaleString()})</span>`;
    };

    if (configList.length > 0 && Object.keys(projects).length === 0) {
        detailsContainer.innerHTML = '<p>No conversation data found. Click the refresh icon to perform an initial count.</p>';
        return;
    }
    if (configList.length === 0) {
        detailsContainer.innerHTML = '<p>No projects configured. Click "New Configuration" to add one.</p>';
        return;
    }

    let detailsHtml = '';
    const sortedProjectIds = Object.keys(projects).sort();

    sortedProjectIds.forEach(projectId => {
        const projectStats = projects[projectId];
        const newTotal = projectStats.total || 0;
        const oldTotal = oldProjects[projectId] ? oldProjects[projectId].total || 0 : 0;
        const delta = newTotal - oldTotal;
        const deltaHtml = formatDelta(delta);

        detailsHtml += `<h4>${projectId}</h4>
                         <ul>
                            <li>
                                <span>Total Conversations</span>
                                <div>
                                   <span class="stat-value">${newTotal.toLocaleString()}</span>
                                   ${deltaHtml}
                                </div>
                            </li>
                         </ul>`;
    });

    if (lastRun) {
        const localDate = new Date(lastRun).toLocaleString();
        detailsHtml += `<p style="margin-top: 1rem; font-size: 0.8em; color: var(--text-muted);"></p>`;
    }
    detailsContainer.innerHTML = detailsHtml;
    
    let grandTotal = 0;
    Object.values(projects).forEach(p => { grandTotal += p.total || 0; });
    
    let oldGrandTotal = 0;
    Object.values(oldProjects).forEach(p => { oldGrandTotal += p.total || 0; });

    const grandDelta = grandTotal - oldGrandTotal;
    const grandDeltaHtml = formatDelta(grandDelta);

    const summaryHtml = `
        <h4>Overall Summary</h4>
        <ul>
            <li>
                <span>Total Conversations</span>
                <div>
                    <span class="stat-value">${grandTotal.toLocaleString()}</span>
                    ${grandDeltaHtml}
                </div>
            </li>
        </ul>`;
    summaryContainer.innerHTML = summaryHtml;
};

const resetForm=(formElement, containerId)=>{
    formElement.reset();
    document.getElementById(containerId).innerHTML = '';

    formElement.querySelectorAll('.slider-container').forEach(c => { 
        if(c.style.display !== 'none') c.style.display = 'none';
        const checkbox = formElement.querySelector(`input[data-controls-slider="${c.dataset.targetId}"]`);
        if (checkbox) checkbox.checked = false;
    });

    initializeSliders(formElement);

    formElement.querySelectorAll('.multi-text-input .tag').forEach(t => t.remove());
    // Clear validation states
    formElement.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
};

const openViewModal = async () => { 
    if (!jsonViewer) {
        jsonViewer = CodeMirror(elements.jsonViewerContainer, {mode: {name: "javascript", json: true}, theme: "material-dark", lineNumbers: true, readOnly: true, lineWrapping: true});
    }
    try { 
        const response = await fetch(`${API_URL}/configurations/raw`); 
        if (!response.ok) throw new Error('Could not fetch raw config.'); 
        const rawText = await response.text(); 
        jsonViewer.setValue(rawText); 
    } catch (err) { 
        showToast(`Error fetching raw config: ${err.message}`, 'error'); 
        jsonViewer.setValue('// Could not load configuration'); 
    } 
    elements.copyJsonBtn.textContent = 'Copy'; 
    elements.jsonModal.classList.add('is-active'); 
    setTimeout(() => jsonViewer.refresh(), 1); 
};

const closeViewModal=()=>elements.jsonModal.classList.remove('is-active');
const openAddModal=()=>{resetForm(elements.addProjectForm, 'modal_virtual_agents_container');elements.addProjectModal.classList.add('is-active')};
const closeAddModal=()=>elements.addProjectModal.classList.remove('is-active');

const handleOpenEditModal = (index) => {
    const configData = configList[index];
    elements.editProjectIndex.value = index;
    document.getElementById('edit-project-title').textContent = `Edit: ${configData.display_name}`;
    
    // Reset form to clear previous state
    resetForm(elements.editProjectForm, 'edit_virtual_agents_container');
    
    // Populate with current data
    populateForm(elements.editProjectForm, configData);
    elements.editProjectModal.classList.add('is-active');
};
const closeEditModal = () => elements.editProjectModal.classList.remove('is-active');

// --- JS API ---
async function loadConfigs() {
    elements.projectListContainer.innerHTML = '<div class="spinner"></div>';
    try {
        const response = await fetch(`${API_URL}/configurations`);
        if (!response.ok) throw new Error(`Failed to load config file (${response.status})`);
        const data = await response.json();
        configList = data.configurations || [];
        renderConfigList();
        showToast('Configuration loaded successfully.', 'success');
    } catch (error) {
        showToast(`Could not load configuration: ${error.message}`, "error");
        elements.projectListContainer.innerHTML = '<p>Could not connect to the backend or load the configuration file.</p>';
    }
}

async function saveSingleConfig(action, configData, originalProjectId=null, originalDisplayName=null) {
    showToast('Saving changes...', 'success');
    try {
        const payload = {
            action: action,
            configuration: configData,
            original_project_id: originalProjectId,
            original_display_name: originalDisplayName
        };

        const response = await fetch(`${API_URL}/configurations/single`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Save failed: ${errorData.description || 'Unknown error'}`);
        }
        
        showToast('Changes saved successfully!', 'success');
        // Reload to reflect changes and any updates from other users
        await loadConfigs();
        return true;
    } catch (error) {
        showToast(`Error saving config: ${error.message}`, 'error');
        return false;
    }
}

async function refreshConversationStats(isInitialLoad = false) {
    const spinnerHtml = isInitialLoad 
        ? '<div class="spinner"></div><p style="text-align: center;">Loading and refreshing stats...</p>'
        : '<div class="spinner"></div><p style="text-align: center;">Refreshing stats...</p>';
    
    elements.conversationDetailsContainer.innerHTML = spinnerHtml;
    elements.conversationSummaryContainer.innerHTML = '';
    elements.refreshStatsBtn.disabled = true;
    const icon = elements.refreshStatsBtn.querySelector('svg');
    if (icon) icon.classList.add('spinning');

    let oldStats = {};

    try {
        const oldStatsResponse = await fetch(`${API_URL}/conversation-counts`);
        if (oldStatsResponse.ok) {
            oldStats = await oldStatsResponse.json();
        } else {
            console.warn("Could not fetch old stats to calculate delta.");
        }

        const refreshResponse = await fetch(`${API_URL}/conversation-counts`, { method: 'POST' });
        if (!refreshResponse.ok) {
            const errorData = await refreshResponse.json();
            throw new Error(errorData.error || `Failed to refresh stats (${refreshResponse.status})`);
        }
        const newStats = await refreshResponse.json();

        renderConversationStats(newStats.data, oldStats);
        showToast(newStats.message || 'Stats refreshed successfully!', 'success');

    } catch (error) {
        showToast(`Error refreshing stats: ${error.message}`, 'error');
        if (Object.keys(oldStats).length > 0) {
            renderConversationStats(oldStats);
        } else {
            elements.conversationDetailsContainer.innerHTML = `<p class="error">Could not refresh stats.</p>`;
        }
    } finally {
        elements.refreshStatsBtn.disabled = false;
        if (icon) icon.classList.remove('spinning');
    }
}

// --- MAIN ---
const elements = { 
    projectListContainer: document.getElementById('projectListContainer'), toastContainer: document.getElementById('toast-container'),
    viewRawJsonBtn: document.getElementById('viewRawJsonBtn'), jsonModal: document.getElementById('json-modal'), jsonViewerContainer: document.getElementById('json-viewer-container'), copyJsonBtn: document.getElementById('copyJsonBtn'), downloadJsonBtn: document.getElementById('downloadJsonBtn'),
    addProjectBtn: document.getElementById('addProjectBtn'),
    addNewProjectBtn: document.getElementById('addNewProjectBtn'), addProjectModal: document.getElementById('add-project-modal'), addProjectForm: document.getElementById('addProjectForm'),
    saveNewProjectBtn: document.getElementById('saveNewProjectBtn'), cancelAddProjectBtn: document.getElementById('cancelAddProjectBtn'),
    editProjectModal: document.getElementById('edit-project-modal'), editProjectForm: document.getElementById('editProjectForm'), editProjectIndex: document.getElementById('edit-project-index'),
    saveEditProjectBtn: document.getElementById('saveEditProjectBtn'), cancelEditProjectBtn: document.getElementById('cancelEditProjectBtn'),
    projectSummaryContainer: document.getElementById('project-summary-container'),
    darkModeToggle: document.getElementById('darkModeToggle'),
    conversationSummaryContainer: document.getElementById('conversation-summary-container'),
    conversationDetailsContainer: document.getElementById('conversation-details-container'),
    refreshStatsBtn: document.getElementById('refresh-stats-btn'),
};

const API_URL = '';
const PROJECTS_FILENAME = 'projects.json';

let configList = [];
let jsonViewer = null;

function collectConfigData(form, containerSelector) {
    const prefix = form.id.includes('add') ? 'add-' : (form.id.includes('edit') ? 'edit-' : '');
    
    // --- 1. MANDATORY FIELD VALIDATION ---
    const requiredFields = [
        'display_name',
        'project_id',
        'project_number',
        'location',
        'buckets_audios',
        'buckets_transcripts',
        'buckets_metadata'
    ];
    
    let isValid = true;
    let firstInvalid = null;

    // Reset styles
    form.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));

    requiredFields.forEach(field => {
        const input = form.querySelector(`#${prefix}${field}`);
        if (!input || !input.value.trim()) {
            isValid = false;
            if(input) input.classList.add('is-invalid');
            if(!firstInvalid) firstInvalid = input;
        }
    });

    if (!isValid) {
        showToast('Please fill in all required fields (marked with *).', 'error');
        if(firstInvalid) firstInvalid.focus();
        return null;
    }

    let displayName = form.querySelector(`#${prefix}display_name`).value.trim();
    const projectId = form.querySelector(`#${prefix}project_id`).value.trim();
    if (!displayName) { displayName = projectId; }
    
    const flatData = { 'display_name': displayName };
    
    // Harvest text inputs
    form.querySelectorAll('input[type="text"], input[type="number"], select, textarea').forEach(input => {
        if(!input.parentElement.classList.contains('multi-text-input')) {
            const key = input.id.replace(prefix, '');
            if (key && key !== 'display_name') flatData[key] = input.value;
        }
    });
    
    // Harvest Checkboxes
    const envName = (form.id === 'projectForm') ? 'environments' : `${prefix}environments`;
    flatData.environments = Array.from(form.querySelectorAll(`input[name="${envName}"]:checked`)).map(cb => cb.value).join(',');

    const sjName = (form.id === 'projectForm') ? 'gen_sentiment_journeys' : `${prefix}gen_sentiment_journeys`;
    flatData.gen_sentiment_journeys = Array.from(form.querySelectorAll(`input[name="${sjName}"]:checked`)).map(cb => cb.value).join(',');

    // Harvest Multi-text inputs (Tags)
    form.querySelectorAll('.multi-text-input:not([data-is-va-topic])').forEach(container => {
        const key = container.dataset.targetId.replace(prefix, '');
        flatData[key] = Array.from(container.querySelectorAll('.tag')).map(t => t.textContent.slice(0, -1).trim()).join(',');
    });
    
    // Harvest Sliders & Conversation Counts
    let hasAnyConversations = false;
    form.querySelectorAll('.slider-container').forEach(container => {
        const key = container.dataset.targetId.replace(prefix, '');
        const checkbox = form.querySelector(`input[data-controls-slider="${container.dataset.targetId}"]`);

        // Logic for conversation count sliders
        if (key.startsWith('max_conversations_per_run')) {
             if (checkbox && checkbox.checked) {
                 hasAnyConversations = true;
             }
        }

        if (checkbox && !checkbox.checked) {
            flatData[key] = '0';
        } else {
            const inputs = container.querySelectorAll('input[type="range"]');
            if(inputs.length > 1) { flatData[key] = `${inputs[0].value},${inputs[1].value}`; } else if(inputs.length === 1) { flatData[key] = inputs[0].value; }
        }
    });

    // --- 2. SMART NOTE (SOFT WARNING) ---
    if (!hasAnyConversations) {
        if (!confirm("Note: You have not enabled any conversation generation (Audio, Chat, or Agentic are all unchecked). \n\nAre you sure you want to save this configuration without generating any data?")) {
            return null; // Stop save process
        }
    }

    const virtualAgents = [];
    document.querySelectorAll(`${containerSelector} .virtual-agent-group`).forEach(group => {
        virtualAgents.push({
            agent: group.querySelector('.va-agent').value.trim(), conversation_profile: group.querySelector('.va-conversation_profile').value.trim(), 
            location: group.querySelector('.va-location').value.trim(), type: group.querySelector('.va-type').value.trim(), 
            environment: group.querySelector('.va-environment').value.trim(), 
            topics: Array.from(group.querySelectorAll('.multi-text-input[data-is-va-topic] .tag')).map(t => t.textContent.slice(0, -1).trim()),
        });
    });
    flatData['virtual_agents'] = virtualAgents;
    return flatData;
}

async function handleAddNewConfig() {
    const newConfigData = collectConfigData(elements.addProjectForm, '#modal_virtual_agents_container');
    if (!newConfigData) return;

    if (configList.some(c => c.display_name === newConfigData.display_name)) {
        showToast(`Display Name "${newConfigData.display_name}" already exists. It must be unique.`, 'error');
        return;
    }

    const success = await saveSingleConfig('add', newConfigData);
    if(success) closeAddModal();
}

async function handleSaveEditedConfig() {
    const editedConfigData = collectConfigData(elements.editProjectForm, '#edit_virtual_agents_container');
    if (!editedConfigData) return;
    
    // Retrieve hidden original IDs
    const originalProjectId = document.getElementById('edit-original-project-id').value;
    const originalDisplayName = document.getElementById('edit-original-display-name').value;

    const index = parseInt(elements.editProjectIndex.value);
    
    // Check uniqueness excluding self
    if (configList.some((c, i) => i !== index && c.display_name === editedConfigData.display_name)) {
        showToast(`Display Name "${editedConfigData.display_name}" already exists. It must be unique.`, 'error');
        return;
    }

    const success = await saveSingleConfig('edit', editedConfigData, originalProjectId, originalDisplayName);
    if(success) closeEditModal();
}

async function handleSidebarAddConfig() {
    const newConfigData = collectConfigData(document.getElementById('projectForm'), '#sidebar_virtual_agents_container');
    if (!newConfigData) return;

    if (configList.some(c => c.display_name === newConfigData.display_name)) {
        showToast(`Display Name "${newConfigData.display_name}" already exists. It must be unique.`, 'error');
        return;
    }
    const success = await saveSingleConfig('add', newConfigData);
    if(success) resetForm(document.getElementById('projectForm'), 'sidebar_virtual_agents_container');
}

function applyDarkMode(isDark) {
    if (isDark) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
}

elements.darkModeToggle.addEventListener('change', (e) => {
    const isDark = e.target.checked;
    applyDarkMode(isDark);
    localStorage.setItem('darkMode', isDark ? 'enabled' : 'disabled');
});

elements.addProjectBtn.addEventListener('click', handleSidebarAddConfig);
elements.saveNewProjectBtn.addEventListener('click', handleAddNewConfig);
elements.saveEditProjectBtn.addEventListener('click', handleSaveEditedConfig);
elements.viewRawJsonBtn.addEventListener('click', openViewModal);
elements.addNewProjectBtn.addEventListener('click', openAddModal);
elements.refreshStatsBtn.addEventListener('click', () => refreshConversationStats(false));

elements.copyJsonBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(jsonViewer.getValue()).then(() => {
        elements.copyJsonBtn.textContent = 'Copied!';
        setTimeout(() => { elements.copyJsonBtn.textContent = 'Copy' }, 2000);
    }).catch(e => { showToast('Failed to copy JSON!', 'error') });
});
elements.downloadJsonBtn.addEventListener('click', () => {
    const blob = new Blob([jsonViewer.getValue()], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = PROJECTS_FILENAME;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

[elements.jsonModal, elements.addProjectModal, elements.editProjectModal].forEach(modal => {
    modal.querySelector('.modal-background').addEventListener('click', () => modal.classList.remove('is-active'));
    modal.querySelector('.modal-close').addEventListener('click', () => modal.classList.remove('is-active'));
});
elements.cancelAddProjectBtn.addEventListener('click', closeAddModal);
elements.cancelEditProjectBtn.addEventListener('click', closeEditModal);

document.addEventListener('keydown', e => {
    if (e.key === "Escape") {
        [elements.jsonModal, elements.addProjectModal, elements.editProjectModal].forEach(m => m.classList.remove('is-active'));
    }
});

// Remove invalid class on input
document.addEventListener('input', (e) => {
    if(e.target.classList.contains('is-invalid')) {
        e.target.classList.remove('is-invalid');
    }
});

document.addEventListener('DOMContentLoaded', async () => {
    const regionOptions = document.getElementById('gcp-regions-template').innerHTML;
    document.querySelectorAll('select[id*="location"]').forEach(sel => sel.innerHTML = regionOptions);
    initializeTagInputs(document);
    initializeSliders(document);
    setupCheckboxSliderToggles();
    
    await loadConfigs();
    await refreshConversationStats(true);

    const savedDarkMode = localStorage.getItem('darkMode');
    if (savedDarkMode === 'disabled') {
        elements.darkModeToggle.checked = false;
        applyDarkMode(false);
    } else {
        elements.darkModeToggle.checked = true;
        applyDarkMode(true);
    }
});
