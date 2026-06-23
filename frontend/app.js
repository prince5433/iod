/**
 * Transaction & Ranking System — Frontend Application Logic
 * 
 * Handles:
 * - Tab navigation
 * - API calls to the backend
 * - Dynamic DOM rendering
 * - Toast notifications
 * - Idempotency key generation
 * - Client-side input validation
 */

// ─── Configuration ───────────────────────────────────────────────
const API_BASE = '/api';

// ─── Utility: Generate UUID v4 ───────────────────────────────────
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

// ─── Utility: Format Currency ────────────────────────────────────
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 2,
    }).format(amount);
}

// ─── Utility: Get avatar color from string ───────────────────────
function getAvatarColor(str) {
    const colors = [
        'linear-gradient(135deg, #3b82f6, #1d4ed8)',
        'linear-gradient(135deg, #8b5cf6, #6d28d9)',
        'linear-gradient(135deg, #06b6d4, #0891b2)',
        'linear-gradient(135deg, #10b981, #059669)',
        'linear-gradient(135deg, #f59e0b, #d97706)',
        'linear-gradient(135deg, #f43f5e, #e11d48)',
    ];
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
}

// ─── Utility: Get initials from name ─────────────────────────────
function getInitials(name) {
    return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

// ─── Utility: Factor color class ─────────────────────────────────
function factorClass(value) {
    if (value >= 0.7) return 'high';
    if (value >= 0.4) return 'medium';
    return 'low';
}


// ═══════════════════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════════════

function showToast(type, title, message, duration = 4000) {
    const container = document.getElementById('toast-container');
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            ${message ? `<div class="toast-message">${message}</div>` : ''}
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// ═══════════════════════════════════════════════════════════════════
// TAB NAVIGATION
// ═══════════════════════════════════════════════════════════════════

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.remove('active');
        tab.setAttribute('aria-selected', 'false');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.querySelector(`[data-tab="${tabName}"]`).setAttribute('aria-selected', 'true');
    
    // Update panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.getElementById(`panel-${tabName}`).classList.add('active');
    
    // Load data for the activated tab
    if (tabName === 'summary') {
        loadUsers();
    } else if (tabName === 'ranking') {
        fetchRanking();
    }
}


// ═══════════════════════════════════════════════════════════════════
// IDEMPOTENCY KEY MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

function regenerateKey() {
    document.getElementById('txn-idempotency-key').value = generateUUID();
}

// Generate initial key on page load
document.addEventListener('DOMContentLoaded', () => {
    regenerateKey();
});


// ═══════════════════════════════════════════════════════════════════
// SEED DATA
// ═══════════════════════════════════════════════════════════════════

async function seedData() {
    const btn = document.getElementById('btn-seed');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Seeding...';

    try {
        const res = await fetch(`${API_BASE}/seed`, { method: 'POST' });
        const data = await res.json();

        if (res.ok) {
            showToast('success', 'Demo Data Loaded', 
                `${data.users_created} users, ${data.transactions_created} transactions`);
            document.getElementById('seed-section').style.display = 'none';
            // Auto-load ranking
            fetchRanking();
        } else {
            showToast('error', 'Seeding Failed', data.detail || 'Unknown error');
        }
    } catch (err) {
        showToast('error', 'Network Error', err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🌱 Load Demo Data';
    }
}


// ═══════════════════════════════════════════════════════════════════
// TRANSACTION SUBMISSION
// ═══════════════════════════════════════════════════════════════════

async function submitTransaction(event) {
    event.preventDefault();
    
    const btn = document.getElementById('btn-submit-txn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Processing...';

    const payload = {
        user_id: document.getElementById('txn-user-id').value.trim(),
        type: document.getElementById('txn-type').value,
        amount: parseFloat(document.getElementById('txn-amount').value),
        description: document.getElementById('txn-description').value.trim(),
        idempotency_key: document.getElementById('txn-idempotency-key').value.trim(),
    };

    // Client-side validation
    if (!payload.user_id) {
        showToast('warning', 'Validation Error', 'User ID is required');
        btn.disabled = false;
        btn.innerHTML = 'Submit Transaction';
        return;
    }

    if (payload.amount <= 0 || payload.amount > 1000000) {
        showToast('warning', 'Validation Error', 'Amount must be between ₹0.01 and ₹10,00,000');
        btn.disabled = false;
        btn.innerHTML = 'Submit Transaction';
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/transaction`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (res.ok || res.status === 200) {
            renderTransactionResult(data, res.status);
            
            if (data.is_duplicate) {
                showToast('warning', 'Duplicate Detected', 
                    'This idempotency key was already used. Original result returned.');
            } else {
                showToast('success', 'Transaction Created', 
                    `${payload.type === 'credit' ? 'Credited' : 'Debited'} ${formatCurrency(payload.amount)}`);
                // Generate new key for next transaction
                regenerateKey();
            }
        } else if (res.status === 429) {
            showToast('error', 'Rate Limited', data.detail);
            renderErrorResult(data.detail);
        } else {
            showToast('error', 'Transaction Failed', data.detail || 'Unknown error');
            renderErrorResult(data.detail || 'Unknown error');
        }
    } catch (err) {
        showToast('error', 'Network Error', err.message);
        renderErrorResult(`Network error: ${err.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Submit Transaction';
    }
}

function renderTransactionResult(data, statusCode) {
    const container = document.getElementById('transaction-result');
    const isDuplicate = data.is_duplicate;
    const typeEmoji = data.type === 'credit' ? '💚' : '🔴';
    
    container.innerHTML = `
        <div class="result-card ${isDuplicate ? 'duplicate' : ''}">
            <div class="result-header">
                ${isDuplicate ? '⚠️ Duplicate Request — Cached Result Returned' : '✅ Transaction Processed Successfully'}
            </div>
            <div class="result-details">
                <span class="result-key">Transaction ID</span>
                <span class="result-value">${data.id}</span>
                
                <span class="result-key">User</span>
                <span class="result-value">${data.user_id}</span>
                
                <span class="result-key">Type</span>
                <span class="result-value">${typeEmoji} ${data.type.toUpperCase()}</span>
                
                <span class="result-key">Amount</span>
                <span class="result-value">${formatCurrency(data.amount)}</span>
                
                <span class="result-key">Description</span>
                <span class="result-value">${data.description || '—'}</span>
                
                <span class="result-key">Idempotency Key</span>
                <span class="result-value" style="font-size:0.7rem;word-break:break-all;">${data.idempotency_key}</span>
                
                <span class="result-key">Status</span>
                <span class="result-value">${data.status}</span>
                
                <span class="result-key">HTTP Status</span>
                <span class="result-value">${statusCode} ${statusCode === 201 ? '(Created)' : '(Cached)'}</span>
                
                <span class="result-key">Timestamp</span>
                <span class="result-value">${new Date(data.created_at).toLocaleString()}</span>
            </div>
        </div>
    `;
}

function renderErrorResult(message) {
    const container = document.getElementById('transaction-result');
    container.innerHTML = `
        <div class="result-card error">
            <div class="result-header">❌ Transaction Failed</div>
            <p style="color: var(--text-secondary); font-size: 0.875rem;">${message}</p>
        </div>
    `;
}

function clearResult() {
    document.getElementById('transaction-result').innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">📄</div>
            <p class="empty-state-title">No transaction submitted yet</p>
            <p class="empty-state-desc">Submit a transaction using the form to see the result here.</p>
        </div>
    `;
}


// ═══════════════════════════════════════════════════════════════════
// USER SUMMARY
// ═══════════════════════════════════════════════════════════════════

async function loadUsers() {
    const grid = document.getElementById('user-select-grid');
    try {
        const res = await fetch(`${API_BASE}/users`);
        const data = await res.json();

        if (data.users && data.users.length > 0) {
            grid.innerHTML = data.users.map(u => `
                <div class="user-select-card" onclick="selectUser('${u.id}')" id="user-card-${u.id}">
                    <div class="user-select-name">${u.name}</div>
                    <div class="user-select-id">${u.id}</div>
                </div>
            `).join('');
        } else {
            grid.innerHTML = '<p style="color: var(--text-muted); font-size: 0.875rem; grid-column: 1 / -1;">No users found. Seed demo data first.</p>';
        }
    } catch (err) {
        grid.innerHTML = '<p style="color: var(--accent-rose); font-size: 0.875rem;">Failed to load users</p>';
    }
}

function selectUser(userId) {
    document.getElementById('summary-user-id').value = userId;
    // Highlight selected card
    document.querySelectorAll('.user-select-card').forEach(c => c.classList.remove('active'));
    const card = document.getElementById(`user-card-${userId}`);
    if (card) card.classList.add('active');
    fetchSummary();
}

async function fetchSummary() {
    const userId = document.getElementById('summary-user-id').value.trim();
    if (!userId) {
        showToast('warning', 'Missing Input', 'Please enter a user ID');
        return;
    }

    const container = document.getElementById('summary-result');
    container.innerHTML = '<div class="empty-state"><div class="spinner" style="margin:0 auto;width:32px;height:32px;border-width:3px;"></div><p style="margin-top:1rem;color:var(--text-muted);">Loading...</p></div>';

    try {
        const res = await fetch(`${API_BASE}/summary/${encodeURIComponent(userId)}`);
        const data = await res.json();

        if (res.ok) {
            renderSummary(data);
        } else {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🚫</div>
                    <p class="empty-state-title">${data.detail || 'User not found'}</p>
                    <p class="empty-state-desc">Make sure the user ID is correct, or create a new transaction for this user.</p>
                </div>
            `;
        }
    } catch (err) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">⚠️</div>
                <p class="empty-state-title">Connection Error</p>
                <p class="empty-state-desc">${err.message}</p>
            </div>
        `;
    }
}

function renderSummary(data) {
    const container = document.getElementById('summary-result');
    const balanceClass = data.balance >= 0 ? 'positive' : 'negative';
    
    container.innerHTML = `
        <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem;">
            <div class="user-avatar" style="width:48px;height:48px;font-size:1rem;background:${getAvatarColor(data.user_id)}">
                ${getInitials(data.user_name)}
            </div>
            <div>
                <div style="font-size:1.25rem;font-weight:700;color:var(--text-primary)">${data.user_name}</div>
                <div style="font-size:0.8125rem;color:var(--text-muted);font-family:'JetBrains Mono',monospace">${data.user_id}</div>
            </div>
        </div>
        
        <div class="grid-4">
            <div class="stat-card">
                <div class="stat-label">Balance</div>
                <div class="stat-value ${balanceClass}">${formatCurrency(data.balance)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Credits</div>
                <div class="stat-value positive">${formatCurrency(data.total_credits)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Debits</div>
                <div class="stat-value negative">${formatCurrency(data.total_debits)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Transactions</div>
                <div class="stat-value neutral">${data.transaction_count}</div>
            </div>
        </div>
        
        ${data.last_transaction_at ? `
            <p style="margin-top:1rem;font-size:0.8125rem;color:var(--text-muted);text-align:center;">
                Last transaction: ${new Date(data.last_transaction_at).toLocaleString()}
            </p>
        ` : ''}
    `;
}


// ═══════════════════════════════════════════════════════════════════
// RANKING LEADERBOARD
// ═══════════════════════════════════════════════════════════════════

async function fetchRanking() {
    const container = document.getElementById('ranking-result');
    container.innerHTML = '<div class="empty-state"><div class="spinner" style="margin:0 auto;width:32px;height:32px;border-width:3px;"></div><p style="margin-top:1rem;color:var(--text-muted);">Computing rankings...</p></div>';

    try {
        const res = await fetch(`${API_BASE}/ranking`);
        const data = await res.json();

        if (res.ok && data.rankings && data.rankings.length > 0) {
            renderRanking(data);
        } else {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🏅</div>
                    <p class="empty-state-title">No ranking data yet</p>
                    <p class="empty-state-desc">Seed demo data or submit transactions to populate the leaderboard.</p>
                </div>
            `;
        }
    } catch (err) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">⚠️</div>
                <p class="empty-state-title">Connection Error</p>
                <p class="empty-state-desc">${err.message}</p>
            </div>
        `;
    }
}

function renderRanking(data) {
    const container = document.getElementById('ranking-result');
    
    const rows = data.rankings.map(entry => {
        const rankClass = entry.rank <= 3 ? `rank-${entry.rank}` : 'rank-default';
        const f = entry.factors;
        
        return `
            <tr>
                <td>
                    <span class="rank-badge ${rankClass}">${entry.rank}</span>
                </td>
                <td>
                    <div class="user-info">
                        <div class="user-avatar" style="background:${getAvatarColor(entry.user_id)}">
                            ${getInitials(entry.user_name)}
                        </div>
                        <div>
                            <div class="user-name">${entry.user_name}</div>
                            <div class="user-id">${entry.user_id}</div>
                        </div>
                    </div>
                </td>
                <td>
                    <div class="score-bar-container">
                        <div class="score-bar">
                            <div class="score-bar-fill" style="width:${(entry.total_score * 100).toFixed(1)}%"></div>
                        </div>
                        <span class="score-value">${(entry.total_score * 100).toFixed(1)}%</span>
                    </div>
                </td>
                <td>
                    <div class="factor-grid">
                        <div class="factor-item">
                            <div class="factor-label">Vol</div>
                            <div class="factor-value ${factorClass(f.volume_score)}">${(f.volume_score * 100).toFixed(0)}%</div>
                        </div>
                        <div class="factor-item">
                            <div class="factor-label">Freq</div>
                            <div class="factor-value ${factorClass(f.frequency_score)}">${(f.frequency_score * 100).toFixed(0)}%</div>
                        </div>
                        <div class="factor-item">
                            <div class="factor-label">Cons</div>
                            <div class="factor-value ${factorClass(f.consistency_score)}">${(f.consistency_score * 100).toFixed(0)}%</div>
                        </div>
                        <div class="factor-item">
                            <div class="factor-label">Rec</div>
                            <div class="factor-value ${factorClass(f.recency_score)}">${(f.recency_score * 100).toFixed(0)}%</div>
                        </div>
                    </div>
                </td>
                <td style="font-family:'JetBrains Mono',monospace;">${entry.transaction_count}</td>
                <td style="font-family:'JetBrains Mono',monospace;">${formatCurrency(entry.total_volume)}</td>
                <td style="font-family:'JetBrains Mono',monospace;color:${entry.balance >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)'}">
                    ${formatCurrency(entry.balance)}
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-container">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>User</th>
                        <th>Total Score</th>
                        <th>Factor Breakdown</th>
                        <th>Txns</th>
                        <th>Volume</th>
                        <th>Balance</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </div>
        <p style="margin-top:1rem;font-size:0.75rem;color:var(--text-muted);text-align:center;">
            Algorithm: ${data.algorithm} · ${data.total_users} ranked users · Updated: ${new Date(data.last_updated).toLocaleString()}
        </p>
    `;
}
