(() => {
// Security: Standalone API key is held strictly in closure memory (never persisted
// to localStorage or sessionStorage) to prevent credential theft via Web Storage.
let runtimeApiKey = '';
let pendingApiKeyPrompt = null;

// --- JS COMPONENTS ---
const createTag = (value) => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.dataset.value = value;
    tag.appendChild(document.createTextNode(value));

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'remove-tag';
    removeBtn.textContent = '\u00D7';
    removeBtn.addEventListener('click', () => tag.remove());

    tag.appendChild(removeBtn);
    return tag;
};

function initializeTagInputs(container) {
    container.querySelectorAll('.multi-text-input').forEach((component) => {
        const input = component.querySelector('input');
        if (!input || input.dataset.tagInitialized === 'true') return;
        input.dataset.tagInitialized = 'true';
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const value = input.value.trim();
                if (value) {
                    component.insertBefore(createTag(value), input);
                    input.value = '';
                }
            }
        });
    });
}

function initializeSliders(container) {
    container.querySelectorAll('.slider-container').forEach((slider) => {
        const id = slider.dataset.targetId;
        const min = parseFloat(slider.dataset.min);
        const max = parseFloat(slider.dataset.max);
        const step = parseFloat(slider.dataset.step);
        const isDouble = slider.dataset.end !== undefined;
        const decimals = String(step).includes('.') ? String(step).split('.')[1].length : 0;

        if (isDouble) {
            const start = parseFloat(slider.dataset.start);
            const end = parseFloat(slider.dataset.end);

            const valuesDiv = document.createElement('div');
            valuesDiv.className = 'slider-values';
            const minValSpan = document.createElement('span');
            minValSpan.textContent = start.toFixed(decimals);
            const maxValSpan = document.createElement('span');
            maxValSpan.textContent = end.toFixed(decimals);
            valuesDiv.append(minValSpan, maxValSpan);

            const rangeWrapper = document.createElement('div');
            rangeWrapper.className = 'range-slider-input';
            const track = document.createElement('div');
            track.className = 'track';

            const minInput = document.createElement('input');
            minInput.type = 'range';
            minInput.id = `${id}_min`;
            minInput.min = String(min);
            minInput.max = String(max);
            minInput.step = String(step);
            minInput.value = String(start);

            const maxInput = document.createElement('input');
            maxInput.type = 'range';
            maxInput.id = `${id}_max`;
            maxInput.min = String(min);
            maxInput.max = String(max);
            maxInput.step = String(step);
            maxInput.value = String(end);

            rangeWrapper.append(track, minInput, maxInput);
            slider.replaceChildren(valuesDiv, rangeWrapper);

            minInput.addEventListener('input', () => {
                if (parseFloat(minInput.value) > parseFloat(maxInput.value)) {
                    minInput.value = maxInput.value;
                }
                minValSpan.textContent = parseFloat(minInput.value).toFixed(decimals);
            });
            maxInput.addEventListener('input', () => {
                if (parseFloat(maxInput.value) < parseFloat(minInput.value)) {
                    maxInput.value = minInput.value;
                }
                maxValSpan.textContent = parseFloat(maxInput.value).toFixed(decimals);
            });
        } else {
            const start = parseFloat(slider.dataset.start);

            const valuesDiv = document.createElement('div');
            valuesDiv.className = 'slider-values';
            valuesDiv.appendChild(document.createTextNode('Value: '));
            const valSpan = document.createElement('span');
            valSpan.textContent = start.toFixed(decimals);
            valuesDiv.appendChild(valSpan);

            const singleWrapper = document.createElement('div');
            singleWrapper.className = 'single-slider-input';
            const track = document.createElement('div');
            track.className = 'track';

            const input = document.createElement('input');
            input.type = 'range';
            input.id = id;
            input.min = String(min);
            input.max = String(max);
            input.step = String(step);
            input.value = String(start);

            singleWrapper.append(track, input);
            slider.replaceChildren(valuesDiv, singleWrapper);

            input.addEventListener('input', () => {
                valSpan.textContent = parseFloat(input.value).toFixed(decimals);
            });
        }
    });
}

function setupCheckboxSliderToggles() {
    document.querySelectorAll('input[type="checkbox"][data-controls-slider]').forEach((checkbox) => {
        const sliderId = checkbox.dataset.controlsSlider;
        const form = checkbox.closest('form');
        if (form) {
            const sliderContainer = form.querySelector(`.slider-container[data-target-id="${sliderId}"]`);
            if (sliderContainer) {
                checkbox.addEventListener('change', () => {
                    if (checkbox.checked) {
                        sliderContainer.classList.remove('is-hidden');
                    } else {
                        sliderContainer.classList.add('is-hidden');
                    }
                });
            }
        }
    });
}

const createLabeledControl = (labelText, controlEl) => {
    const wrapper = document.createElement('div');
    const label = document.createElement('label');
    if (controlEl.id) {
        label.setAttribute('for', controlEl.id);
    }
    label.textContent = labelText;
    wrapper.append(label, controlEl);
    return wrapper;
};

