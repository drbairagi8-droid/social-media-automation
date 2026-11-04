/**
 * Google Apps Script Webhook for @UdayPsychRadarBot
 *
 * Provides an interactive 24/7 Telegram Control Center for Psychologist Uday:
 * - 1-tap toggles for Morning (06:00 AM), Afternoon (12:00 PM), Evening (05:30 PM)
 * - Interactive Video Slot Manager: assign any queued video to Morning, Afternoon, Evening, or Auto
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
    // Dynamic remote override hook: allows future bot updates directly via Google Drive without redeploying
    const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
    const remoteFiles = folder.getFilesByName("telegram_bot_remote.js");
    if (remoteFiles.hasNext()) {
      eval(remoteFiles.next().getBlob().getDataAsString());
      if (typeof handleRemotePost === "function") {
        return handleRemotePost(e);
      }
    }

    const update = JSON.parse(e.postData.contents);

    // 1. Handle incoming text commands (/start, /schedule, /status, /slots)
    if (update.message) {
      const chatId = String(update.message.chat.id);
      if (chatId !== ALLOWED_CHAT_ID) {
        sendTelegramMessage(chatId, "⛔ Unauthorized access.");
        return HtmlService.createHtmlOutput("OK");
      }

      const text = (update.message.text || "").trim().toLowerCase();
      if (text.startsWith("/slots")) {
        renderSlotsMenu(chatId);
      } else if (text.startsWith("/schedule") || text.startsWith("/status") || text.startsWith("/start")) {
        renderDashboard(chatId);
      } else {
        sendTelegramMessage(chatId, "👋 Send /schedule to open your posting control dashboard, or /slots to assign videos to Morning, Afternoon, or Evening.");
      }
    }

    // 2. Handle interactive button taps (callback_query)
    if (update.callback_query) {
      const callback = update.callback_query;
      const chatId = String(callback.message.chat.id);
      const messageId = callback.message.message_id;
      const data = callback.data || "";

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
  if (!config.video_slots) {
    config.video_slots = {};
  }
  let alertText = "";
  let view = "main";

  if (action === "toggle_morning") {
    config.slots.morning.enabled = !config.slots.morning.enabled;
    alertText = "Morning slot is now " + (config.slots.morning.enabled ? "ON 🟢" : "OFF 🔴");
    saveScheduleConfig(config);
  } else if (action === "toggle_afternoon") {
    config.slots.afternoon.enabled = !config.slots.afternoon.enabled;
    alertText = "Afternoon slot is now " + (config.slots.afternoon.enabled ? "ON 🟢" : "OFF 🔴");
    saveScheduleConfig(config);
  } else if (action === "toggle_evening") {
    config.slots.evening.enabled = !config.slots.evening.enabled;
    alertText = "Evening slot is now " + (config.slots.evening.enabled ? "ON 🟢" : "OFF 🔴");
    saveScheduleConfig(config);
  } else if (action === "toggle_all") {
    config.all_posting_enabled = !config.all_posting_enabled;
    alertText = config.all_posting_enabled ? "All postings RESUMED ▶️" : "All postings PAUSED ⏸";
    saveScheduleConfig(config);
  } else if (action === "trigger_now") {
    alertText = "🚀 Triggering post immediately on GitHub Actions...";
    triggerGitHubPostNow();
  } else if (action === "refresh") {
    alertText = "🔄 Refreshed live status.";
  } else if (action === "menu_slots") {
    alertText = "🎯 Opening Video Slot Manager...";
    view = "slots";
  } else if (action === "back_main") {
    alertText = "⬅️ Back to Control Center";
    view = "main";
  } else if (action.indexOf("s:") === 0) {
    // Format: s:<m|a|e|u>:<fileId>
    const parts = action.split(":");
    const slotCode = parts[1];
    const fileId = parts.slice(2).join(":");
    if (slotCode === "m") {
      config.video_slots[fileId] = "morning";
      alertText = "🌅 Assigned to Morning (06:00 AM IST)";
    } else if (slotCode === "a") {
      config.video_slots[fileId] = "afternoon";
      alertText = "☀️ Assigned to Afternoon (12:00 PM IST)";
    } else if (slotCode === "e") {
      config.video_slots[fileId] = "evening";
      alertText = "🌙 Assigned to Evening (05:30 PM IST)";
    } else {
      delete config.video_slots[fileId];
      alertText = "🔄 Set to Auto Queue (any open slot)";
    }
    saveScheduleConfig(config);
    view = "slots";
  }

  answerCallbackQuery(callbackId, alertText);
  if (view === "slots") {
    updateSlotsMessage(chatId, messageId, config);
  } else {
    updateDashboardMessage(chatId, messageId, config);
  }
}

function renderDashboard(chatId) {
  const config = getScheduleConfig();
  const queueInfo = getQueueInfo(config);
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

function renderSlotsMenu(chatId) {
  const config = getScheduleConfig();
  const queueInfo = getQueueInfo(config);
  const payload = buildSlotsPayload(config, queueInfo);

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
  const queueInfo = getQueueInfo(config);
  const payload = buildDashboardPayload(config, queueInfo);

  const url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/editMessageText";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    muteHttpExceptions: true,
    payload: JSON.stringify({
      chat_id: chatId,
      message_id: messageId,
      text: payload.text,
      parse_mode: "Markdown",
      reply_markup: payload.reply_markup
    })
  });
}

function updateSlotsMessage(chatId, messageId, config) {
  const queueInfo = getQueueInfo(config);
  const payload = buildSlotsPayload(config, queueInfo);

  const url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/editMessageText";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    muteHttpExceptions: true,
    payload: JSON.stringify({
      chat_id: chatId,
      message_id: messageId,
      text: payload.text,
      parse_mode: "Markdown",
      reply_markup: payload.reply_markup
    })
  });
}

function findNextVideoForSlot(files, videoSlots, targetSlot) {
  for (let i = 0; i < files.length; i++) {
    if (videoSlots[files[i].id] === targetSlot) {
      return "📌 `" + files[i].name + "`";
    }
  }
  for (let i = 0; i < files.length; i++) {
    if (!videoSlots[files[i].id]) {
      return "🔄 `" + files[i].name + "` _(Auto)_";
    }
  }
  return "_None queued_";
}

function buildDashboardPayload(config, queueInfo) {
  const m = config.slots.morning.enabled;
  const a = config.slots.afternoon.enabled;
  const e = config.slots.evening.enabled;
  const all = config.all_posting_enabled;
  const videoSlots = config.video_slots || {};

  const statusEmoji = all ? "🟢 ACTIVE" : "⏸ PAUSED";

  let text = "🎛️ *SOCIAL POSTING CONTROL CENTER*\n";
  text += "━━━━━━━━━━━━━━━━━━━━━━\n";
  text += "⚡ *Master Switch:* " + statusEmoji + "\n";
  text += "📁 *Videos in Queue:* " + queueInfo.count + "\n";
  text += "━━━━━━━━━━━━━━━━━━━━━━\n";
  text += "*Active Daily Slots & Lineup:*\n";
  text += (m ? "🟢" : "🔴") + " *Morning (06:00 AM IST)*\n";
  text += "   ↳ " + findNextVideoForSlot(queueInfo.files, videoSlots, "morning") + "\n";
  text += (a ? "🟢" : "🔴") + " *Afternoon (12:00 PM IST)*\n";
  text += "   ↳ " + findNextVideoForSlot(queueInfo.files, videoSlots, "afternoon") + "\n";
  text += (e ? "🟢" : "🔴") + " *Evening (05:30 PM IST)*\n";
  text += "   ↳ " + findNextVideoForSlot(queueInfo.files, videoSlots, "evening") + "\n";

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
      { text: "🎯 Assign Video Slots (" + queueInfo.count + " in Queue)", callback_data: "menu_slots" }
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

function buildSlotsPayload(config, queueInfo) {
  const videoSlots = config.video_slots || {};
  const files = queueInfo.files;

  let text = "🎯 *VIDEO SLOT MANAGER*\n";
  text += "━━━━━━━━━━━━━━━━━━━━━━\n";

  const keyboard = [];

  if (files.length === 0) {
    text += "📭 *Your Google Drive Queue is currently empty.*\n\n";
    text += "Upload `.mp4` videos into your `Social Queue` folder on Google Drive, then tap *Refresh* below to assign them to Morning, Afternoon, or Evening.";
  } else {
    text += "Tap a button under any video to lock it to *Morning (6:00 AM)*, *Afternoon (12:00 PM)*, *Evening (5:30 PM)*, or leave it on *Auto*:\n\n";
    const maxDisplay = Math.min(files.length, 8);
    for (let i = 0; i < maxDisplay; i++) {
      const f = files[i];
      const num = i + 1;
      const current = videoSlots[f.id] || "auto";
      let badge = "🔄 Auto (Any Open Slot)";
      if (current === "morning") badge = "🌅 Morning (06:00 AM IST)";
      if (current === "afternoon") badge = "☀️ Afternoon (12:00 PM IST)";
      if (current === "evening") badge = "🌙 Evening (05:30 PM IST)";

      text += "*" + num + ".* `" + f.name + "`\n";
      text += "   ↳ Slot: *" + badge + "*\n\n";

      keyboard.push([
        {
          text: (current === "morning" ? "✅ " : "") + num + " 🌅 Morn",
          callback_data: "s:m:" + f.id
        },
        {
          text: (current === "afternoon" ? "✅ " : "") + num + " ☀️ Aft",
          callback_data: "s:a:" + f.id
        },
        {
          text: (current === "evening" ? "✅ " : "") + num + " 🌙 Eve",
          callback_data: "s:e:" + f.id
        },
        {
          text: (current === "auto" ? "✅ " : "") + num + " 🔄 Auto",
          callback_data: "s:u:" + f.id
        }
      ]);
    }
  }

  keyboard.push([
    { text: "🔄 Refresh Queue", callback_data: "menu_slots" },
    { text: "⬅️ Back to Dashboard", callback_data: "back_main" }
  ]);

  return { text: text, reply_markup: { inline_keyboard: keyboard } };
}

function getScheduleConfig() {
  const defaultCfg = {
    all_posting_enabled: true,
    slots: {
      morning: { enabled: true, name: "Morning (06:00 AM IST)" },
      afternoon: { enabled: true, name: "Afternoon (12:00 PM IST)" },
      evening: { enabled: true, name: "Evening (05:30 PM IST)" }
    },
    video_slots: {}
  };
  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFilesByName("schedule_config.json");
  if (files.hasNext()) {
    const file = files.next();
    try {
      const parsed = JSON.parse(file.getBlob().getDataAsString());
      if (!parsed.video_slots) parsed.video_slots = {};
      if (parsed.slots) {
        if (parsed.slots.morning) parsed.slots.morning.name = "Morning (06:00 AM IST)";
        if (parsed.slots.afternoon) parsed.slots.afternoon.name = "Afternoon (12:00 PM IST)";
        if (parsed.slots.evening) parsed.slots.evening.name = "Evening (05:30 PM IST)";
      }
      return parsed;
    } catch (e) {}
  }
  return defaultCfg;
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

function getQueueInfo(config) {
  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFiles();
  const videoList = [];

  while (files.hasNext()) {
    const file = files.next();
    const name = file.getName();
    const lower = name.toLowerCase();
    if (lower.endsWith(".mp4") || lower.endsWith(".mov")) {
      videoList.push({
        id: file.getId(),
        name: name,
        created: file.getDateCreated().getTime()
      });
    }
  }

  // Sort oldest first (matching Python createdTime asc, name asc)
  videoList.sort(function(a, b) {
    if (a.created !== b.created) return a.created - b.created;
    return a.name.localeCompare(b.name);
  });

  // Clean up any archived/deleted file IDs from video_slots
  if (config && config.video_slots) {
    const activeIds = {};
    for (let i = 0; i < videoList.length; i++) {
      activeIds[videoList[i].id] = true;
    }
    let changed = false;
    const savedIds = Object.keys(config.video_slots);
    for (let j = 0; j < savedIds.length; j++) {
      if (!activeIds[savedIds[j]]) {
        delete config.video_slots[savedIds[j]];
        changed = true;
      }
    }
    if (changed) {
      saveScheduleConfig(config);
    }
  }

  return {
    count: videoList.length,
    next: videoList.length > 0 ? videoList[0].name : "",
    files: videoList
  };
}

function triggerGitHubPostNow() {
  const url = "https://api.github.com/repos/" + GITHUB_REPO + "/actions/workflows/daily_poster.yml/dispatches";
  UrlFetchApp.fetch(url, {
    method: "post",
    headers: {
      "Authorization": "Bearer " + GITHUB_TOKEN,
      "Accept": "application/vnd.github.v3+json",
      "User-Agent": "PsychologistUday-TelegramBot"
    },
    contentType: "application/json",
    muteHttpExceptions: true,
    payload: JSON.stringify({
      ref: "main",
      inputs: {
        platform: "all",
        dry_run: false,
        force: true
      }
    })
  });
}

function sendTelegramMessage(chatId, text) {
  const url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      chat_id: chatId,
      text: text,
      parse_mode: "Markdown"
    })
  });
}

function answerCallbackQuery(callbackId, text) {
  const url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/answerCallbackQuery";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      callback_query_id: callbackId,
      text: text
    })
  });
}
