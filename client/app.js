"use strict";

const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const chatMessages = document.getElementById("chatMessages");
const sendButton = document.getElementById("sendButton");
const newChatButton = document.getElementById("newChatButton");
const retryHistoryButton = document.getElementById("retryHistoryButton");
const statusElement = document.getElementById("status");
const SESSION_KEY = "smartcourse_session_id";
const TOOL_LABELS = {
    grade_calculator: "Grade Calculator",
    course_information_lookup: "Course Information Lookup"
};

let sessionId = null;
let busy = false;
let historyReady = true;
let storageAvailable = true;
let conversationVersion = 0;

try {
    sessionId = localStorage.getItem(SESSION_KEY);
} catch (_) {
    storageAvailable = false;
}

function rememberSession(value) {
    sessionId = value;
    try {
        if (value) localStorage.setItem(SESSION_KEY, value);
        else localStorage.removeItem(SESSION_KEY);
    } catch (_) {
        storageAvailable = false;
    }
}

function setStatus(message = "", isError = false) {
    statusElement.textContent = message;
    statusElement.classList.toggle("error", isError);
}

function updateControls() {
    sendButton.disabled = busy || !historyReady;
    messageInput.disabled = busy || !historyReady;
    newChatButton.disabled = busy;
    retryHistoryButton.disabled = busy;
    chatMessages.setAttribute("aria-busy", String(busy));
}

function setBusy(value, label = "") {
    busy = value;
    updateControls();
    if (value) setStatus(label);
}

function showWelcome() {
    chatMessages.replaceChildren();
    const welcome = document.createElement("div");
    welcome.className = "welcome";
    const title = document.createElement("h2");
    title.textContent = "Welcome to SmartCourse AI";
    const description = document.createElement("p");
    description.textContent = "Ask about course materials, calculate weighted grades, or ask a general study question.";
    welcome.append(title, description);
    chatMessages.append(welcome);
}

function addMessage(role, content, metadata = {}) {
    chatMessages.querySelector(".welcome")?.remove();
    const message = document.createElement("article");
    const isUser = role === "user";
    message.className = `message ${isUser ? "user" : "assistant"}`;
    const bubble = document.createElement("div");
    bubble.className = "message-content";
    const speaker = document.createElement("div");
    speaker.className = "speaker";
    speaker.textContent = isUser ? "You" : "SmartCourse AI";
    const text = document.createElement("div");
    text.className = "message-text";
    text.dir = "auto";
    // User input, model output, filenames and metadata are always plain text.
    text.textContent = typeof content === "string" ? content : "";
    bubble.append(speaker, text);

    if (!isUser) {
        const route = metadata.route;
        if (route) {
            const badge = document.createElement("div");
            badge.className = "route";
            const tool = TOOL_LABELS[metadata.tool] || metadata.tool;
            badge.textContent = `Route: ${route === "TOOL" && tool ? `TOOL: ${tool}` : route}`;
            bubble.append(badge);
        }
        if (metadata.routing_reason) {
            const reason = document.createElement("div");
            reason.className = "routing-reason";
            reason.textContent = metadata.routing_reason;
            bubble.append(reason);
        }
        if (Array.isArray(metadata.sources) && metadata.sources.length) {
            const sources = document.createElement("ul");
            sources.className = "sources";
            for (const source of metadata.sources) {
                if (!source || typeof source !== "object") continue;
                const item = document.createElement("li");
                item.dir = "auto";
                const documentName = source.document || source.source || source.filename;
                const page = source.page ?? source.page_number;
                const parts = [documentName ? `Source: ${documentName}` : "Source: unnamed document"];
                if (page !== null && page !== undefined) parts.push(`Page: ${page}`);
                if (typeof source.similarity === "number" && Number.isFinite(source.similarity)) {
                    parts.push(`Similarity: ${source.similarity.toFixed(3)}`);
                }
                item.textContent = parts.join(" · ");
                sources.append(item);
            }
            if (sources.childElementCount) bubble.append(sources);
        }
    }
    message.append(bubble);
    chatMessages.append(message);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return message;
}

async function requestJSON(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 300000);
    try {
        const response = await fetch(url, { ...options, signal: controller.signal, credentials: "same-origin" });
        let data;
        try {
            data = await response.json();
        } catch (_) {
            throw new Error("The server returned an unreadable response. Check that Flask is running.");
        }
        if (!data || typeof data !== "object" || Array.isArray(data)) {
            throw new Error("The server returned an unexpected response.");
        }
        return { response, data };
    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error(sessionId
                ? "The request timed out. Use Retry history to check whether a response was saved."
                : "The request timed out while starting the chat. Check the connection and try again.");
        }
        if (error instanceof TypeError) throw new Error("Cannot reach the server. Check the connection and try again.");
        throw error;
    } finally {
        clearTimeout(timeout);
    }
}

