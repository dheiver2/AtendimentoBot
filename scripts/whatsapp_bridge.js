"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

require("dotenv").config({ path: path.resolve(__dirname, "..", ".env") });

const qrcode = require("qrcode-terminal");
const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const {
  clearLocalAuthSession,
  getMessageId,
  normalizeInboundMessageType,
  normalizeWidSerialized,
  rememberSentMessage,
  shouldDownloadInboundMedia,
  shouldIgnoreMessage,
} = require("./whatsapp_bridge_helpers");

const ROOT_DIR = path.resolve(__dirname, "..");
const DEFAULT_SESSION_DIR = path.join(ROOT_DIR, "data", "whatsapp-web-session");

function isTruthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function normalizePath(value, fallback) {
  const base = String(value || fallback || "").trim() || fallback;
  if (!base.startsWith("/")) {
    return `/${base}`;
  }
  return base.replace(/\/+$/, "") || "/";
}

function normalizeLocalHost(value) {
  const host = String(value || "").trim();
  if (!host || host === "0.0.0.0" || host === "::") {
    return "127.0.0.1";
  }
  return host;
}

function resolvePath(value, fallback) {
  const raw = String(value || fallback || "").trim() || fallback;
  if (path.isAbsolute(raw)) {
    return raw;
  }
  return path.resolve(ROOT_DIR, raw);
}

if (!isTruthy(process.env.WHATSAPP_WEB_ENABLED || "1")) {
  console.error("WHATSAPP_WEB_ENABLED precisa estar ativo para iniciar o bridge do WhatsApp.");
  process.exit(1);
}

const bridgeHost = normalizeLocalHost(process.env.WHATSAPP_WEB_BRIDGE_HOST || "127.0.0.1");
const bridgePort = Number.parseInt(process.env.WHATSAPP_WEB_BRIDGE_PORT || "8010", 10);
const bridgePath = normalizePath(
  process.env.WHATSAPP_WEB_BRIDGE_PATH,
  "/bridge/whatsapp/message",
);
const bridgeToken = String(process.env.WHATSAPP_WEB_BRIDGE_TOKEN || "").trim();
const statusHost = normalizeLocalHost(process.env.WHATSAPP_WEB_CLIENT_HOST || "127.0.0.1");
const statusPort = Number.parseInt(process.env.WHATSAPP_WEB_CLIENT_PORT || "8011", 10);
const statusPath = normalizePath(process.env.WHATSAPP_WEB_CLIENT_HEALTH_PATH, "/health");
const clientId = String(process.env.WHATSAPP_WEB_CLIENT_ID || "atendimento-bot").trim() || "atendimento-bot";
const sessionDir = resolvePath(process.env.WHATSAPP_WEB_SESSION_DIR, DEFAULT_SESSION_DIR);
const forceNewQr = isTruthy(process.env.WHATSAPP_WEB_FORCE_NEW_QR);
const bridgeHealthUrl = new URL("/health", `http://${bridgeHost}:${bridgePort}${bridgePath}`).toString();
const BRIDGE_HEALTH_TIMEOUT_MS = 5000;

if (forceNewQr) {
  const clearedSessionPath = clearLocalAuthSession(sessionDir, clientId, fs);
  if (clearedSessionPath) {
    console.log(`Sessao anterior removida para forcar novo QR Code: ${clearedSessionPath}`);
  }
}

fs.mkdirSync(sessionDir, { recursive: true });

let state = "starting";
let lastError = "";
let lastQrAt = null;
let lastReadyAt = null;
const sentMessageIds = new Map();

function statusPayload() {
  return {
    ok: true,
    state,
    lastError,
    lastQrAt,
    lastReadyAt,
    bridgeUrl: `http://${bridgeHost}:${bridgePort}${bridgePath}`,
    sessionDir,
    clientId,
    forceNewQr,
    ownNumber: client.info?.wid?.user || null,
  };
}

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  response.end(body);
}