const addVirtualAgentFields = (containerId, prefix = '') => {
    const container = document.getElementById(containerId);
    if (!container) return null;

    const uniqueId = Date.now() + Math.floor(Math.random() * 1000);
    const group = document.createElement('div');
    group.className = 'virtual-agent-group';

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn btn-danger';
    removeBtn.textContent = 'Remove';
    removeBtn.addEventListener('click', () => group.remove());

    const grid = document.createElement('div');
    grid.className = 'form-grid';

    const agentInput = document.createElement('input');
    agentInput.type = 'text';
    agentInput.id = `${prefix}va_agent_${uniqueId}`;
    agentInput.className = 'va-agent';

    const profileInput = document.createElement('input');
    profileInput.type = 'text';
    profileInput.id = `${prefix}va_conv_profile_${uniqueId}`;
    profileInput.className = 'va-conversation_profile';

    const locationSelect = document.createElement('select');
    locationSelect.id = `${prefix}va_location_${uniqueId}`;
    locationSelect.className = 'va-location';
    const regionTemplate = document.getElementById('gcp-regions-template');
    if (regionTemplate && regionTemplate.content) {
        locationSelect.replaceChildren(regionTemplate.content.cloneNode(true));
    }

    const typeSelect = document.createElement('select');
    typeSelect.id = `${prefix}va_type_${uniqueId}`;
    typeSelect.className = 'va-type';
    ['deterministic', 'generative', 'next-gen', 'agent-studio', 'cxas'].forEach((vaType) => {
        const opt = document.createElement('option');
        opt.value = vaType;
        opt.textContent = vaType;
        typeSelect.appendChild(opt);
    });

    const envSelect = document.createElement('select');
    envSelect.id = `${prefix}va_env_${uniqueId}`;
    envSelect.className = 'va-environment';
    ['prod', 'stg'].forEach((envVal) => {
        const opt = document.createElement('option');
        opt.value = envVal;
        opt.textContent = envVal;
        envSelect.appendChild(opt);
    });

    grid.append(
        createLabeledControl('Agent ID', agentInput),
        createLabeledControl('Conv. Profile', profileInput),
        createLabeledControl('Location', locationSelect),
        createLabeledControl('Type', typeSelect),
        createLabeledControl('Environment', envSelect)
    );

    const topicsWrapper = document.createElement('div');
    topicsWrapper.className = 'va-topics-wrapper';
    const topicsLabel = document.createElement('label');
    topicsLabel.textContent = 'Topics';
    const topicsMulti = document.createElement('div');
    topicsMulti.className = 'multi-text-input';
    topicsMulti.dataset.isVaTopic = 'true';
    const topicsInput = document.createElement('input');
    topicsInput.type = 'text';
    topicsInput.placeholder = 'Add & press Enter...';
    topicsMulti.appendChild(topicsInput);
    topicsWrapper.append(topicsLabel, topicsMulti);

    group.append(removeBtn, grid, topicsWrapper);
    container.appendChild(group);

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

const showSpinnerMessage = (container, messageText = '') => {
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    if (messageText) {
        const msg = document.createElement('p');
        msg.className = 'text-center';
        msg.textContent = messageText;
        container.replaceChildren(spinner, msg);
    } else {
        container.replaceChildren(spinner);
    }
};

const showParagraphMessage = (container, messageText, className = '') => {
    const p = document.createElement('p');
    if (className) p.className = className;
    p.textContent = messageText;
    container.replaceChildren(p);
};

const promptForApiKey = () => {
    if (!elements.apiKeyModal || !elements.apiKeyInput) {
        return Promise.resolve(null);
    }
    if (pendingApiKeyPrompt) {
        return pendingApiKeyPrompt;
    }
    pendingApiKeyPrompt = new Promise((resolve) => {
        elements.apiKeyInput.value = '';
        elements.apiKeyModal.classList.add('is-active');
        elements.apiKeyInput.focus();

        const cleanup = () => {
            elements.apiKeyModal.classList.remove('is-active');
            elements.submitApiKeyBtn.removeEventListener('click', onSubmit);
            elements.cancelApiKeyBtn.removeEventListener('click', onCancel);
            elements.apiKeyInput.removeEventListener('keydown', onKeyDown);
            pendingApiKeyPrompt = null;
        };

        const onSubmit = () => {
            const entered = elements.apiKeyInput.value.trim();
            elements.apiKeyInput.value = '';
            cleanup();
            if (entered) {
                runtimeApiKey = entered;
                resolve(entered);
            } else {
                resolve(null);
            }
        };

        const onCancel = () => {
            elements.apiKeyInput.value = '';
            cleanup();
            resolve(null);
        };

        const onKeyDown = (ev) => {
            if (ev.key === 'Enter') {
                ev.preventDefault();
                onSubmit();
            } else if (ev.key === 'Escape') {
                ev.preventDefault();
                onCancel();
            }
        };

        elements.submitApiKeyBtn.addEventListener('click', onSubmit);
        elements.cancelApiKeyBtn.addEventListener('click', onCancel);
        elements.apiKeyInput.addEventListener('keydown', onKeyDown);
    });
    return pendingApiKeyPrompt;
};

const showConfirmDialog = (titleText, messageText) => {
    if (!elements.confirmModal) {
        return Promise.resolve(false);
    }
    return new Promise((resolve) => {
        elements.confirmModalTitle.textContent = titleText;
        elements.confirmModalMessage.textContent = messageText;
        elements.confirmModal.classList.add('is-active');

        const cleanup = () => {
            elements.confirmModal.classList.remove('is-active');
            elements.acceptConfirmBtn.removeEventListener('click', onAccept);
            elements.cancelConfirmBtn.removeEventListener('click', onCancel);
        };

        const onAccept = () => {
            cleanup();
            resolve(true);
        };
        const onCancel = () => {
            cleanup();
            resolve(false);
        };

        elements.acceptConfirmBtn.addEventListener('click', onAccept);
        elements.cancelConfirmBtn.addEventListener('click', onCancel);
    });
};

async function apiFetch(url, options = {}) {
    const buildInit = () => {
        const headers = new Headers(options.headers || {});
        if (runtimeApiKey) {
            headers.set('X-API-Key', runtimeApiKey);
        }
        return { ...options, headers };
    };

    let response = await fetch(url, buildInit());
    if (response.status === 401) {
        runtimeApiKey = '';
        const enteredKey = await promptForApiKey();
        if (enteredKey) {
            response = await fetch(url, buildInit());
        }
    }
    return response;
}

const populateForm = (form, data) => {
    const prefix = form.id.includes('add') ? 'add-' : 'edit-';
    const get = (obj, path, def = '') => {
        const value = path.split('.').reduce((o, k) => (o || {})[k], obj);
        return value !== null && value !== undefined ? value : def;
    };

    form.querySelector(`#${prefix}display_name`).value = get(data, 'display_name');
    form.querySelector(`#${prefix}project_id`).value = get(data, 'project_id');
    form.querySelector(`#${prefix}project_number`).value = get(data, 'project_number');
    form.querySelector(`#${prefix}location`).value = get(data, 'location', 'us-central1');
    form.querySelector(`#${prefix}buckets_audios`).value = get(data, 'buckets.audios');
    form.querySelector(`#${prefix}buckets_transcripts`).value = get(data, 'buckets.transcripts');
    form.querySelector(`#${prefix}buckets_metadata`).value = get(data, 'buckets.metadata');
    form.querySelector(`#${prefix}gen_model`).value = get(data, 'generation_profile.model', 'gemini-2.5-pro');
    form.querySelector(`#${prefix}gen_company_name`).value = get(data, 'generation_profile.company_name');

    if (form.id === 'editProjectForm') {
        document.getElementById('edit-original-project-id').value = get(data, 'project_id');
        document.getElementById('edit-original-display-name').value = get(data, 'display_name');
    }

    const theme = get(data, 'generation_profile.theme', ['Telecommunications']);
    form.querySelector(`#${prefix}gen_theme`).value = Array.isArray(theme) && theme.length > 0
        ? theme[0]
        : (typeof theme === 'string' ? theme : 'Telecommunications');

    const lang = get(data, 'generation_profile.language', ['en-US']);
    form.querySelector(`#${prefix}gen_language`).value = Array.isArray(lang) && lang.length > 0
        ? lang[0]
        : (typeof lang === 'string' ? lang : 'en-US');

    const environments = get(data, 'environments', []);
    const envName = (form.id === 'projectForm') ? 'environments' : `${prefix}environments`;
    form.querySelectorAll(`input[name="${envName}"]`).forEach((checkbox) => {
        checkbox.checked = environments.includes(checkbox.value);
    });

    const sentimentJourneys = get(data, 'generation_profile.sentiment_journeys', []);
    const sjName = (form.id === 'projectForm') ? 'gen_sentiment_journeys' : `${prefix}gen_sentiment_journeys`;
    form.querySelectorAll(`input[name="${sjName}"]`).forEach((checkbox) => {
        checkbox.checked = sentimentJourneys.includes(checkbox.value);
    });

    const tagFields = {
        gen_topics: get(data, 'generation_profile.topics', []),
        gen_prompt_hint: get(data, 'generation_profile.prompt_hint', []),
    };
    for (const [key, values] of Object.entries(tagFields)) {
        const container = form.querySelector(`.multi-text-input[data-target-id="${prefix}${key}"]`);
        if (container) {
            container.querySelectorAll('.tag').forEach((t) => t.remove());
            (Array.isArray(values) ? values : []).forEach((val) => {
                container.insertBefore(createTag(String(val)), container.querySelector('input'));
            });
        }
    }

    const setRangeSliderValue = (key, values) => {
        const minInput = form.querySelector(`#${prefix}${key}_min`);
        const maxInput = form.querySelector(`#${prefix}${key}_max`);
        if (minInput && maxInput && values?.length >= 2) {
            minInput.value = values[0];
            maxInput.value = values[1];
            minInput.dispatchEvent(new Event('input'));
            maxInput.dispatchEvent(new Event('input'));
        }
    };

    const setSingleSliderValue = (key, value) => {
        const targetId = `${prefix}${key}`;
        const input = form.querySelector(`#${targetId}`);
        const checkbox = form.querySelector(`input[data-controls-slider="${targetId}"]`);
        const container = input ? input.closest('.slider-container') : null;

        if (checkbox && container) {
            const numericValue = parseFloat(value);
            if (!Number.isNaN(numericValue) && numericValue > 0) {
                checkbox.checked = true;
                container.classList.remove('is-hidden');
                input.value = numericValue;
            } else {
                checkbox.checked = false;
                container.classList.add('is-hidden');
                input.value = container.dataset.start;
            }
            if (input) input.dispatchEvent(new Event('input'));
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

    setSingleSliderValue('max_conversations_per_run_audio', get(data, 'generation_profile.max_conversations_per_run.audio'));
    setSingleSliderValue('max_conversations_per_run_chat', get(data, 'generation_profile.max_conversations_per_run.chat'));
    setSingleSliderValue('max_conversations_per_run_agentic', get(data, 'generation_profile.max_conversations_per_run.agentic'));

    const vaContainerId = `${prefix.replace(/-/g, '_')}virtual_agents_container`;
    const vaContainer = document.getElementById(vaContainerId);
    if (vaContainer) {
        vaContainer.replaceChildren();
        (get(data, 'virtual_agents', []) || []).forEach((agentData) => {
            const group = addVirtualAgentFields(vaContainerId, prefix);
            if (!group) return;
            group.querySelector('.va-agent').value = get(agentData, 'agent');
            group.querySelector('.va-conversation_profile').value = get(agentData, 'conversation_profile');
            group.querySelector('.va-location').value = get(agentData, 'location', 'global');
            group.querySelector('.va-type').value = get(agentData, 'type', 'deterministic');
            group.querySelector('.va-environment').value = get(agentData, 'environment', 'prod');
            const topicContainer = group.querySelector('.multi-text-input[data-is-va-topic]');
            (get(agentData, 'topics', []) || []).forEach((topic) => {
                topicContainer.insertBefore(createTag(String(topic)), topicContainer.querySelector('input'));
            });
        });
    }
};

const renderConfigList = () => {
    elements.projectListContainer.replaceChildren();

    if (configList.length === 0) {
        const card = document.createElement('div');
        card.className = 'card empty-state';
        const heading = document.createElement('h3');
        heading.textContent = 'Empty Configuration';
        const desc = document.createElement('p');
        desc.textContent = 'No configurations found. Add one using the form.';
        card.append(heading, desc);
        elements.projectListContainer.appendChild(card);
    } else {
        configList.forEach((p, i) => {
            const detailsEl = document.createElement('details');
            detailsEl.className = 'project-item';

            const summaryEl = document.createElement('summary');
            const headerDiv = document.createElement('div');
            headerDiv.className = 'project-item-header';

            const heading = document.createElement('h3');
            const chip = document.createElement('span');
            chip.className = 'project-id-chip';
            chip.textContent = p.project_id || '';
            heading.append(document.createTextNode(p.display_name || ''), chip);

            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'project-item-actions';

            const editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'btn btn-primary';
            editBtn.textContent = 'Edit';
            editBtn.addEventListener('click', (ev) => {
                ev.stopPropagation();
                ev.preventDefault();
                handleOpenEditModal(i);
            });
            actionsDiv.appendChild(editBtn);

            headerDiv.append(heading, actionsDiv);
            summaryEl.appendChild(headerDiv);

            const pre = document.createElement('pre');
            pre.textContent = JSON.stringify(
                p,
                (key, value) => (key === 'display_name' ? undefined : value),
                2
            );

            detailsEl.append(summaryEl, pre);
            elements.projectListContainer.appendChild(detailsEl);
        });
    }

    const summaryList = document.createElement('ul');
    const summaryItem = document.createElement('li');
    const summaryStrong = document.createElement('strong');
    summaryStrong.textContent = 'Total Demo Projects:';
    const summarySpan = document.createElement('span');
    summarySpan.className = 'stat-value';
    summarySpan.textContent = String(configList.length);
    summaryItem.append(summaryStrong, document.createTextNode(' '), summarySpan);
    summaryList.appendChild(summaryItem);
    elements.projectSummaryContainer.replaceChildren(summaryList);
};

const createDeltaElement = (delta, hasOldStats) => {
    if (!hasOldStats || delta === 0) return null;
    const sign = delta > 0 ? '+' : '';
    const span = document.createElement('span');
    span.className = `delta ${delta > 0 ? 'positive' : 'negative'}`;
    span.textContent = `(${sign}${delta.toLocaleString()})`;
    return span;
};

const createStatList = (totalValue, deltaEl) => {
    const ul = document.createElement('ul');
    const li = document.createElement('li');
    const labelSpan = document.createElement('span');
    labelSpan.textContent = 'Total Conversations';

    const valContainer = document.createElement('div');
    const valSpan = document.createElement('span');
    valSpan.className = 'stat-value';
    valSpan.textContent = totalValue.toLocaleString();
    valContainer.appendChild(valSpan);
    if (deltaEl) {
        valContainer.appendChild(deltaEl);
    }

    li.append(labelSpan, valContainer);
    ul.appendChild(li);
    return ul;
};

const renderConversationStats = (statsData, oldStatsData = null) => {
    const summaryContainer = elements.conversationSummaryContainer;
    const detailsContainer = elements.conversationDetailsContainer;
    const safeStats = statsData || {};
    const projects = safeStats.projects || {};
    const oldProjects = oldStatsData ? oldStatsData.projects || {} : {};
    const hasOldStats = Boolean(oldStatsData && Object.keys(oldProjects).length > 0);
    const lastRun = safeStats.last_run_utc;

    summaryContainer.replaceChildren();
    detailsContainer.replaceChildren();

    if (configList.length > 0 && Object.keys(projects).length === 0) {
        showParagraphMessage(
            detailsContainer,
            'No conversation data found. Click the refresh icon to perform an initial count.'
        );
        return;
    }
    if (configList.length === 0) {
        showParagraphMessage(
            detailsContainer,
            'No projects configured. Click "New Configuration" to add one.'
        );
        return;
    }

    const sortedProjectIds = Object.keys(projects).sort();
    sortedProjectIds.forEach((projectId) => {
        const projectStats = projects[projectId] || {};
        const newTotal = Number(projectStats.total) || 0;
        const oldTotal = oldProjects[projectId] ? Number(oldProjects[projectId].total) || 0 : 0;
        const delta = newTotal - oldTotal;

        const h4 = document.createElement('h4');
        h4.textContent = projectId;
        const ul = createStatList(newTotal, createDeltaElement(delta, hasOldStats));
        detailsContainer.append(h4, ul);
    });

    if (lastRun) {
        const parsedDate = new Date(lastRun);
        if (!Number.isNaN(parsedDate.getTime())) {
            const lastUpdated = document.createElement('p');
            lastUpdated.className = 'stats-last-updated';
            lastUpdated.textContent = `Last updated: ${parsedDate.toLocaleString()}`;
            detailsContainer.appendChild(lastUpdated);
        }
    }

    let grandTotal = 0;
    Object.values(projects).forEach((p) => {
        grandTotal += Number((p || {}).total) || 0;
    });

    let oldGrandTotal = 0;
    Object.values(oldProjects).forEach((p) => {
        oldGrandTotal += Number((p || {}).total) || 0;
    });

    const grandDelta = grandTotal - oldGrandTotal;
    const summaryHeading = document.createElement('h4');
    summaryHeading.textContent = 'Overall Summary';
    const summaryUl = createStatList(grandTotal, createDeltaElement(grandDelta, hasOldStats));
    summaryContainer.append(summaryHeading, summaryUl);
};

const resetForm = (formElement, containerId) => {
    formElement.reset();
    const vaContainer = document.getElementById(containerId);
    if (vaContainer) {
        vaContainer.replaceChildren();
    }

    formElement.querySelectorAll('.slider-container').forEach((c) => {
        const checkbox = formElement.querySelector(
            `input[data-controls-slider="${c.dataset.targetId}"]`
        );
        if (checkbox) {
            c.classList.add('is-hidden');
            checkbox.checked = false;
        }
    });

    initializeSliders(formElement);
    formElement.querySelectorAll('.multi-text-input .tag').forEach((t) => t.remove());
    formElement.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));
};

const renderRawJsonViewer = (rawText) => {
    currentRawJson = String(rawText ?? '');
    const wrapper = document.createElement('div');
    wrapper.className = 'json-code-viewer';
    currentRawJson.split('\n').forEach((lineText, idx) => {
        const row = document.createElement('div');
        row.className = 'json-code-line';
        const lineNum = document.createElement('span');
        lineNum.className = 'json-line-num';
        lineNum.textContent = String(idx + 1);
        const lineBody = document.createElement('span');
        lineBody.className = 'json-line-text';
        lineBody.textContent = lineText;
        row.append(lineNum, lineBody);
        wrapper.appendChild(row);
    });
    elements.jsonViewerContainer.replaceChildren(wrapper);
};

const openViewModal = async () => {
    try {
        const response = await apiFetch(`${API_URL}/configurations/raw`);
        if (!response.ok) throw new Error('Could not fetch raw config.');
        const rawText = await response.text();
        renderRawJsonViewer(rawText);
    } catch (err) {
        showToast(`Error fetching raw config: ${err.message}`, 'error');
        renderRawJsonViewer('// Could not load configuration');
    }
    elements.copyJsonBtn.textContent = 'Copy';
    elements.jsonModal.classList.add('is-active');
};

const closeViewModal = () => elements.jsonModal.classList.remove('is-active');
const openAddModal = () => {
    resetForm(elements.addProjectForm, 'modal_virtual_agents_container');
    elements.addProjectModal.classList.add('is-active');
};
const closeAddModal = () => elements.addProjectModal.classList.remove('is-active');

const handleOpenEditModal = (index) => {
    const configData = configList[index];
    if (!configData) return;
    elements.editProjectIndex.value = index;
    document.getElementById('edit-project-title').textContent = `Edit: ${configData.display_name}`;

    resetForm(elements.editProjectForm, 'edit_virtual_agents_container');
    populateForm(elements.editProjectForm, configData);
    elements.editProjectModal.classList.add('is-active');
};
const closeEditModal = () => elements.editProjectModal.classList.remove('is-active');

// --- JS API ---
async function loadConfigs() {
    showSpinnerMessage(elements.projectListContainer);
    try {
        const response = await apiFetch(`${API_URL}/configurations`);
        if (!response.ok) throw new Error(`Failed to load config file (${response.status})`);
        const data = await response.json();
        configList = Array.isArray(data.configurations) ? data.configurations : [];
        renderConfigList();
        showToast('Configuration loaded successfully.', 'success');
    } catch (error) {
        showToast(`Could not load configuration: ${error.message}`, 'error');
        showParagraphMessage(
            elements.projectListContainer,
            'Could not connect to the backend or load the configuration file.'
        );
    }
}

async function saveSingleConfig(action, configData, originalProjectId = null, originalDisplayName = null) {
    showToast('Saving changes...', 'success');
    try {
        const payload = {
            action,
            configuration: configData,
            original_project_id: originalProjectId,
            original_display_name: originalDisplayName,
        };

        const response = await apiFetch(`${API_URL}/configurations/single`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            let errorDetail = 'Unknown error';
            try {
                const errorData = await response.json();
                errorDetail = errorData.description || errorData.error || errorDetail;
            } catch (_parseErr) {
                errorDetail = `HTTP ${response.status}`;
            }
            throw new Error(`Save failed: ${errorDetail}`);
        }

        showToast('Changes saved successfully!', 'success');
        await loadConfigs();
        return true;
    } catch (error) {
        showToast(`Error saving config: ${error.message}`, 'error');
        return false;
    }
}

async function refreshConversationStats(isInitialLoad = false) {
    const loadingText = isInitialLoad
        ? 'Loading and refreshing stats...'
        : 'Refreshing stats...';
    showSpinnerMessage(elements.conversationDetailsContainer, loadingText);
    elements.conversationSummaryContainer.replaceChildren();
    elements.refreshStatsBtn.disabled = true;
    const icon = elements.refreshStatsBtn.querySelector('svg');
    if (icon) icon.classList.add('spinning');

    let oldStats = {};

    try {
        const oldStatsResponse = await apiFetch(`${API_URL}/conversation-counts`);
        if (oldStatsResponse.ok) {
            oldStats = await oldStatsResponse.json();
        }

        const refreshResponse = await apiFetch(`${API_URL}/conversation-counts`, {
            method: 'POST',
        });
        if (!refreshResponse.ok) {
            let errMessage = `Failed to refresh stats (${refreshResponse.status})`;
            try {
                const errorData = await refreshResponse.json();
                errMessage = errorData.description || errorData.error || errMessage;
            } catch (_parseErr) {
                // Keep generic HTTP status fallback.
            }
            throw new Error(errMessage);
        }
        const newStats = await refreshResponse.json();

        renderConversationStats(newStats.data, oldStats);
        showToast(newStats.message || 'Stats refreshed successfully!', 'success');
    } catch (error) {
        showToast(`Error refreshing stats: ${error.message}`, 'error');
        if (Object.keys(oldStats).length > 0) {
            renderConversationStats(oldStats);
        } else {
            showParagraphMessage(
                elements.conversationDetailsContainer,
                'Could not refresh stats.',
                'error'
            );
        }
    } finally {
        elements.refreshStatsBtn.disabled = false;
        if (icon) icon.classList.remove('spinning');
    }
}

// --- MAIN ---
const elements = {
    projectListContainer: document.getElementById('projectListContainer'),
    toastContainer: document.getElementById('toast-container'),
    viewRawJsonBtn: document.getElementById('viewRawJsonBtn'),
    jsonModal: document.getElementById('json-modal'),
    jsonViewerContainer: document.getElementById('json-viewer-container'),
    copyJsonBtn: document.getElementById('copyJsonBtn'),
    downloadJsonBtn: document.getElementById('downloadJsonBtn'),
    addProjectBtn: document.getElementById('addProjectBtn'),
    addNewProjectBtn: document.getElementById('addNewProjectBtn'),
    addProjectModal: document.getElementById('add-project-modal'),
    addProjectForm: document.getElementById('addProjectForm'),
    saveNewProjectBtn: document.getElementById('saveNewProjectBtn'),
    cancelAddProjectBtn: document.getElementById('cancelAddProjectBtn'),
    editProjectModal: document.getElementById('edit-project-modal'),
    editProjectForm: document.getElementById('editProjectForm'),
    editProjectIndex: document.getElementById('edit-project-index'),
    saveEditProjectBtn: document.getElementById('saveEditProjectBtn'),
    cancelEditProjectBtn: document.getElementById('cancelEditProjectBtn'),
    projectSummaryContainer: document.getElementById('project-summary-container'),
    darkModeToggle: document.getElementById('darkModeToggle'),
    conversationSummaryContainer: document.getElementById('conversation-summary-container'),
    conversationDetailsContainer: document.getElementById('conversation-details-container'),
    refreshStatsBtn: document.getElementById('refresh-stats-btn'),
    apiKeyModal: document.getElementById('api-key-modal'),
    apiKeyInput: document.getElementById('api-key-input'),
    submitApiKeyBtn: document.getElementById('submitApiKeyBtn'),
    cancelApiKeyBtn: document.getElementById('cancelApiKeyBtn'),
    confirmModal: document.getElementById('confirm-modal'),
    confirmModalTitle: document.getElementById('confirm-modal-title'),
    confirmModalMessage: document.getElementById('confirm-modal-message'),
    acceptConfirmBtn: document.getElementById('acceptConfirmBtn'),
    cancelConfirmBtn: document.getElementById('cancelConfirmBtn'),
};

const API_URL = '';
const PROJECTS_FILENAME = 'projects.json';

let configList = [];
let currentRawJson = '';

async function collectConfigData(form, containerSelector) {
    const prefix = form.id.includes('add') ? 'add-' : (form.id.includes('edit') ? 'edit-' : '');

    const requiredFields = [
        'display_name',
        'project_id',
        'project_number',
        'location',
        'buckets_audios',
        'buckets_transcripts',
        'buckets_metadata',
    ];

    let isValid = true;
    let firstInvalid = null;

    form.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));

    requiredFields.forEach((field) => {
        const input = form.querySelector(`#${prefix}${field}`);
        if (!input || !input.value.trim()) {
            isValid = false;
            if (input) input.classList.add('is-invalid');
            if (!firstInvalid) firstInvalid = input;
        }
    });

    if (!isValid) {
        showToast('Please fill in all required fields (marked with *).', 'error');
        if (firstInvalid) firstInvalid.focus();
        return null;
    }

    let displayName = form.querySelector(`#${prefix}display_name`).value.trim();
    const projectId = form.querySelector(`#${prefix}project_id`).value.trim();
    if (!displayName) {
        displayName = projectId;
    }

    const flatData = { display_name: displayName };

    form.querySelectorAll('input[type="text"], input[type="number"], select, textarea').forEach((input) => {
        if (!input.parentElement.classList.contains('multi-text-input') && !input.closest('.virtual-agent-group')) {
            const key = input.id.replace(prefix, '');
            if (key && key !== 'display_name') flatData[key] = input.value;
        }
    });

    const envName = (form.id === 'projectForm') ? 'environments' : `${prefix}environments`;
    flatData.environments = Array.from(form.querySelectorAll(`input[name="${envName}"]:checked`))
        .map((cb) => cb.value)
        .join(',');

    const sjName = (form.id === 'projectForm') ? 'gen_sentiment_journeys' : `${prefix}gen_sentiment_journeys`;
    flatData.gen_sentiment_journeys = Array.from(form.querySelectorAll(`input[name="${sjName}"]:checked`))
        .map((cb) => cb.value)
        .join(',');

    form.querySelectorAll('.multi-text-input:not([data-is-va-topic])').forEach((container) => {
        const key = container.dataset.targetId.replace(prefix, '');
        flatData[key] = Array.from(container.querySelectorAll('.tag'))
            .map((t) => (t.dataset.value || t.textContent.slice(0, -1)).trim())
            .join(',');
    });

    let hasAnyConversations = false;
    form.querySelectorAll('.slider-container').forEach((container) => {
        const key = container.dataset.targetId.replace(prefix, '');
        const checkbox = form.querySelector(`input[data-controls-slider="${container.dataset.targetId}"]`);

        if (key.startsWith('max_conversations_per_run') && checkbox && checkbox.checked) {
            hasAnyConversations = true;
        }

        if (checkbox && !checkbox.checked) {
            flatData[key] = '0';
        } else {
            const inputs = container.querySelectorAll('input[type="range"]');
            if (inputs.length > 1) {
                flatData[key] = `${inputs[0].value},${inputs[1].value}`;
            } else if (inputs.length === 1) {
                flatData[key] = inputs[0].value;
            }
        }
    });

    if (!hasAnyConversations) {
        const confirmed = await showConfirmDialog(
            'No Conversation Types Enabled',
            'You have not enabled any conversation generation (Audio, Chat, or Agentic are all unchecked). Save this configuration anyway?'
        );
        if (!confirmed) {
            return null;
        }
    }

    const virtualAgents = [];
    document.querySelectorAll(`${containerSelector} .virtual-agent-group`).forEach((group) => {
        virtualAgents.push({
            agent: group.querySelector('.va-agent').value.trim(),
            conversation_profile: group.querySelector('.va-conversation_profile').value.trim(),
            location: group.querySelector('.va-location').value.trim(),
            type: group.querySelector('.va-type').value.trim(),
            environment: group.querySelector('.va-environment').value.trim(),
            topics: Array.from(group.querySelectorAll('.multi-text-input[data-is-va-topic] .tag'))
                .map((t) => (t.dataset.value || t.textContent.slice(0, -1)).trim()),
        });
    });
    flatData.virtual_agents = virtualAgents;
    return flatData;
}

