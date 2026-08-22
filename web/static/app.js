let currentFile = null;
let audioBlobUrl = null;
let analysisData = null;
let currentSessionId = null;
let currentSource = null;
let audioContext = null;
let playToken = 0;
let decodedBuffer = null;
let decodedForFile = null;
let decodePromise = null;

const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const loading = document.getElementById('loading');
const results = document.getElementById('results');
const error = document.getElementById('error');
const loopsTbody = document.getElementById('loops-tbody');
const exportBtn = document.getElementById('export-btn');
const retryBtn = document.getElementById('retry-btn');
const newFileBtn = document.getElementById('new-file-btn');
const paginationEl = document.getElementById('pagination');
const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');
const pageIndicator = document.getElementById('page-indicator');

const PAGE_SIZE = 8;
let currentLoops = [];
let currentPage = 0;
let selectedIndices = new Set();

uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('drag-over');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

exportBtn.addEventListener('click', exportSelectedLoops);
retryBtn.addEventListener('click', () => {
    error.classList.add('hidden');
    uploadZone.classList.remove('hidden');
});
newFileBtn.addEventListener('click', startOver);

prevPageBtn.addEventListener('click', () => {
    if (currentPage > 0) {
        currentPage--;
        renderLoopPage();
    }
});

nextPageBtn.addEventListener('click', () => {
    const totalPages = Math.max(1, Math.ceil(currentLoops.length / PAGE_SIZE));
    if (currentPage < totalPages - 1) {
        currentPage++;
        renderLoopPage();
    }
});

function startOver() {
    stopPreview();
    analysisData = null;
    currentSessionId = null;
    currentFile = null;
    decodedBuffer = null;
    decodedForFile = null;
    decodePromise = null;
    currentLoops = [];
    currentPage = 0;
    selectedIndices = new Set();
    if (audioBlobUrl) {
        URL.revokeObjectURL(audioBlobUrl);
        audioBlobUrl = null;
    }

    loading.classList.add('hidden');
    results.classList.add('hidden');
    error.classList.add('hidden');
    uploadZone.classList.remove('hidden');
}

function handleFile(file) {
    stopPreview();
    analysisData = null;
    currentSessionId = null;
    selectedIndices = new Set();

    currentFile = file;
    decodedBuffer = null;
    decodedForFile = null;
    decodePromise = null;
    if (audioBlobUrl) {
        URL.revokeObjectURL(audioBlobUrl);
    }
    audioBlobUrl = URL.createObjectURL(file);

    showLoading();

    const formData = new FormData();
    formData.append('file', file);

    fetch('/upload', {
        method: 'POST',
        body: formData,
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            let msg = data.error;
            if (data.details) {
                msg += '\n\n' + data.details;
            }
            if (data.audioDuration !== undefined) {
                msg += '\n\nAudio duration: ' + formatDuration(data.audioDuration);
            }
            if (data.bpm !== undefined) {
                msg += '\nDetected BPM: ' + data.bpm.toFixed(2);
            }
            showError(msg);
            return;
        }
        analysisData = data;
        currentSessionId = data.sessionId;
        displayResults(data);
    })
    .catch(err => {
        showError('Failed to upload file. Please try again.');
        console.error(err);
    });
}

let playingLoopIndex = null;

function displayResults(data) {
    loading.classList.add('hidden');
    results.classList.remove('hidden');

    document.getElementById('filename').textContent = data.filename;
    document.getElementById('duration').textContent = formatDuration(data.duration);
    document.getElementById('bpm').textContent = data.bpm.toFixed(2);
    document.getElementById('key').textContent = data.key;

    rebuildLoopTable(data.loops);
    updateExportState();
}

function rebuildLoopTable(loops) {
    currentLoops = loops;
    currentPage = 0;
    renderLoopPage();
}

// Loop selections (for export) and the playing indicator both key off the loop's
// index, which is stable across pages, so state survives paging even though each
// page swaps out the actual <tr> elements in the DOM.
function renderLoopPage() {
    const totalPages = Math.max(1, Math.ceil(currentLoops.length / PAGE_SIZE));
    currentPage = Math.min(currentPage, totalPages - 1);

    const start = currentPage * PAGE_SIZE;
    const pageLoops = currentLoops.slice(start, start + PAGE_SIZE);

    loopsTbody.innerHTML = '';
    pageLoops.forEach(loop => {
        const row = document.createElement('tr');
        row.dataset.index = loop.index;
        row.dataset.startSec = loop.loop_start_sec;
        row.dataset.endSec = loop.loop_end_sec;
        if (loop.index === playingLoopIndex) {
            row.classList.add('playing');
        }
        let typeLabel = '?';
        if (loop.loop_type === 'one_bar') {
            typeLabel = '1 Bar';
        } else if (loop.loop_type === 'two_bars') {
            typeLabel = '2 Bars';
        } else if (loop.loop_type === 'four_bars') {
            typeLabel = '4 Bars';
        } else {
            typeLabel = '?';
        }
        const typeClass = loop.loop_type === 'unknown' ? 'unknown' : loop.loop_type;
        const checkedAttr = selectedIndices.has(loop.index) ? 'checked' : '';
        row.innerHTML = `
            <td><input type="checkbox" name="export-loop" value="${loop.index}" ${checkedAttr}></td>
            <td>${loop.index}</td>
            <td>${loop.start_time}</td>
            <td>${loop.end_time}</td>
            <td>${loop.length}</td>
            <td><span class="loop-type-badge ${typeClass}">${typeLabel}</span></td>
            <td class="score-cell">${loop.score.toFixed(2)}</td>
        `;
        loopsTbody.appendChild(row);
    });

    loopsTbody.querySelectorAll('tr[data-index]').forEach(row => {
        row.addEventListener('click', (e) => {
            if (e.target.type === 'checkbox') return;

            const idx = parseInt(row.dataset.index);
            const startSec = parseFloat(row.dataset.startSec);
            const endSec = parseFloat(row.dataset.endSec);

            if (playingLoopIndex === idx) {
                stopPreview();
            } else {
                playLoop(idx, startSec, endSec, row);
            }
        });
    });

    loopsTbody.querySelectorAll('input[name="export-loop"]').forEach(cb => {
        cb.addEventListener('change', () => {
            const idx = parseInt(cb.value);
            if (cb.checked) {
                selectedIndices.add(idx);
            } else {
                selectedIndices.delete(idx);
            }
            updateExportState();
        });
    });

    paginationEl.classList.toggle('hidden', currentLoops.length <= PAGE_SIZE);
    prevPageBtn.disabled = currentPage === 0;
    nextPageBtn.disabled = currentPage >= totalPages - 1;
    pageIndicator.textContent = `PAGE ${currentPage + 1} / ${totalPages}`;
}