function responseError(data, fallback) {
    const error = new Error(typeof data.error === "string" ? data.error : fallback);
    error.code = data.code;
    return error;
}

async function loadHistory() {
    if (!sessionId || busy) return;
    const requestedSession = sessionId;
    const version = conversationVersion;
    historyReady = false;
    retryHistoryButton.hidden = true;
    setBusy(true, "Loading your conversation...");
    try {
        const { response, data } = await requestJSON(`/history?session_id=${encodeURIComponent(requestedSession)}`);
        // Never apply history belonging to a chat that has since been replaced.
        if (version !== conversationVersion || requestedSession !== sessionId) return;
        if (response.status === 404 || (response.status === 400 && data.code === "invalid_session")) {
            rememberSession(null);
            showWelcome();
            historyReady = true;
            setStatus("The saved session is no longer available. Your next message will start a new chat.");
            return;
        }
        if (!response.ok) throw responseError(data, "Unable to load conversation history.");
        if (!Array.isArray(data.messages)) throw new Error("The server returned invalid conversation history.");
        showWelcome();
        for (const message of data.messages) {
            if (message && ["user", "assistant"].includes(message.role)) {
                addMessage(message.role, message.content, { ...(message.metadata || {}), ...message });
            }
        }
        historyReady = true;
        setStatus(storageAvailable ? "" : "Browser storage is unavailable; this chat will not survive a refresh.");
    } catch (error) {
        if (version !== conversationVersion) return;
        setStatus(`${error.message} Retry history or start a new chat.`, true);
        retryHistoryButton.hidden = false;
    } finally {
        setBusy(false);
        if (historyReady) messageInput.focus();
    }
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !historyReady) return;
    const message = messageInput.value.trim();
    if (!message) {
        setStatus("Please enter a question.", true);
        return;
    }
    const version = conversationVersion;
    const optimisticMessage = addMessage("user", message);
    messageInput.value = "";
    setBusy(true, "SmartCourse AI is thinking...");
    try {
        // Save the new UUID before generation so a slow/failed response can be
        // recovered through history, including on the first turn of a chat.
        if (!sessionId) {
            const created = await requestJSON("/sessions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({})
            });
            if (version !== conversationVersion) return;
            if (!created.response.ok) throw responseError(created.data, "Unable to start the chat.");
            if (typeof created.data.session_id !== "string" || !created.data.session_id) {
                throw new Error("The server did not return a valid session ID.");
            }
            rememberSession(created.data.session_id);
        }
        const body = { message, session_id: sessionId };
        const { response, data } = await requestJSON("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (version !== conversationVersion) return;
        // An error can still identify a newly created session, even without a saved exchange.
        if (typeof data.session_id === "string" && data.session_id) rememberSession(data.session_id);
        if (!response.ok) throw responseError(data, "Unable to process the question.");
        if (typeof data.answer !== "string" || typeof data.session_id !== "string") {
            throw new Error("The server returned an incomplete answer.");
        }
        addMessage("assistant", data.answer, data);
        setStatus(storageAvailable ? "" : "Browser storage is unavailable; this chat will not survive a refresh.");
    } catch (error) {
        if (version !== conversationVersion) return;
        optimisticMessage.classList.add("unconfirmed");
        optimisticMessage.title = "The response failed. Reload history to check what the server saved.";
        messageInput.value = message;
        setStatus(`${error.message} Your question is restored in the input.`, true);
        if (sessionId) retryHistoryButton.hidden = false;
    } finally {
        setBusy(false);
        messageInput.focus();
    }
});

messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (!busy && historyReady) chatForm.requestSubmit();
    }
});

newChatButton.addEventListener("click", () => {
    if (busy) return;
    conversationVersion += 1;
    rememberSession(null);
    historyReady = true;
    retryHistoryButton.hidden = true;
    showWelcome();
    messageInput.value = "";
    setStatus("A new chat will start when you send your first question.");
    updateControls();
    messageInput.focus();
});

retryHistoryButton.addEventListener("click", loadHistory);
if (sessionId) loadHistory();
else if (!storageAvailable) setStatus("Browser storage is unavailable; this chat will not survive a refresh.");
