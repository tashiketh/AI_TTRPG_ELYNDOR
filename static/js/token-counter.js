// Token Counter for AI Usage Tracking
// Add this to your HTML: <script src="/static/js/token-counter.js"></script>

// Initialize token counter
let tokenCounter = 0;

// Add token counter to UI when page loads
document.addEventListener('DOMContentLoaded', () => {
    addTokenCounterToUI();
    resetTokenCounter(); // Start fresh each session
});

function addTokenCounterToUI() {
    // Create status bar with token counter
    const statusBar = document.createElement('div');
    statusBar.id = 'statusBar';
    statusBar.className = 'status-bar';
    statusBar.innerHTML = `
        <div class="token-counter">
            <i class="fas fa-coins"></i>
            <span id="tokenCount">0</span>
            <span class="token-label">Tokens Used</span>
        </div>
    `;
    
    // Add to top of page
    document.body.insertBefore(statusBar, document.body.firstChild);
    
    // Add CSS styles
    const style = document.createElement('style');
    style.textContent = `
        /* Token Counter Styles */
        .status-bar {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: rgba(10, 10, 18, 0.9);
            padding: 8px 20px;
            display: flex;
            justify-content: flex-end;
            z-index: 100;
            border-bottom: 1px solid #00ffaa33;
            box-sizing: border-box;
        }
        
        .token-counter {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #00ffaa;
            font-size: 0.9rem;
            padding: 4px 12px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 6px;
            transition: transform 0.2s ease;
        }
        
        .token-counter i {
            font-size: 0.9rem;
        }
        
        #tokenCount {
            font-weight: bold;
            font-family: 'Courier New', monospace;
            min-width: 40px;
            text-align: right;
        }
        
        .token-label {
            color: #aaa;
            font-size: 0.8rem;
            display: none;
        }
        
        .token-counter:hover .token-label {
            display: inline;
        }
        
        /* Pulse animation for token updates */
        @keyframes tokenPulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.15); }
            100% { transform: scale(1); }
        }
        
        .token-counter.pulse {
            animation: tokenPulse 0.3s ease;
        }
    `;
    
    document.head.appendChild(style);
}

/**
 * Update the token counter and add visual feedback
 * @param {number} tokensUsed - Number of tokens used in this API call
 */
function updateTokenCounter(tokensUsed) {
    tokenCounter += tokensUsed;
    const counterElement = document.getElementById('tokenCount');
    
    if (counterElement) {
        counterElement.textContent = tokenCounter.toLocaleString();
        
        // Add pulse animation
        const counterParent = counterElement.parentElement;
        counterParent.classList.add('pulse');
        setTimeout(() => {
            counterParent.classList.remove('pulse');
        }, 300);
    }
}

/**
 * Reset the token counter (called when game loads)
 */
function resetTokenCounter() {
    tokenCounter = 0;
    const counterElement = document.getElementById('tokenCount');
    if (counterElement) {
        counterElement.textContent = '0';
    }
}

/**
 * Get current token count
 * @returns {number} Current token count
 */
function getTokenCount() {
    return tokenCounter;
}

// Export functions if using modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        updateTokenCounter,
        resetTokenCounter,
        getTokenCount
    };
}