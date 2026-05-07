// static/js/main.js
let currentRightTab = 'character';
// Tab Switching
function showRightTab(tabName) {
    // Hide ALL tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
        tab.style.display = 'none';
    });
    // Deactivate all buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    // Show selected tab
    const selectedTab = document.getElementById(`right-${tabName}`);
    if (selectedTab) {
        selectedTab.classList.add('active');
        selectedTab.style.display = 'block';
    }
    // Activate button
    const activeButton = Array.from(document.querySelectorAll('.tab-button'))
        .find(btn => btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(tabName));
    
    if (activeButton) activeButton.classList.add('active');
    currentRightTab = tabName;
    // Load content if needed
    if (tabName === 'inventory') {
        loadInventory();
    }
    if (tabName === 'party') {
    loadParty();
    }
    if (tabName === 'quests') {
        loadQuests();
    }
}
function scrollToBottom() {
    const output = document.getElementById('dmOutput');
    if (output) {
        output.scrollTop = output.scrollHeight;
    }
}
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    }[ch]));
}
function formatItemNumber(value) {
    if (value === undefined || value === null || value === '') return '';
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return escapeHtml(value);
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2).replace(/\.?0+$/, '');
}
// Make sure inventory loads when tab is clicked
async function loadInventory() {
    const grid = document.getElementById('inventoryGrid');
    grid.innerHTML = '<p>Loading inventory...</p>';
    try {
        const res = await fetch('/api/inventory');
        const payload = await res.json();
        const inventory = payload.items || payload || {};
        const currency = payload.currency || {display: '0 copper', denominations: {}};
        grid.innerHTML = '';
        const currencyBar = document.createElement('div');
        currencyBar.className = 'currency-bar';
        const denominations = currency.denominations || {};
        currencyBar.innerHTML = `
            <div class="currency-label">Currency</div>
            <div class="currency-total">${escapeHtml(currency.display || '0 copper')}</div>
            <div class="currency-denoms">
                <span>PP ${escapeHtml(denominations.platinum || 0)}</span>
                <span>GP ${escapeHtml(denominations.gold || 0)}</span>
                <span>SP ${escapeHtml(denominations.silver || 0)}</span>
                <span>CP ${escapeHtml(denominations.copper || 0)}</span>
            </div>
        `;
        grid.appendChild(currencyBar);
        if (Object.keys(inventory || {}).length === 0) {
            const empty = document.createElement('p');
            empty.textContent = 'Your inventory is empty.';
            grid.appendChild(empty);
            return;
        }
        Object.values(inventory).forEach(item => {
            const div = document.createElement('div');
            div.className = 'inventory-item';
            const name = item.name || item.archetype || item.type || item.id || 'Unknown Item';
            const quantity = item.qty ?? item.quantity;
            const details = [
                item.archetype || item.type,
                item.condition,
                Array.isArray(item.tags) && item.tags.length ? item.tags.join(', ') : ''
            ].filter(Boolean).map(escapeHtml).join(' • ');
            const weaponStats = ['damage', 'speed', 'range', 'weight', 'price']
                .filter(key => item[key] !== undefined && item[key] !== null)
                .map(key => `${key}: ${formatItemNumber(item[key])}`)
                .join(' • ');
            div.innerHTML = `
                <div class="item-name">${escapeHtml(name)}</div>
                <div class="item-details">
                    ${quantity ? `${escapeHtml(quantity)}× ` : ''}${details}
                    ${weaponStats ? `<br><small>${weaponStats}</small>` : ''}
                    ${item.description ? `<br><small>${escapeHtml(item.description)}</small>` : ''}
                </div>
            `;
            grid.appendChild(div);
        });
    } catch (e) {
        console.error(e);
        grid.innerHTML = '<p>Could not load inventory.</p>';
    }
}
async function loadQuests() {
    const questList = document.getElementById('questList');
    questList.textContent = 'Loading quests...';
    try {
        const res = await fetch('/api/quests');
        const quests = await res.json();
        const flatQuests = Array.isArray(quests) ? quests.flat().filter(Boolean) : Object.values(quests || {});
        questList.innerHTML = '';
        if (flatQuests.length === 0) {
            questList.textContent = 'No quests yet.';
            return;
        }
        flatQuests.forEach(quest => {
            const item = document.createElement('div');
            item.className = 'quest-item';
            const title = document.createElement('div');
            title.className = 'quest-title';
            title.textContent = quest.title || quest.name || quest.quest_id || 'Untitled Quest';
            const details = document.createElement('div');
            details.className = 'quest-details';
            details.textContent = `${quest.status || 'active'}${quest.description ? ' - ' + quest.description : ''}`;
            item.appendChild(title);
            item.appendChild(details);
            questList.appendChild(item);
        });
    } catch (e) {
        console.error(e);
        questList.textContent = 'Could not load quests.';
    }
}
// Load main game state
async function loadGameState() {
    try {
        const res = await fetch('/api/game_state');
        const data = await res.json();
        
        const player = data.player || {};
        const identity = player.identity || {};
        const stats = player.stats || {};
        const derived = player.derived || {};
        // Status Bar
        renderOpeningScene(data);
        updateCharacterSheet(player);
    } catch (e) {
        console.error("Failed to load game state", e);
    }
}
function renderOpeningScene(gameState) {
    const output = document.getElementById('outputContent');
    if (!output) return;
    const scenario = gameState.scenario || {};
    const opening = scenario.opening_scene || {};
    const resume = gameState.resume_context || {};
    const resumeText = resume.last_dm_narrative || '';
    const sceneText = resumeText || scenario.current_scene || opening.text;
    if (!sceneText) return;
    const defaultText = 'Welcome, adventurer. What would you like to do?';
    const alreadyRendered = output.dataset.openingSceneRendered === 'true';
    if (alreadyRendered || output.textContent.trim() !== defaultText) return;
    output.textContent = '';
    appendTranscriptLine(output, 'DM', sceneText, resumeText ? 'resume-scene-line' : 'opening-scene-line');
    if (resume.last_player_input) {
        updateLastPlayerInput(resume.last_player_input);
    }
    output.dataset.openingSceneRendered = 'true';
}
// Player Character Sheet - Two Column Layout
// PLAYER CHARACTER SHEET - Single clean card layout (your mockup style)
function updateCharacterSheet(player) {
    const container = document.getElementById('characterInfo');
    if (!player) {
        container.innerHTML = '<p>No character data available.</p>';
        return;
    }

    const id = player.identity || player;
    const stats = player.stats || {};
    const skills = player.skills || {};
    const derived = player.derived || {};

    const html = `
        <div class="player-sheet">
            <div class="player-header">
                <div class="player-title">
                    <h2>${id.name || 'Aburi'}</h2>
                    <p class="subtitle">${(id.race || 'Human').toUpperCase()} • ${id.class_theme || 'Isekai Adventurer'}</p>
                    <p class="background">${id.background || 'A former database analyst pulled into Elyndor.'}</p>
                </div>
                <div class="player-portrait">
                    <img src="/static/images/${id.name}.png" 
                         onerror="this.src='/static/images/default-character.png'" 
                         alt="${id.name}">
                </div>
            </div>

            <!-- HP / MP / AC -->
            <div class="stat-grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom: 20px;">
                <div class="stat-item">
                    <div class="stat-label">HP</div>
                    <div class="stat-value">${derived.HP || 0} / ${derived.HP_max || 0}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">MP</div>
                    <div class="stat-value">${derived.MP || 0} / ${derived.MP_max || 0}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">AC</div>
                    <div class="stat-value">${derived.AC || '—'}</div>
                </div>
            </div>

            <!-- Simple Divider -->
            <div class="section-divider"></div>

            <!-- Core Attributes - 6 columns -->
            <div class="stat-grid" style="grid-template-columns: repeat(6, 1fr);">
                ${Object.entries(stats).map(([k, v]) => `
                    <div class="stat-item">
                        <div class="stat-label">${k}</div>
                        <div class="stat-value">${typeof v === 'number' ? v.toFixed(1) : v}</div>
                    </div>
                `).join('')}
            </div>

            <!-- Simple Divider -->
            <div class="section-divider"></div>

            <!-- Skills -->
            <div class="stat-grid">
                ${Object.entries(skills).map(([k, v]) => `
                    <div class="stat-item">
                        <div class="stat-label">${k}</div>
                        <span class="stat-value">${parseFloat(v || 0).toFixed(1)}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    container.innerHTML = html;
}
function appendTranscriptLine(container, speaker, text, className = '') {
    const line = document.createElement('div');  // Changed from <p> to <div> for better control
    if (className) line.className = className;

    const label = document.createElement('strong');
    label.textContent = `${speaker}: `;
    line.appendChild(label);

    // Preserve paragraphs and line breaks
    const paragraphs = text.split('\n\n');  // Split on double newlines (true paragraphs)
    
    paragraphs.forEach((para, index) => {
        if (index > 0) {
            const br = document.createElement('br');
            line.appendChild(br);
        }
        
        const paraText = document.createElement('span');
        paraText.textContent = para.trim();
        line.appendChild(paraText);
    });

    container.appendChild(line);
    scrollToBottom();
}
function updateLastPlayerInput(text) {
    const lastPlayerText = document.getElementById('lastPlayerText');
    if (lastPlayerText) {
        lastPlayerText.textContent = text || 'No action yet.';
    }
}
function setSubmitButtonBusy(button, isBusy) {
    if (!button) return;
    const icon = button.querySelector('i');
    const label = button.querySelector('span');
    button.disabled = isBusy;
    if (icon) {
        icon.className = isBusy ? 'fa-solid fa-hourglass-half' : 'fa-solid fa-arrow-right';
    }
    if (label) {
        label.textContent = isBusy ? 'Thinking...' : 'Submit';
    }
}
// Submit Action
// Submit Action - Improved with loading state + auto-scroll
async function submitAction() {
    const input = document.getElementById('playerInput');
    const output = document.getElementById('outputContent');
    const playerText = input.value.trim();

    if (!playerText || input.disabled) return;

    // Keep the DM transcript for DM narration only.
    updateLastPlayerInput(playerText);

    // Clear input
    input.value = '';

    // === LOADING STATE ===
    const submitBtn = document.getElementById('submitActionButton');

    input.disabled = true;
    setSubmitButtonBusy(submitBtn, true);

    // Add thinking indicator
    const thinkingId = 'dm-thinking';
    let thinkingDiv = document.getElementById(thinkingId);
    if (!thinkingDiv) {
        thinkingDiv = document.createElement('p');
        thinkingDiv.id = thinkingId;
        thinkingDiv.className = 'dm-message thinking';
        thinkingDiv.innerHTML = `<em>The DM is considering your actions...</em>`;
        output.appendChild(thinkingDiv);
    }

    scrollToBottom();

    try {
        const res = await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: playerText })
        });

        const result = await res.json();

        // Remove thinking indicator
        if (thinkingDiv) thinkingDiv.remove();

        if (!res.ok || result.error) {
            appendTranscriptLine(output, 'Error', result.error || `Request failed`, 'error-line');
        } else if (result.narrative) {
            appendTranscriptLine(output, 'DM', result.narrative);
        }

        // Refresh other panels
        loadGameState();

    } catch (e) {
        if (thinkingDiv) thinkingDiv.remove();
        appendTranscriptLine(output, 'Error', e.message || 'Connection error', 'error-line');
    } finally {
        // Restore UI
        input.disabled = false;
        setSubmitButtonBusy(submitBtn, false);
        input.focus();
        scrollToBottom();
    }
}
function showHelp() {
    alert("Try commands like:\n• attack goblin\n• cast fire dart\n• talk to kaelra\n• rest");
}
// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadGameState();
    const input = document.getElementById('playerInput');
    if (input) {
        input.addEventListener('keydown', event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                submitAction();
            }
        });
    }
    // Removed automatic refresh - setInterval(loadGameState, 4000);
});
// ==================== PARTY TAB ====================
async function loadParty() {
    const buttonsContainer = document.getElementById('partyButtons');
    const sheetContainer = document.getElementById('partyMemberSheet');
    
    buttonsContainer.innerHTML = '';
    sheetContainer.innerHTML = '<p>Select a party member to view details.</p>';
    try {
        const res = await fetch('/api/npcs');
        const npcs = await res.json();
        // Filter NPCs that are in the party
        const partyMembers = Object.values(npcs).filter(npc => 
            npc.party === true || 
            (npc.relationship && npc.relationship.toLowerCase() === "friend")
        );
        if (partyMembers.length === 0) {
            buttonsContainer.innerHTML = '<p>No party members yet.</p>';
            return;
        }
        partyMembers.forEach(npc => {
            const btn = document.createElement('button');
            btn.className = 'party-member-btn';
            btn.textContent = npc.name;
            btn.onclick = () => showPartyMember(npc);
            buttonsContainer.appendChild(btn);
        });
    } catch (e) {
        console.error("Failed to load party", e);
        buttonsContainer.innerHTML = '<p>Error loading party members.</p>';
    }
}
// Party Member Sheet - Same two-column layout
function showPartyMember(npc) {
    const container = document.getElementById('partyMemberSheet');
    const stats = npc.stats || {};
    const html = `
        <div class="character-sheet-grid">
            <div class="character-left">
                <div class="character-header">
                    <h2>${npc.name}</h2>
                    <p class="subtitle">${(npc.race || '').toUpperCase()} • ${npc.role || 'Companion'}</p>
                </div>
                <div class="stats-section">
                    <h3>Core Attributes</h3>
                    <div class="stat-grid">
                        ${Object.entries(stats).map(([k, v]) => `
                            <div class="stat-item"><span class="stat-label">${k}</span><span class="stat-value">${typeof v === 'number' ? v.toFixed(1) : v}</span></div>
                        `).join('')}
                    </div>
                </div>
                <div class="stats-section">
                    <h3>Status</h3>
                    <p><strong>Mood:</strong> ${npc.mood || '—'}</p>
                    <p><strong>Relationship:</strong> ${npc.relationship || '—'}</p>
                    <p><strong>Location:</strong> ${npc.location || '—'}</p>
                </div>
            </div>

            <!-- Right Column: Portrait -->
            <div class="player-portrait" id="playerPortraitContainer">
                <img id="playerPortraitImg"
                    src="/static/images/${id.name}.png"
                    alt="${id.name}"
                    style="display: none;"
                    onerror="tryNextImageFormat(this, '${id.name || 'Aburi'}')">
                <div class="image-note" id="playerPortraitNote" style="display: none;">
                    Save your character image as:<br>
                    <strong>./static/images/${id.name || 'Aburi'}.png</strong><br>
                    <small>(or .jpg, .jpeg, or .webp)</small>
                </div>
            </div>
        </div>
    `;
    container.innerHTML = html;
    if (tabName === 'quests') {
        loadQuests();
    }
}
function tryNextImageFormat(img, baseName) {
    const formats = ['.png', '.jpg', '.jpeg', '.webp'];
    let currentIndex = formats.indexOf(img.src.slice(-4).toLowerCase());
    
    // If current format failed, try the next one
    if (currentIndex < formats.length - 1) {
        const nextFormat = formats[currentIndex + 1];
        img.src = `/static/images/${baseName}${nextFormat}`;
    } else {
        // All formats failed → show the help message
        img.style.display = 'none';
        const note = document.getElementById('playerPortraitNote');
        if (note) note.style.display = 'block';
    }
}
