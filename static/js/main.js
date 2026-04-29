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
// Make sure inventory loads when tab is clicked
async function loadInventory() {
    const grid = document.getElementById('inventoryGrid');
    grid.innerHTML = '<p>Loading inventory...</p>';
    try {
        const res = await fetch('/api/inventory');
        const inventory = await res.json();
        grid.innerHTML = '';
        if (Object.keys(inventory || {}).length === 0) {
            grid.innerHTML = '<p>Your inventory is empty.</p>';
            return;
        }
        Object.values(inventory).forEach(item => {
            const div = document.createElement('div');
            div.className = 'inventory-item';
            div.innerHTML = `
                <div class="item-name">${item.name || 'Unknown Item'}</div>
                <div class="item-details">
                    ${item.quantity ? item.quantity + '× ' : ''}${item.archetype || item.type || ''}
                    ${item.description ? `<br><small>${item.description}</small>` : ''}
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
            <div class="character-portrait">
                <img src="/static/images/${npc.name}.png" 
                     onerror="this.src='/static/images/${npc.name}.jpg'; this.onerror=null;"
                     alt="${npc.name}"
                     class="character-portrait-img">
            </div>
        </div>
    `;
    container.innerHTML = html;
    if (tabName === 'quests') {
        loadQuests();
    }
}
