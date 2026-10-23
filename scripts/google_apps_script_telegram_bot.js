/**
 * Google Apps Script Webhook for @UdayPsychRadarBot
 * 
 * Provides an interactive 24/7 Telegram Control Center for Psychologist Uday:
 * - 1-tap toggles for Morning (7 AM), Afternoon (1 PM), Evening (7 PM)
 * - Emergency Pause / Resume button
 * - Instant "Post Next Video Right Now" trigger (via GitHub Actions API)
 * - Live Google Drive Queue status counter
 *
 * 100% Free, runs 24/7 on Google's cloud with ZERO Make.com credit consumption.
 */

const TELEGRAM_BOT_TOKEN = "8905994788:AAE2MAUN8r71Zru97i9CTqMmDrXMiymM49M";
const ALLOWED_CHAT_ID = "6866435263";
const QUEUE_FOLDER_ID = "1XGJ0mGt9-g978Zjvy2wD_9WB3w-CzHDz";
const GITHUB_TOKEN = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN") || "gho_YOUR_GITHUB_TOKEN";
const GITHUB_REPO = "drbairagi8-droid/social-media-automation";

function doPost(e) {
  try {
    const update = JSON.parse(e.postData.contents);

    // 1. Handle incoming text commands (/start, /schedule, /status)
    if (update.message) {
      const chatId = String(update.message.chat.id);
      if (chatId !== ALLOWED_CHAT_ID) {
        sendTelegramMessage(chatId, "⛔ Unauthorized access.");
        return HtmlService.createHtmlOutput("OK");
      }

      const text = (update.message.text || "").trim().toLowerCase();
      if (text.startsWith("/schedule") || text.startsWith("/status") || text.startsWith("/start")) {
        renderDashboard(chatId);
      } else {
        sendTelegramMessage(chatId, "👋 Send /schedule to open your posting control dashboard.");
      }
    }

    // 2. Handle interactive button taps (callback_query)
    if (update.callback_query) {
      const callback = update.callback_query;
      const chatId = String(callback.message.chat.id);
      const messageId = callback.message.message_id;
      const data = callback.data;

      if (chatId !== ALLOWED_CHAT_ID) {
        answerCallbackQuery(callback.id, "Unauthorized.");
        return HtmlService.createHtmlOutput("OK");
      }

      handleCallbackAction(chatId, messageId, callback.id, data);
    }
  } catch (err) {
    Logger.log("Error in doPost: " + err);
  }
  return HtmlService.createHtmlOutput("OK");
}

function handleCallbackAction(chatId, messageId, callbackId, action) {
  let config = getScheduleConfig();
  let alertText = "";

  if (action === "toggle_morning") {
    config.slots.morning.enabled = !config.slots.morning.enabled;
    alertText = "Morning slot is now " + (config.slots.morning.enabled ? "ON 🟢" : "OFF 🔴");
  } else if (action === "toggle_afternoon") {
    config.slots.afternoon.enabled = !config.slots.afternoon.enabled;
    alertText = "Afternoon slot is now " + (config.slots.afternoon.enabled ? "ON 🟢" : "OFF 🔴");
  } else if (action === "toggle_evening") {
    config.slots.evening.enabled = !config.slots.evening.enabled;
    alertText = "Evening slot is now " + (config.slots.evening.enabled ? "ON 🟢" : "OFF 🔴");
  } else if (action === "toggle_all") {
    config.all_posting_enabled = !config.all_posting_enabled;
    alertText = config.all_posting_enabled ? "All postings RESUMED ▶️" : "All postings PAUSED ⏸";
  } else if (action === "trigger_now") {
    alertText = "🚀 Triggering post immediately on GitHub Actions...";
    triggerGitHubPostNow();
  } else if (action === "refresh") {
    alertText = "🔄 Refreshed live status.";
  }

  // Save updated config to Drive
  if (action.startsWith("toggle_")) {
    saveScheduleConfig(config);
  }

  answerCallbackQuery(callbackId, alertText);
  updateDashboardMessage(chatId, messageId, config);
}

function renderDashboard(chatId) {
  const config = getScheduleConfig();
  const queueInfo = getQueueInfo();
  const payload = buildDashboardPayload(config, queueInfo);

  const url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      chat_id: chatId,
      text: payload.text,
      parse_mode: "Markdown",
      reply_markup: payload.reply_markup
    })
  });
}