async function handleAddNewConfig() {
    const newConfigData = await collectConfigData(elements.addProjectForm, '#modal_virtual_agents_container');
    if (!newConfigData) return;

    if (configList.some((c) => c.display_name === newConfigData.display_name)) {
        showToast(`Display Name "${newConfigData.display_name}" already exists. It must be unique.`, 'error');
        return;
    }

    const success = await saveSingleConfig('add', newConfigData);
    if (success) closeAddModal();
}

async function handleSaveEditedConfig() {
    const editedConfigData = await collectConfigData(elements.editProjectForm, '#edit_virtual_agents_container');
    if (!editedConfigData) return;

    const originalProjectId = document.getElementById('edit-original-project-id').value;
    const originalDisplayName = document.getElementById('edit-original-display-name').value;
    const index = parseInt(elements.editProjectIndex.value, 10);

    if (configList.some((c, i) => i !== index && c.display_name === editedConfigData.display_name)) {
        showToast(`Display Name "${editedConfigData.display_name}" already exists. It must be unique.`, 'error');
        return;
    }

    const success = await saveSingleConfig('edit', editedConfigData, originalProjectId, originalDisplayName);
    if (success) closeEditModal();
}

async function handleSidebarAddConfig() {
    const newConfigData = await collectConfigData(document.getElementById('projectForm'), '#sidebar_virtual_agents_container');
    if (!newConfigData) return;

    if (configList.some((c) => c.display_name === newConfigData.display_name)) {
        showToast(`Display Name "${newConfigData.display_name}" already exists. It must be unique.`, 'error');
        return;
    }
    const success = await saveSingleConfig('add', newConfigData);
    if (success) resetForm(document.getElementById('projectForm'), 'sidebar_virtual_agents_container');
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

document.querySelectorAll('[data-add-va-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
        addVirtualAgentFields(btn.dataset.addVaTarget, btn.dataset.addVaPrefix || '');
    });
});