const statusServer = http.createServer((request, response) => {
  if (request.method !== "GET" || normalizePath(request.url, "/") !== statusPath) {
    sendJson(response, 404, { ok: false, error: "Endpoint nao encontrado." });
    return;
  }
  sendJson(response, 200, statusPayload());
});

statusServer.listen(statusPort, statusHost, () => {
  console.log(`Status local do WhatsApp em http://${statusHost}:${statusPort}${statusPath}`);
});

const client = new Client({
  authStrategy: new LocalAuth({
    clientId,
    dataPath: sessionDir,
  }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

async function buildPayload(message) {
  let sender = String(message.from || "").trim();
  const text = String(message.body || "").trim();
  const messageType = normalizeInboundMessageType(message.type, text);
  const ownChatId = normalizeWidSerialized(client.info?.wid);
  try {
    const chat = typeof message.getChat === "function" ? await message.getChat() : null;
    const chatId = normalizeWidSerialized(chat?.id);
    if (chatId) {
      sender = chatId;
    }
  } catch (_error) {
    // Mantem o sender original quando o chat nao puder ser resolvido.
  }

  const payload = {
    sender,
    message_id: getMessageId(message),
    text,
    message_type: messageType,
    is_owner_chat: Boolean(ownChatId && sender === ownChatId),
    mime_type: "",
    file_name: "",
    media_base64: "",
  };

  if (!message.hasMedia || !shouldDownloadInboundMedia(messageType)) {
    return payload;
  }

  let media = null;
  try {
    media = await message.downloadMedia();
  } catch (error) {
    console.warn(
      `Nao foi possivel baixar a midia da mensagem ${getMessageId(message) || "<sem-id>"} `
      + `(${messageType}). O bridge vai continuar sem anexo.`,
      error,
    );
    return payload;
  }

  if (!media) {
    return payload;
  }

  payload.mime_type = String(media.mimetype || "");
  payload.file_name = String(media.filename || "");
  payload.media_base64 = String(media.data || "");
  return payload;
}

async function checkPythonBridgeHealth() {
  try {
    const response = await fetch(bridgeHealthUrl, {
      method: "GET",
      signal: AbortSignal.timeout(BRIDGE_HEALTH_TIMEOUT_MS),
    });
    if (!response.ok) {
      lastError = `Bridge Python indisponivel em ${bridgeHealthUrl} (HTTP ${response.status}).`;
      return false;
    }

    lastError = "";
    return true;
  } catch (error) {
    lastError = (
      `Bridge Python indisponivel em ${bridgeHealthUrl}: `
      + `${error instanceof Error ? error.message : String(error)}`
    );
    return false;
  }
}

async function sendActions(message, actions) {
  if (!Array.isArray(actions) || !actions.length) {
    return;
  }

  const chat = await message.getChat();
  for (const action of actions) {
    if (!action || typeof action !== "object") {
      continue;
    }

    if (action.type === "text") {
      const text = String(action.text || "").trim();
      if (!text) {
        continue;
      }
      const sentMessage = await chat.sendMessage(text, {
        quotedMessageId: getMessageId(message) || undefined,
      });
      rememberSentMessage(sentMessageIds, sentMessage);
      continue;
    }

    if (action.type === "image") {
      const mediaBase64 = String(action.media_base64 || "");
      const mimeType = String(action.mime_type || "image/jpeg");
      if (!mediaBase64) {
        continue;
      }
      const media = new MessageMedia(
        mimeType,
        mediaBase64,
        String(action.filename || "imagem.jpg"),
      );
      const sentMessage = await chat.sendMessage(media, {
        caption: String(action.caption || ""),
        quotedMessageId: getMessageId(message) || undefined,
      });
      rememberSentMessage(sentMessageIds, sentMessage);
    }
  }
}

async function replyUnsupported(message) {
  try {
    const sentMessage = await message.reply("No momento eu consigo responder apenas mensagens de texto.");
    rememberSentMessage(sentMessageIds, sentMessage);
  } catch (error) {
    console.error("Falha ao responder mensagem nao suportada:", error);
  }
}

async function onMessage(message) {
  if (!message.from || message.from === "status@broadcast") {
    return;
  }

  if (
    message.from.endsWith("@g.us")
    || message.from.endsWith("@newsletter")
    || message.from.endsWith("@broadcast")
  ) {
    return;
  }

  if (await shouldIgnoreMessage(message, client.info?.wid, sentMessageIds)) {
    return;
  }

  try {
    const response = await fetch(`http://${bridgeHost}:${bridgePort}${bridgePath}`, {
      method: "POST",
      headers: bridgeToken
        ? {
            "Content-Type": "application/json",
            Authorization: `Bearer ${bridgeToken}`,
          }
        : { "Content-Type": "application/json" },
      body: JSON.stringify(await buildPayload(message)),
      signal: AbortSignal.timeout(120000),
    });

    if (!response.ok) {
      throw new Error(`Bridge respondeu com HTTP ${response.status}`);
    }

    const payload = await response.json();
    const actions = Array.isArray(payload.actions) ? payload.actions : [];
    if (actions.length) {
      await sendActions(message, actions);
      return;
    }

    const reply = String(payload.reply || "").trim();
    if (reply) {
      await sendActions(message, [{ type: "text", text: reply }]);
      return;
    }

    if (message.type !== "chat" && !message.hasMedia) {
      await replyUnsupported(message);
    }
  } catch (error) {
    lastError = error instanceof Error ? error.message : String(error);
    console.error("Falha ao encaminhar mensagem para o bridge Python:", error);
  }
}

client.on("qr", (qr) => {
  state = "qr";
  lastQrAt = new Date().toISOString();
  lastError = "";
  console.clear();
  console.log("Escaneie o QR code abaixo no WhatsApp para conectar o atendimento:");
  console.log("");
  qrcode.generate(qr, { small: true });
  console.log("");
  console.log("Mantenha este terminal aberto. O main continua em outro terminal.");
});

client.on("authenticated", () => {
  state = "authenticated";
  lastError = "";
  console.log("WhatsApp autenticado. Aguardando sincronizacao...");
});

client.on("ready", () => {
  state = "ready";
  lastReadyAt = new Date().toISOString();
  void checkPythonBridgeHealth()
    .then((bridgeReady) => {
      if (bridgeReady) {
        console.log("WhatsApp pronto para atender mensagens.");
        return;
      }

      console.error(
        "WhatsApp conectado, mas o bridge Python nao respondeu. "
        + "As mensagens nao serao atendidas ate o main ficar ativo.",
      );
      console.error(`Verifique o outro terminal do main e o endpoint ${bridgeHealthUrl}.`);
    })
    .catch((error) => {
      lastError = error instanceof Error ? error.message : String(error);
      console.error("Falha ao validar o bridge Python apos conectar o WhatsApp:", error);
    });
});

client.on("auth_failure", (message) => {
  state = "auth_failure";
  lastError = String(message || "Falha de autenticacao.");
  console.error("Falha de autenticacao do WhatsApp:", lastError);
});

client.on("disconnected", (reason) => {
  state = "disconnected";
  lastError = String(reason || "Sessao desconectada.");
  console.error("WhatsApp desconectado:", lastError);
});

client.on("message", onMessage);

async function shutdown(signal) {
  console.log(`Encerrando bridge do WhatsApp (${signal})...`);
  state = "stopping";
  statusServer.close();
  try {
    await client.destroy();
  } catch (error) {
    console.error("Falha ao encerrar cliente do WhatsApp:", error);
  }
  process.exit(0);
}

process.on("SIGINT", () => {
  shutdown("SIGINT").catch((error) => {
    console.error(error);
    process.exit(1);
  });
});

process.on("SIGTERM", () => {
  shutdown("SIGTERM").catch((error) => {
    console.error(error);
    process.exit(1);
  });
});

client.initialize().catch((error) => {
  lastError = error instanceof Error ? error.message : String(error);
  console.error("Falha ao inicializar o WhatsApp Web:", error);
  process.exit(1);
});
