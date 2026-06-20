/**
 * InfrX Mortgage Intelligence Agent v2 — Frontend Application
 * Handles document tree, page viewer, chat QA, audit flow, and all interactions.
 */
document.addEventListener("DOMContentLoaded", () => {

    // ================================================================
    // STATE
    // ================================================================
    const state = {
        docName: "",
        pageCount: 0,
        currentPage: 1,
        documents: [],
        isQuerying: false,
    };

    // ================================================================
    // DOM REFS
    // ================================================================
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const statusLabel     = $("#status-label");
    const fileInput       = $("#file-input");
    const docTreeList     = $("#doc-tree-list");
    const lblCurrentPage  = $("#lbl-current-page");
    const lblTotalPages   = $("#lbl-total-pages");
    const pageText        = $("#page-text");
    const btnPrevPage     = $("#btn-prev-page");
    const btnNextPage     = $("#btn-next-page");
    const chatFeed        = $("#chat-feed");
    const chatForm        = $("#chat-form");
    const chatInput       = $("#chat-input");
    const chatSendBtn     = $("#chat-send-btn");
    const modalConfig     = $("#modal-config");
    const modalClose      = $("#modal-close");
    const inputApiKey     = $("#input-api-key");
    const btnSaveKey      = $("#btn-save-key");
    const navSettings     = $("#nav-settings");
    const dropOverlay     = $("#drop-overlay");

    // Tab switching
    const tabBtns    = $$(".tab-btn");
    const tabPanes   = $$(".tab-pane");

    // ================================================================
    // INIT
    // ================================================================
    if (localStorage.getItem("gemini_api_key")) {
        inputApiKey.value = localStorage.getItem("gemini_api_key");
    }
    fetchStatus();

    // ================================================================
    // EVENT LISTENERS
    // ================================================================

    // -- Tab switching
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));
            btn.classList.add("active");
            const target = btn.getAttribute("data-tab");
            $(`#${target}`).classList.add("active");
        });
    });

    // -- Settings modal
    navSettings.addEventListener("click", () => modalConfig.classList.add("open"));
    modalClose.addEventListener("click", () => modalConfig.classList.remove("open"));
    modalConfig.addEventListener("click", (e) => {
        if (e.target === modalConfig) modalConfig.classList.remove("open");
    });
    btnSaveKey.addEventListener("click", () => {
        localStorage.setItem("gemini_api_key", inputApiKey.value.trim());
        modalConfig.classList.remove("open");
    });

    // -- Page navigation
    btnPrevPage.addEventListener("click", () => {
        if (state.currentPage > 1) loadPage(state.currentPage - 1);
    });
    btnNextPage.addEventListener("click", () => {
        if (state.currentPage < state.pageCount) loadPage(state.currentPage + 1);
    });

    // -- Keyboard page navigation
    document.addEventListener("keydown", (e) => {
        // Only when viewer tab is active and no input focused
        if (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA") return;
        if (e.key === "ArrowLeft") {
            if (state.currentPage > 1) loadPage(state.currentPage - 1);
        } else if (e.key === "ArrowRight") {
            if (state.currentPage < state.pageCount) loadPage(state.currentPage + 1);
        }
    });

    // -- File upload
    fileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        await uploadFile(file);
    });

    // -- Drag-and-drop
    let dragCounter = 0;
    document.addEventListener("dragenter", (e) => {
        e.preventDefault();
        dragCounter++;
        dropOverlay.classList.add("active");
    });
    document.addEventListener("dragleave", (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            dropOverlay.classList.remove("active");
        }
    });
    document.addEventListener("dragover", (e) => e.preventDefault());
    document.addEventListener("drop", async (e) => {
        e.preventDefault();
        dragCounter = 0;
        dropOverlay.classList.remove("active");
        const file = e.dataTransfer.files[0];
        if (file && file.name.toLowerCase().endsWith(".pdf")) {
            await uploadFile(file);
        }
    });

    // -- Chat form submit
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query || state.isQuerying) return;
        chatInput.value = "";
        submitQuery(query);
    });

    // -- Global click delegation
    document.addEventListener("click", (e) => {
        // Suggest chips
        if (e.target.classList.contains("suggest-chip")) {
            const q = e.target.innerText;
            if (!state.isQuerying) submitQuery(q);
        }
        // Citation pills
        if (e.target.closest(".citation-pill")) {
            const pill = e.target.closest(".citation-pill");
            const pageNum = parseInt(pill.getAttribute("data-page"));
            if (pageNum) jumpToPage(pageNum);
        }
        // Audit flow toggle
        if (e.target.closest(".audit-flow-toggle")) {
            const box = e.target.closest(".audit-flow-box");
            box.classList.toggle("expanded");
        }
    });

    // ================================================================
    // API FUNCTIONS
    // ================================================================

    async function fetchStatus() {
        try {
            const resp = await fetch("/api/status");
            const data = await resp.json();
            state.docName = data.document_name || "";
            state.pageCount = data.page_count || 0;
            statusLabel.textContent = state.docName || "No document loaded";
            lblTotalPages.textContent = state.pageCount;

            if (data.loaded) {
                const docsResp = await fetch("/api/documents");
                state.documents = await docsResp.json();
                renderDocTree();
                if (state.pageCount > 0) loadPage(1);
            }
        } catch (err) {
            console.error("Status fetch failed:", err);
            statusLabel.textContent = "Connection error";
        }
    }

    async function loadPage(pageNum) {
        if (pageNum < 1 || pageNum > state.pageCount) return;
        state.currentPage = pageNum;
        lblCurrentPage.textContent = pageNum;
        try {
            const resp = await fetch(`/api/page/${pageNum}`);
            const data = await resp.json();
            pageText.textContent = data.text;
        } catch (err) {
            pageText.textContent = "Error loading page content.";
        }
    }

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append("file", file);
        statusLabel.textContent = "Analyzing document boundaries...";

        try {
            const resp = await fetch("/api/upload", { method: "POST", body: formData });
            const data = await resp.json();
            if (resp.ok) {
                state.docName = data.document_name;
                state.pageCount = data.page_count;
                state.documents = data.documents;
                state.currentPage = 1;
                statusLabel.textContent = state.docName;
                lblTotalPages.textContent = state.pageCount;
                lblCurrentPage.textContent = 1;
                renderDocTree();
                loadPage(1);
                addSystemMessage(`Successfully uploaded and paginated <b>${esc(state.docName)}</b> into <b>${state.documents.length}</b> logical documents across <b>${state.pageCount}</b> pages.`);
            } else {
                alert(`Upload failed: ${data.detail}`);
                fetchStatus();
            }
        } catch (err) {
            alert(`Error uploading: ${err.message}`);
            fetchStatus();
        }
    }

    async function submitQuery(query) {
        state.isQuerying = true;
        chatSendBtn.disabled = true;
        addUserMessage(query);
        const placeholder = addTypingPlaceholder();

        const apiKey = localStorage.getItem("gemini_api_key") || "";

        try {
            const resp = await fetch("/api/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, api_key: apiKey })
            });
            const data = await resp.json();

            if (resp.ok) {
                replaceWithAnswer(placeholder, data);
            } else {
                replaceWithError(placeholder, data.detail || "Something went wrong.");
            }
        } catch (err) {
            replaceWithError(placeholder, `Network error: ${err.message}`);
        }

        state.isQuerying = false;
        chatSendBtn.disabled = false;
    }

    // ================================================================
    // DOCUMENT TREE RENDERER
    // ================================================================

    function renderDocTree() {
        docTreeList.innerHTML = "";
        if (!state.documents.length) {
            docTreeList.innerHTML = '<p class="text-muted" style="font-size:12px; padding:8px 0;">No sub-documents detected.</p>';
            return;
        }

        state.documents.forEach((doc, idx) => {
            const color = doc.color || "#6b7280";
            const icon = doc.icon || "fa-file";
            const gradient = doc.gradient || `linear-gradient(135deg, ${color}, ${color})`;
            const confidence = doc.confidence || 0.8;

            const node = document.createElement("div");
            node.className = "doc-node";
            node.style.setProperty("--node-color", color);
            node.style.animationDelay = `${idx * 0.05}s`;

            // Build metadata chips
            let metaHTML = "";
            if (doc.metadata) {
                for (const [key, val] of Object.entries(doc.metadata)) {
                    metaHTML += `<span class="meta-tag"><b>${key}:</b> ${esc(String(val))}</span>`;
                }
            }
            if (!metaHTML) {
                metaHTML = '<span class="meta-tag">No extra attributes</span>';
            }

            // Page range label
            const pageLabel = doc.start_page === doc.end_page
                ? `Page ${doc.start_page}`
                : `Pages ${doc.start_page}–${doc.end_page}`;

            node.innerHTML = `
                <div class="doc-node-top">
                    <div class="doc-node-label">
                        <div class="doc-node-icon" style="background:${gradient}">
                            <i class="fa-solid ${icon}"></i>
                        </div>
                        <span class="doc-node-name">${esc(doc.doc_type)}</span>
                    </div>
                    <span class="doc-node-pages-badge" style="color:${color}; background:${color}12;">${pageLabel}</span>
                </div>
                <div class="doc-node-meta">${metaHTML}</div>
                <div class="doc-node-confidence">
                    <div class="confidence-bar-track">
                        <div class="confidence-bar-fill" style="width:${confidence * 100}%; background:${color};"></div>
                    </div>
                    <span class="confidence-label">${Math.round(confidence * 100)}% conf.</span>
                </div>
            `;

            node.addEventListener("click", () => jumpToPage(doc.start_page));
            docTreeList.appendChild(node);
        });
    }

    // ================================================================
    // PAGE NAVIGATION
    // ================================================================

    function jumpToPage(pageNum) {
        // Switch to viewer tab
        const viewerTab = $('[data-tab="tab-viewer"]');
        if (viewerTab) viewerTab.click();
        loadPage(pageNum);
    }

    // ================================================================
    // CHAT MESSAGE BUILDERS
    // ================================================================

    function addUserMessage(text) {
        const div = document.createElement("div");
        div.className = "msg user-msg";
        div.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-user"></i></div>
            <div class="msg-bubble"><p>${esc(text)}</p></div>
        `;
        chatFeed.appendChild(div);
        scrollChat();
    }

    function addSystemMessage(html) {
        const div = document.createElement("div");
        div.className = "msg system-msg";
        div.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-circle-info"></i></div>
            <div class="msg-bubble"><p>${html}</p></div>
        `;
        chatFeed.appendChild(div);
        scrollChat();
    }

    function addTypingPlaceholder() {
        const div = document.createElement("div");
        div.className = "msg assistant-msg";
        div.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-bubble">
                <div class="typing-indicator"><span></span><span></span><span></span></div>
            </div>
        `;
        chatFeed.appendChild(div);
        scrollChat();
        return div;
    }

    function replaceWithAnswer(placeholder, data) {
        const answer = data.answer || "No answer returned.";
        const citations = data.citations || [];
        const confidence = data.confidence || "medium";
        const reasoning = data.reasoning || "";
        const auditFlow = data.audit_flow || null;

        // Confidence badge
        const confBadge = `<div class="confidence-badge ${confidence}"><i class="fa-solid fa-${confidence === 'high' ? 'circle-check' : confidence === 'medium' ? 'circle-exclamation' : 'circle-xmark'}"></i> ${confidence.toUpperCase()} CONFIDENCE</div>`;

        // Citations row
        let citationsHTML = "";
        if (citations.length) {
            const pills = citations.map(c =>
                `<button class="citation-pill" data-page="${c}"><i class="fa-solid fa-file-lines"></i> Page ${c}</button>`
            ).join(" ");
            citationsHTML = `
                <div class="citations-row">
                    <span class="citations-label">Sources:</span>
                    ${pills}
                </div>
            `;
        }

        // Audit flow panel
        let auditHTML = "";
        if (auditFlow) {
            auditHTML = buildAuditFlowHTML(auditFlow);
        }

        placeholder.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-bubble">
                ${confBadge}
                <p>${esc(answer)}</p>
                ${citationsHTML}
                ${auditHTML}
            </div>
        `;
        scrollChat();
    }

    function replaceWithError(placeholder, detail) {
        placeholder.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-bubble">
                <p class="error-text"><i class="fa-solid fa-triangle-exclamation"></i> <b>Error:</b> ${esc(detail)}</p>
            </div>
        `;
        scrollChat();
    }

    // ================================================================
    // AUDIT FLOW RENDERER
    // ================================================================

    function buildAuditFlowHTML(af) {
        let sections = "";

        // Matrices
        if (af.matrices) {
            const score = af.matrices.score || 0;
            sections += `
                <div class="audit-section">
                    <div class="audit-section-header">
                        <div class="audit-section-title matrices"><i class="fa-solid fa-border-all"></i> Representation Matrices</div>
                        <span class="audit-score text-cyan">${(score * 100).toFixed(0)}%</span>
                    </div>
                    <div class="audit-section-desc">${esc(af.matrices.description || "")}</div>
                    <div class="score-bar"><div class="score-bar-fill cyan" style="width:${score * 100}%"></div></div>
                </div>
            `;
        }

        // Lattice
        if (af.lattice) {
            const score = af.lattice.score || 0;
            sections += `
                <div class="audit-section">
                    <div class="audit-section-header">
                        <div class="audit-section-title lattice"><i class="fa-solid fa-table-cells"></i> Page Lattice</div>
                        <span class="audit-score text-amber">${(score * 100).toFixed(0)}%</span>
                    </div>
                    <div class="audit-section-desc">${esc(af.lattice.description || "")}</div>
                    <div class="score-bar"><div class="score-bar-fill amber" style="width:${score * 100}%"></div></div>
                </div>
            `;
        }

        // Semaphore
        if (af.semaphore) {
            let stagesHTML = "";
            if (af.semaphore.stages && af.semaphore.stages.length) {
                stagesHTML = '<div class="semaphore-stages">' +
                    af.semaphore.stages.map(s =>
                        `<div class="semaphore-stage"><span class="semaphore-dot ${s.status}"></span> ${esc(s.name)}</div>`
                    ).join("") +
                '</div>';
            }
            sections += `
                <div class="audit-section">
                    <div class="audit-section-header">
                        <div class="audit-section-title semaphore"><i class="fa-solid fa-traffic-light"></i> Processing Semaphore</div>
                    </div>
                    <div class="audit-section-desc">${esc(af.semaphore.description || "")}</div>
                    ${stagesHTML}
                </div>
            `;
        }

        // Entropy
        if (af.entropy) {
            const score = af.entropy.score || 0;
            const level = af.entropy.level || "medium";
            sections += `
                <div class="audit-section">
                    <div class="audit-section-header">
                        <div class="audit-section-title entropy"><i class="fa-solid fa-wave-square"></i> Token Entropy</div>
                        <span class="audit-score text-purple">${(score * 100).toFixed(0)}% (${level})</span>
                    </div>
                    <div class="audit-section-desc">${esc(af.entropy.description || "")}</div>
                    <div class="score-bar"><div class="score-bar-fill purple" style="width:${score * 100}%"></div></div>
                </div>
            `;
        }

        // Covariance
        if (af.covariance) {
            const score = af.covariance.score || 0;
            sections += `
                <div class="audit-section">
                    <div class="audit-section-header">
                        <div class="audit-section-title covariance"><i class="fa-solid fa-chart-line"></i> Wage Covariance</div>
                        <span class="audit-score text-pink">${(score * 100).toFixed(0)}%</span>
                    </div>
                    <div class="audit-section-desc">${esc(af.covariance.description || "")}</div>
                    <div class="score-bar"><div class="score-bar-fill pink" style="width:${score * 100}%"></div></div>
                </div>
            `;
        }

        return `
            <div class="audit-flow-box">
                <div class="audit-flow-toggle">
                    <i class="fa-solid fa-chevron-right"></i>
                    <span class="toggle-label">Technical Audit Flow</span>
                    <span class="toggle-badge">BROWNIE POINTS</span>
                </div>
                <div class="audit-flow-content">
                    ${sections}
                </div>
            </div>
        `;
    }

    // ================================================================
    // UTILITIES
    // ================================================================

    function scrollChat() {
        chatFeed.scrollTop = chatFeed.scrollHeight;
    }

    function esc(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

});