function updateDashboardMessage(chatId, messageId, config) {
  const queueInfo = getQueueInfo();
  const payload = buildDashboardPayload(config, queueInfo);

  const url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/editMessageText";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      chat_id: chatId,
      message_id: messageId,
      text: payload.text,
      parse_mode: "Markdown",
      reply_markup: payload.reply_markup
    })
  });
}

function buildDashboardPayload(config, queueInfo) {
  const m = config.slots.morning.enabled;
  const a = config.slots.afternoon.enabled;
  const e = config.slots.evening.enabled;
  const all = config.all_posting_enabled;

  const statusEmoji = all ? "🟢 ACTIVE" : "⏸ PAUSED";

  let text = "🎛️ *SOCIAL POSTING CONTROL CENTER*\n";
  text += "━━━━━━━━━━━━━━━━━━━━━━\n";
  text += "⚡ *Master Switch:* " + statusEmoji + "\n";
  text += "📁 *Videos in Queue:* " + queueInfo.count + "\n";
  if (queueInfo.next) {
    text += "🎬 *Next Up:* `" + queueInfo.next + "`\n";
  }
  text += "━━━━━━━━━━━━━━━━━━━━━━\n";
  text += "*Active Daily Slots:*\n";
  text += (m ? "🟢" : "🔴") + " *Morning:* 07:00 AM IST\n";
  text += (a ? "🟢" : "🔴") + " *Afternoon:* 01:00 PM IST\n";
  text += (e ? "🟢" : "🔴") + " *Evening:* 07:00 PM IST\n";

  const keyboard = [
    [
      { text: (m ? "🟢 Morning ON" : "🔴 Morning OFF"), callback_data: "toggle_morning" },
      { text: (a ? "🟢 Afternoon ON" : "🔴 Afternoon OFF"), callback_data: "toggle_afternoon" }
    ],
    [
      { text: (e ? "🟢 Evening ON" : "🔴 Evening OFF"), callback_data: "toggle_evening" },
      { text: (all ? "⏸ Pause All" : "▶️ Resume All"), callback_data: "toggle_all" }
    ],
    [
      { text: "🚀 Post Next Video Right Now", callback_data: "trigger_now" }
    ],
    [
      { text: "🔄 Refresh Status", callback_data: "refresh" }
    ]
  ];

  return { text: text, reply_markup: { inline_keyboard: keyboard } };
}

function getScheduleConfig() {
  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFilesByName("schedule_config.json");
  if (files.hasNext()) {
    const file = files.next();
    try {
      return JSON.parse(file.getBlob().getDataAsString());
    } catch (e) {}
  }
  return {
    all_posting_enabled: true,
    slots: {
      morning: { enabled: true, name: "Morning (07:00 AM IST)" },
      afternoon: { enabled: true, name: "Afternoon (01:00 PM IST)" },
      evening: { enabled: true, name: "Evening (07:00 PM IST)" }
    }
  };
}

function saveScheduleConfig(config) {
  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFilesByName("schedule_config.json");
  const jsonString = JSON.stringify(config, null, 2);
  if (files.hasNext()) {
    files.next().setContent(jsonString);
  } else {
    folder.createFile("schedule_config.json", jsonString, "application/json");
  }
}

function getQueueInfo() {
  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFiles();
  let count = 0;
  let nextFile = "";

  while (files.hasNext()) {
    const file = files.next();
    const name = file.getName();
    if (name.toLowerCase().endsWith(".mp4") || name.toLowerCase().endsWith(".mov")) {
      count++;
      if (!nextFile) {
        nextFile = name;
      }
    }
  }
  return { count: count, next: nextFile };
}

function triggerGitHubPostNow() {
  const url = "https://api.github.com/repos/" + GITHUB_REPO + "/actions/workflows/daily_poster.yml/dispatches";
  const payload = {
    ref: "main",
    inputs: {
      platform: "all",
      force: true
    }
  };

  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      "Authorization": "Bearer " + GITHUB_TOKEN,
      "Accept": "application/vnd.github.v3+json",
      "User-Agent": "Google-Apps-Script"
    },
    payload: JSON.stringify(payload)
  });
}

function sendTelegramMessage(chatId, text) {
  UrlFetchApp.fetch("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage", {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ chat_id: chatId, text: text })
  });
}

function answerCallbackQuery(callbackId, text) {
  UrlFetchApp.fetch("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/answerCallbackQuery", {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ callback_query_id: callbackId, text: text })
  });
}