elements.copyJsonBtn.addEventListener('click', () => {
    const rawValue = currentRawJson || elements.jsonViewerContainer.textContent;
    navigator.clipboard.writeText(rawValue).then(() => {
        elements.copyJsonBtn.textContent = 'Copied!';
        setTimeout(() => { elements.copyJsonBtn.textContent = 'Copy'; }, 2000);
    }).catch(() => {
        showToast('Failed to copy JSON!', 'error');
    });
});

elements.downloadJsonBtn.addEventListener('click', () => {
    const rawValue = currentRawJson || elements.jsonViewerContainer.textContent;
    const blob = new Blob([rawValue], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = PROJECTS_FILENAME;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

[
    elements.jsonModal,
    elements.addProjectModal,
    elements.editProjectModal,
    elements.apiKeyModal,
    elements.confirmModal,
].filter(Boolean).forEach((modal) => {
    const bg = modal.querySelector('.modal-background');
    const closeBtn = modal.querySelector('.modal-close');
    if (bg) {
        bg.addEventListener('click', () => {
            if (modal === elements.apiKeyModal && elements.cancelApiKeyBtn) {
                elements.cancelApiKeyBtn.click();
            } else if (modal === elements.confirmModal && elements.cancelConfirmBtn) {
                elements.cancelConfirmBtn.click();
            } else {
                modal.classList.remove('is-active');
            }
        });
    }
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            if (modal === elements.apiKeyModal && elements.cancelApiKeyBtn) {
                elements.cancelApiKeyBtn.click();
            } else if (modal === elements.confirmModal && elements.cancelConfirmBtn) {
                elements.cancelConfirmBtn.click();
            } else {
                modal.classList.remove('is-active');
            }
        });
    }
});
elements.cancelAddProjectBtn.addEventListener('click', closeAddModal);
elements.cancelEditProjectBtn.addEventListener('click', closeEditModal);

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        [elements.jsonModal, elements.addProjectModal, elements.editProjectModal]
            .filter(Boolean)
            .forEach((m) => m.classList.remove('is-active'));
        if (elements.confirmModal && elements.confirmModal.classList.contains('is-active')) {
            elements.cancelConfirmBtn.click();
        }
    }
});

document.addEventListener('input', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('is-invalid')) {
        e.target.classList.remove('is-invalid');
    }
});

document.addEventListener('DOMContentLoaded', async () => {
    const regionTemplate = document.getElementById('gcp-regions-template');
    if (regionTemplate && regionTemplate.content) {
        document.querySelectorAll('select[id*="location"]').forEach((sel) => {
            sel.replaceChildren(regionTemplate.content.cloneNode(true));
        });
    }
    initializeTagInputs(document);
    initializeSliders(document);
    setupCheckboxSliderToggles();

    const savedDarkMode = localStorage.getItem('darkMode');
    if (savedDarkMode === 'disabled') {
        elements.darkModeToggle.checked = false;
        applyDarkMode(false);
    } else {
        elements.darkModeToggle.checked = true;
        applyDarkMode(true);
    }

    await loadConfigs();
    await refreshConversationStats(true);
});
})();
