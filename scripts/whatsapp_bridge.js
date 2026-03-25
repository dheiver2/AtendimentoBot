"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

require("dotenv").config({ path: path.resolve(__dirname, "..", ".env") });

const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

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

fs.mkdirSync(sessionDir, { recursive: true });

let state = "starting";
let lastError = "";
let lastQrAt = null;
let lastReadyAt = null;

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

async function askPythonBridge(message) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (bridgeToken) {
    headers.Authorization = `Bearer ${bridgeToken}`;
  }

  const response = await fetch(`http://${bridgeHost}:${bridgePort}${bridgePath}`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      sender: message.from,
      message_id: message.id?._serialized || "",
      text: String(message.body || "").trim(),
    }),
    signal: AbortSignal.timeout(120000),
  });

  if (!response.ok) {
    throw new Error(`Bridge respondeu com HTTP ${response.status}`);
  }

  const payload = await response.json();
  return String(payload.reply || "").trim();
}

async function replyUnsupported(message) {
  try {
    await message.reply("No momento eu consigo responder apenas mensagens de texto.");
  } catch (error) {
    console.error("Falha ao responder mensagem nao suportada:", error);
  }
}

async function onMessage(message) {
  if (message.fromMe) {
    return;
  }

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

  const text = String(message.body || "").trim();
  if (!text) {
    if (message.type !== "chat") {
      await replyUnsupported(message);
    }
    return;
  }

  try {
    const reply = await askPythonBridge(message);
    if (!reply) {
      return;
    }
    await message.reply(reply);
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
  lastError = "";
  console.log("WhatsApp pronto para atender mensagens.");
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
