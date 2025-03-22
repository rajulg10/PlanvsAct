document.addEventListener('DOMContentLoaded', function() {
    // Initialize form elements
    const form = document.getElementById('productionForm');
    const lossSection = document.getElementById('lossSection');
    const plannedInput = document.getElementById('planned');
    const actualInput = document.getElementById('actual');
    const totalLossTimeInput = document.getElementById('totalLossTime');
    const addLossButton = document.getElementById('addLossButton');
    const lossEntries = document.getElementById('lossEntries');

    // Initialize loss section as hidden
    lossSection.style.display = 'none';

    // Function to check and update loss section visibility
    function updateLossSectionVisibility() {
        const planned = parseInt(plannedInput.value) || 0;
        const actual = parseInt(actualInput.value) || 0;
        
        if (actual < planned) {
            lossSection.style.display = 'block';
            if (!lossEntries.hasChildNodes()) {
                addLossEntry();
            }
        } else {
            lossSection.style.display = 'none';
            lossEntries.innerHTML = '';
            totalLossTimeInput.value = '0';
        }
    }

    // Add event listeners for planned and actual inputs
    plannedInput.addEventListener('input', updateLossSectionVisibility);
    actualInput.addEventListener('input', updateLossSectionVisibility);

    // Add loss entry button handler
    addLossButton.addEventListener('click', function(e) {
        e.preventDefault();
        addLossEntry();
    });

    // Function to calculate and update total loss time
    function updateTotalLossTime() {
        const total = Array.from(document.querySelectorAll('.loss-time'))
            .reduce((sum, input) => sum + (parseInt(input.value) || 0), 0);
        totalLossTimeInput.value = total;
    }

    // Function to add a new loss entry
    function addLossEntry(data = null) {
        const template = document.getElementById('lossEntryTemplate');
        const clone = document.importNode(template.content, true);
        
        const entry = clone.querySelector('.loss-entry');
        const timeInput = entry.querySelector('.loss-time');
        const removeButton = entry.querySelector('.remove-loss');
        
        // Add event listeners
        timeInput.addEventListener('input', updateTotalLossTime);
        removeButton.addEventListener('click', function() {
            entry.remove();
            updateTotalLossTime();
            if (!lossEntries.hasChildNodes() && parseInt(plannedInput.value) > parseInt(actualInput.value)) {
                addLossEntry();
            }
        });
        
        // If data is provided, populate the fields
        if (data) {
            entry.querySelector('.loss-reason').value = data.reason || '';
            entry.querySelector('.loss-time').value = data.loss_time || '';
            entry.querySelector('.loss-remarks').value = data.remarks || '';
        }
        
        lossEntries.appendChild(clone);
        updateTotalLossTime();
    }

    // Function to get all loss entries
    function getLossEntries() {
        return Array.from(document.querySelectorAll('.loss-entry')).map(entry => ({
            reason: entry.querySelector('.loss-reason').value.trim(),
            loss_time: parseInt(entry.querySelector('.loss-time').value) || 0,
            remarks: entry.querySelector('.loss-remarks').value.trim()
        })).filter(entry => entry.reason && entry.loss_time > 0);
    }

    // Form submission handler
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const planned = parseInt(plannedInput.value);
        const actual = parseInt(actualInput.value);
        
        if (actual < planned && !getLossEntries().length) {
            alert('Please add at least one loss reason when actual is less than planned');
            return;
        }
        
        const entryId = document.getElementById('entryId').value;
        const method = entryId ? 'PUT' : 'POST';
        const url = entryId ? `/api/entry/${entryId}` : '/api/entry';
        
        try {
            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    line_number: parseInt(document.getElementById('lineNumber').value),
                    from_time: document.getElementById('fromTime').value,
                    to_time: document.getElementById('toTime').value,
                    planned: planned,
                    actual: actual,
                    total_loss_time: parseInt(totalLossTimeInput.value) || 0,
                    losses: getLossEntries()
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to save entry');
            }
            
            clearForm();
            await updateDailySummary();
        } catch (error) {
            console.error('Error:', error);
            alert(error.message);
        }
    });

    // Function to clear the form
    window.clearForm = function() {
        document.getElementById('entryId').value = '';
        form.reset();
        lossEntries.innerHTML = '';
        lossSection.style.display = 'none';
        totalLossTimeInput.value = '0';
    }

    // Function to load an entry for editing
    window.loadEntry = async function(entryId) {
        try {
            const response = await fetch(`/api/entry/${entryId}`);
            if (!response.ok) {
                throw new Error('Failed to load entry');
            }
            
            const data = await response.json();
            
            // Populate form fields
            document.getElementById('entryId').value = entryId;
            document.getElementById('lineNumber').value = data.line_number;
            document.getElementById('fromTime').value = data.from_time;
            document.getElementById('toTime').value = data.to_time;
            plannedInput.value = data.planned;
            actualInput.value = data.actual;
            
            // Clear existing loss entries
            lossEntries.innerHTML = '';
            
            // Show/hide loss section and add entries if needed
            if (data.actual < data.planned) {
                lossSection.style.display = 'block';
                if (data.losses && data.losses.length > 0) {
                    data.losses.forEach(loss => addLossEntry(loss));
                } else {
                    addLossEntry();
                }
            } else {
                lossSection.style.display = 'none';
            }
            
            window.scrollTo(0, 0);
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to load entry');
        }
    }

    // Function to update the daily summary
    async function updateDailySummary() {
        try {
            const response = await fetch('/api/daily-report');
            if (!response.ok) {
                throw new Error('Failed to fetch daily report');
            }
            
            const entries = await response.json();
            
            // Group entries by line
            const lines = {1: [], 2: []};
            entries.forEach(entry => lines[entry.line_number].push(entry));
            
            // Update each line's summary
            [1, 2].forEach(lineNum => {
                const lineEntries = lines[lineNum];
                
                // Calculate totals
                const totals = lineEntries.reduce((acc, entry) => ({
                    planned: acc.planned + entry.planned,
                    actual: acc.actual + entry.actual,
                    lossTime: acc.lossTime + entry.total_loss_time
                }), { planned: 0, actual: 0, lossTime: 0 });
                
                // Update summary stats
                document.getElementById(`totalPlanned${lineNum}`).textContent = totals.planned;
                document.getElementById(`totalActual${lineNum}`).textContent = totals.actual;
                document.getElementById(`totalLossTime${lineNum}`).textContent = `${totals.lossTime} min`;
                
                // Generate entries HTML
                const entriesHtml = lineEntries.map(entry => {
                    const lossesHtml = entry.losses.map(loss => `
                        <div class="ms-3 small">
                            <strong>${loss.reason}</strong> (${loss.loss_time} min)
                            ${loss.remarks ? `: ${loss.remarks}` : ''}
                        </div>
                    `).join('');
                    
                    return `
                        <div class="card mb-2">
                            <div class="card-body p-3">
                                <div class="d-flex justify-content-between align-items-start">
                                    <div>
                                        <strong>${entry.from_time} - ${entry.to_time}</strong>
                                        <div>Planned: ${entry.planned} | Actual: ${entry.actual}</div>
                                        ${entry.total_loss_time > 0 ? `<div class="text-danger">Loss Time: ${entry.total_loss_time} min</div>` : ''}
                                    </div>
                                    <button class="btn btn-outline-primary btn-sm" onclick="loadEntry(${entry.id})">
                                        Edit
                                    </button>
                                </div>
                                ${lossesHtml}
                            </div>
                        </div>`;
                }).join('');
                
                document.getElementById(`dailyEntries${lineNum}`).innerHTML = 
                    entriesHtml || '<p class="text-muted">No entries for today</p>';
                
                // Generate loss summary with time ranges and remarks
                const lossSummary = {};
                lineEntries.forEach(entry => {
                    entry.losses.forEach(loss => {
                        const key = loss.reason;
                        if (!lossSummary[key]) {
                            lossSummary[key] = {
                                totalTime: 0,
                                occurrences: []
                            };
                        }
                        lossSummary[key].totalTime += loss.loss_time;
                        lossSummary[key].occurrences.push({
                            timeRange: `${entry.from_time}-${entry.to_time}`,
                            lossTime: loss.loss_time,
                            remarks: loss.remarks
                        });
                    });
                });
                
                const lossSummaryHtml = Object.entries(lossSummary)
                    .map(([reason, data]) => {
                        const occurrencesHtml = data.occurrences
                            .map(occ => `
                                <div class="ms-3 small">
                                    <span class="text-muted">${occ.timeRange}</span>: 
                                    ${occ.lossTime} min
                                    ${occ.remarks ? `<br><span class="text-muted">Remarks: ${occ.remarks}</span>` : ''}
                                </div>
                            `).join('');
                        
                        return `
                            <div class="card mb-2">
                                <div class="card-body p-2">
                                    <div><strong>${reason}</strong>: Total ${data.totalTime} minutes</div>
                                    ${occurrencesHtml}
                                </div>
                            </div>
                        `;
                    }).join('');
                
                document.getElementById(`lossSummary${lineNum}`).innerHTML = 
                    lossSummaryHtml || '<p class="text-muted">No losses recorded</p>';
            });
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to update summary');
        }
    }

    // Function to generate reports
    window.generateReport = function(type) {
        window.open(`/api/report/${type}`, '_blank');
    }

    // Initial load
    updateDailySummary();
});