function updateExportState() {
    exportBtn.disabled = selectedIndices.size === 0;
}

function getAudioContext() {
    if (!audioContext || audioContext.state === 'closed') {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioContext;
}

// Decodes (and caches) the current file's audio data. Concurrent callers share the
// same in-flight promise instead of each kicking off their own FileReader/decode.
function getDecodedBuffer() {
    if (decodedBuffer && decodedForFile === currentFile) {
        return Promise.resolve(decodedBuffer);
    }
    if (decodePromise && decodedForFile === currentFile) {
        return decodePromise;
    }

    decodedForFile = currentFile;
    decodePromise = new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            getAudioContext().decodeAudioData(e.target.result)
                .then((audioBuffer) => {
                    decodedBuffer = audioBuffer;
                    resolve(audioBuffer);
                })
                .catch(reject);
        };
        reader.onerror = () => reject(new Error('Failed to read audio file for preview.'));
        reader.readAsArrayBuffer(currentFile);
    });
    return decodePromise;
}

function playLoop(index, startSec, endSec, row) {
    stopPreview();

    if (!audioBlobUrl) {
        alert('Audio file not available for preview.');
        return;
    }

    // Mark as playing (and bump the token) synchronously, before the async decode
    // resolves, so a rapid second click on the same row is recognized as "stop this"
    // by the caller instead of racing to start a second, independent playback.
    const myToken = ++playToken;
    playingLoopIndex = index;
    row.classList.add('playing');

    getDecodedBuffer().then((audioBuffer) => {
        if (myToken !== playToken) return; // superseded by a newer play/stop request

        // startSec/endSec are computed server-side from the audio file's actual native
        // sample rate. decodeAudioData() always resamples into the AudioContext's own
        // sample rate (commonly different from the source file's, e.g. 48kHz vs a
        // 44.1kHz FLAC), so audioBuffer.sampleRate must never be used to convert the
        // server's loop points -- doing so silently scales the loop length by the ratio
        // between the two rates.
        const ctx = getAudioContext();
        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);

        source.loop = true;
        source.loopStart = startSec;
        source.loopEnd = endSec;

        source.start(0, startSec);
        currentSource = source;
    }).catch(err => {
        console.error('Decode failed:', err);
        if (myToken === playToken) {
            alert('Failed to decode audio for preview.');
            stopPreview();
        }
    });
}

function stopPreview() {
    playToken++; // invalidate any in-flight play request so it can't start after this
    if (currentSource) {
        try {
            currentSource.stop();
        } catch (e) {
            // already stopped/ended
        }
        currentSource = null;
    }
    if (playingLoopIndex !== null) {
        const playingRow = loopsTbody.querySelector(`tr[data-index="${playingLoopIndex}"]`);
        if (playingRow) {
            playingRow.classList.remove('playing');
        }
    }
    playingLoopIndex = null;
}

function exportSelectedLoops() {
    const selected = Array.from(selectedIndices).sort((a, b) => a - b);

    if (selected.length === 0) {
        alert('Please select at least one loop.');
        return;
    }

    exportBtn.disabled = true;
    exportBtn.textContent = 'Exporting...';

    fetch('/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            sessionId: currentSessionId,
            selectedIndices: selected,
        }),
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            alert('Export failed: ' + data.error);
            exportBtn.disabled = false;
            exportBtn.textContent = 'Export Selected';
            return;
        }

        const a = document.createElement('a');
        a.href = data.downloadUrl;
        a.download = `${analysisData.filename.replace(/\.[^.]+$/, '')}-loops.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        exportBtn.disabled = false;
        exportBtn.textContent = 'Export Selected';
    })
    .catch(err => {
        alert('Export failed. Please try again.');
        console.error(err);
        exportBtn.disabled = false;
        exportBtn.textContent = 'Export Selected';
    });
}

function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);
    return `${mins}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
}

function showLoading() {
    uploadZone.classList.add('hidden');
    results.classList.add('hidden');
    error.classList.add('hidden');
    loading.classList.remove('hidden');
}

function showError(message) {
    loading.classList.add('hidden');
    uploadZone.classList.remove('hidden');
    results.classList.add('hidden');
    error.classList.remove('hidden');
    error.querySelector('.error-message').textContent = message;
}