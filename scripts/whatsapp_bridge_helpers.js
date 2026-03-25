"use strict";

const path = require("path");

const SENT_MESSAGE_CACHE_TTL_MS = 10 * 60 * 1000;
const DOWNLOADABLE_MEDIA_TYPES = new Set(["image", "document"]);
const TEXT_EQUIVALENT_TYPES = new Set(["interactive", "buttons_response", "list_response"]);

function normalizeWidSerialized(value) {
  if (!value) {
    return "";
  }

  if (typeof value === "string") {
    return value.trim();
  }

  if (typeof value === "object") {
    if (value._serialized) {
      return String(value._serialized).trim();
    }

    const user = String(value.user || "").trim();
    const server = String(value.server || "").trim();
    if (user && server) {
      return `${user}@${server}`;
    }
  }

  return "";
}

function getMessageId(message) {
  if (!message || !message.id) {
    return "";
  }

  if (typeof message.id === "string") {
    return message.id.trim();
  }

  if (typeof message.id === "object" && message.id._serialized) {
    return String(message.id._serialized).trim();
  }

  return "";
}

function normalizeInboundMessageType(rawType, text) {
  const messageType = String(rawType || "chat").trim().toLowerCase() || "chat";
  if (TEXT_EQUIVALENT_TYPES.has(messageType) && String(text || "").trim()) {
    return "chat";
  }
  return messageType;
}

function shouldDownloadInboundMedia(messageType) {
  return DOWNLOADABLE_MEDIA_TYPES.has(String(messageType || "").trim().toLowerCase());
}

function pruneSentMessageIds(cache, now = Date.now()) {
  if (!(cache instanceof Map)) {
    return;
  }

  for (const [messageId, expiresAt] of cache.entries()) {
    if (expiresAt <= now) {
      cache.delete(messageId);
    }
  }
}

function rememberSentMessage(cache, sentMessage, now = Date.now()) {
  if (!(cache instanceof Map) || !sentMessage) {
    return;
  }

  if (Array.isArray(sentMessage)) {
    for (const item of sentMessage) {
      rememberSentMessage(cache, item, now);
    }
    return;
  }

  const messageId = getMessageId(sentMessage);
  if (!messageId) {
    return;
  }

  pruneSentMessageIds(cache, now);
  cache.set(messageId, now + SENT_MESSAGE_CACHE_TTL_MS);
}

function hasRememberedMessage(cache, messageId, now = Date.now()) {
  if (!(cache instanceof Map) || !messageId) {
    return false;
  }

  pruneSentMessageIds(cache, now);
  return cache.has(messageId);
}

async function shouldIgnoreMessage(message, ownWid, sentMessageIds, now = Date.now()) {
  if (!message || !message.fromMe) {
    return false;
  }

  const messageId = getMessageId(message);
  if (messageId && hasRememberedMessage(sentMessageIds, messageId, now)) {
    return true;
  }

  const ownChatId = normalizeWidSerialized(ownWid);
  if (!ownChatId) {
    return true;
  }

  try {
    const chat = typeof message.getChat === "function" ? await message.getChat() : null;
    const chatId = normalizeWidSerialized(chat?.id);
    if (chatId) {
      return chatId !== ownChatId;
    }
  } catch (_error) {
    // Sem contexto do chat, caimos no fallback abaixo.
  }

  const from = normalizeWidSerialized(message.from);
  const to = normalizeWidSerialized(message.to);
  return from !== ownChatId && to !== ownChatId;
}

function getLocalAuthSessionPath(dataPath, clientId) {
  const basePath = String(dataPath || "").trim();
  if (!basePath) {
    return "";
  }

  const normalizedClientId = String(clientId || "").trim();
  const sessionName = normalizedClientId ? `session-${normalizedClientId}` : "session";
  return path.join(basePath, sessionName);
}

function clearLocalAuthSession(dataPath, clientId, fsModule) {
  const sessionPath = getLocalAuthSessionPath(dataPath, clientId);
  if (!sessionPath || !fsModule || typeof fsModule.rmSync !== "function") {
    return "";
  }

  fsModule.rmSync(sessionPath, { recursive: true, force: true });
  return sessionPath;
}

module.exports = {
  clearLocalAuthSession,
  getMessageId,
  getLocalAuthSessionPath,
  normalizeWidSerialized,
  normalizeInboundMessageType,
  rememberSentMessage,
  shouldDownloadInboundMedia,
  shouldIgnoreMessage,
};
