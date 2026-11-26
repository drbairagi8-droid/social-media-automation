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
    return handleCorePost(e);
  } catch (err) {
    Logger.log("Error in doPost: " + err);
  }
  return HtmlService.createHtmlOutput("OK");
}

function handleRemotePost(e) {
  return handleCorePost(e);
}
this.handleRemotePost = handleRemotePost;

function handleCorePost(e) {
  try {
    // If invoked by Google Apps Script's 15-minute Time-Driven Trigger (no postData), run exact schedule check
    if (!e || !e.postData || !e.postData.contents) {
      const statusMsg = runExactScheduleCheck();
      Logger.log("[EXACT SCHEDULER] " + statusMsg);
      return null;
    }

    const update = JSON.parse(e.postData.contents);
    if (update.internal_action === "health_check") {
      const config = getScheduleConfig();
      const history = getPostHistory();
      const queueInfo = getQueueInfo(null);
      const nowUtcMs = new Date().getTime();
      const istDateObj = new Date(nowUtcMs + (5.5 * 3600 * 1000));
      const istTime = istDateObj.getUTCFullYear() + "-" +
        String(istDateObj.getUTCMonth() + 1).padStart(2, "0") + "-" +
        String(istDateObj.getUTCDate()).padStart(2, "0") + " " +
        String(istDateObj.getUTCHours()).padStart(2, "0") + ":" +
        String(istDateObj.getUTCMinutes()).padStart(2, "0") + " IST";
      return ContentService.createTextOutput(JSON.stringify({
        ok: true,
        ist_time: istTime,
        queue_count: queueInfo.count,
        slots: config.slots || {},
        posted_slots_by_date: history.posted_slots_by_date || {},
        dispatched_slots_by_date: history.dispatched_slots_by_date || {}
      })).setMimeType(ContentService.MimeType.JSON);
    }
    if (update.internal_action === "install_exact_triggers") {
      let trigMsg = "";
      try {
        trigMsg = installExactScheduleTrigger(true);
      } catch (te) {
        trigMsg = "Trigger install error (likely missing ScriptApp scope): " + String(te);
      }
      let checkMsg = "";
      try {
        checkMsg = runExactScheduleCheck();
      } catch (ce) {
        checkMsg = "Schedule check error: " + String(ce);
      }
      return ContentService.createTextOutput(JSON.stringify({ ok: true, trigger: trigMsg, check: checkMsg })).setMimeType(ContentService.MimeType.JSON);
    }
    if (update.internal_action === "run_exact_check") {
      const checkMsg = runExactScheduleCheck();
      return ContentService.createTextOutput(JSON.stringify({ ok: true, check: checkMsg })).setMimeType(ContentService.MimeType.JSON);
    }

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
    Logger.log("Error in handleCorePost: " + err);
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
  // Keep schedule_config.json strictly for user settings; post/dispatch history lives in post_history.json
  const cleanConfig = JSON.parse(JSON.stringify(config || {}));
  delete cleanConfig.posted_slots_by_date;
  delete cleanConfig.dispatched_slots_by_date;

  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFilesByName("schedule_config.json");
  const jsonString = JSON.stringify(cleanConfig, null, 2);
  if (files.hasNext()) {
    files.next().setContent(jsonString);
  } else {
    folder.createFile("schedule_config.json", jsonString, "application/json");
  }
}

function getPostHistory() {
  const defaultHistory = {
    posted_slots_by_date: {},
    dispatched_slots_by_date: {}
  };
  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFilesByName("post_history.json");
  if (files.hasNext()) {
    const file = files.next();
    try {
      const parsed = JSON.parse(file.getBlob().getDataAsString());
      if (!parsed.posted_slots_by_date) parsed.posted_slots_by_date = {};
      if (!parsed.dispatched_slots_by_date) parsed.dispatched_slots_by_date = {};
      return parsed;
    } catch (e) {}
  }
  return defaultHistory;
}

function savePostHistory(history) {
  const folder = DriveApp.getFolderById(QUEUE_FOLDER_ID);
  const files = folder.getFilesByName("post_history.json");
  const jsonString = JSON.stringify(history, null, 2);
  if (files.hasNext()) {
    files.next().setContent(jsonString);
  } else {
    folder.createFile("post_history.json", jsonString, "application/json");
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
  triggerGitHubWorkflowDispatch(true, "");
}

function triggerGitHubWorkflowDispatch(forceFlag, slotKey) {
  const url = "https://api.github.com/repos/" + GITHUB_REPO + "/actions/workflows/daily_poster.yml/dispatches";
  const inputs = {
    platform: "all",
    dry_run: false,
    force: Boolean(forceFlag)
  };
  if (slotKey) {
    inputs.slot = String(slotKey);
  }
  const resp = UrlFetchApp.fetch(url, {
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
      inputs: inputs
    })
  });
  return resp.getResponseCode();
}

/**
 * Exact-Time Google Apps Script Scheduler:
 * Runs every 15 minutes via Google's Time-Driven Trigger to eliminate GitHub Actions' 1-8h cron delays.
 * Because doPost() exists in the top-level deployed script, the time-driven trigger calls doPost()
 * with no arguments, which automatically delegates into telegram_bot_remote.js -> runExactScheduleCheck()!
 */
function ensureExactScheduleTriggerInstalled() {
  try {
    const props = PropertiesService.getScriptProperties();
    if (props.getProperty("EXACT_SCHEDULE_TRIGGER_V1") === "installed") {
      return;
    }
    installExactScheduleTrigger(false);
  } catch (err) {
    Logger.log("Could not verify/install exact schedule trigger: " + err);
  }
}

function installExactScheduleTrigger(forceReinstall) {
  const triggers = ScriptApp.getProjectTriggers();
  let found = false;
  for (let i = 0; i < triggers.length; i++) {
    const fn = triggers[i].getHandlerFunction();
    if (fn === "doPost") {
      if (forceReinstall) {
        ScriptApp.deleteTrigger(triggers[i]);
      } else {
        found = true;
      }
    }
  }
  if (!found || forceReinstall) {
    ScriptApp.newTrigger("doPost")
      .timeBased()
      .everyMinutes(15)
      .create();
  }
  PropertiesService.getScriptProperties().setProperty("EXACT_SCHEDULE_TRIGGER_V1", "installed");
  return "Installed 15-minute exact-time schedule trigger on doPost.";
}

function runExactScheduleCheck() {
  const config = getScheduleConfig();
  if (!config.all_posting_enabled) {
    return "Paused (all_posting_enabled=false)";
  }

  // Compute current IST date and hour/minute
  const nowUtcMs = new Date().getTime();
  const istDateObj = new Date(nowUtcMs + (5.5 * 3600 * 1000));
  const yyyy = istDateObj.getUTCFullYear();
  const mm = String(istDateObj.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(istDateObj.getUTCDate()).padStart(2, "0");
  const todayIst = yyyy + "-" + mm + "-" + dd;
  const hour = istDateObj.getUTCHours();
  const minute = istDateObj.getUTCMinutes();
  const totalMinutes = hour * 60 + minute;

  // Hard late-night blackout window (10:00 PM - 05:45 AM IST)
  if (totalMinutes >= 22 * 60 || totalMinutes < 5 * 60 + 45) {
    return "Late-night blackout (" + hour + ":" + minute + " IST)";
  }

  // Determine which slot should be active right now:
  // Morning:   05:55 AM - 10:45 AM IST (355 - 645 mins)
  // Afternoon: 11:55 AM - 03:45 PM IST (715 - 945 mins)
  // Evening:   05:25 PM - 09:45 PM IST (1045 - 1305 mins)
  let targetSlot = "";
  if (totalMinutes >= 355 && totalMinutes <= 645) {
    targetSlot = "morning";
  } else if (totalMinutes >= 715 && totalMinutes <= 945) {
    targetSlot = "afternoon";
  } else if (totalMinutes >= 1045 && totalMinutes <= 1305) {
    targetSlot = "evening";
  } else {
    return "Outside posting slot windows (" + hour + ":" + minute + " IST)";
  }

  const history = getPostHistory();
  const historyPostedMap = history.posted_slots_by_date || {};
  const legacyPostedMap = config.posted_slots_by_date || {};
  const historyToday = Array.isArray(historyPostedMap[todayIst]) ? historyPostedMap[todayIst] : [];
  const legacyToday = Array.isArray(legacyPostedMap[todayIst]) ? legacyPostedMap[todayIst] : [];
  const postedToday = historyToday.slice();
  for (let i = 0; i < legacyToday.length; i++) {
    if (postedToday.indexOf(legacyToday[i]) === -1) {
      postedToday.push(legacyToday[i]);
    }
  }

  const slots = config.slots || {};
  const isSlotOn = function(k) {
    return slots[k] && slots[k].enabled === true;
  };

  // Smart Catch-Up: if we are in the Afternoon window and Afternoon is OFF, check if Morning was missed today
  if (targetSlot === "afternoon" && (!isSlotOn("afternoon") || postedToday.indexOf("afternoon") !== -1)) {
    if (isSlotOn("morning") && postedToday.indexOf("morning") === -1) {
      targetSlot = "morning";
    }
  }

  if (!isSlotOn(targetSlot)) {
    return "Slot " + targetSlot + " is OFF";
  }
  if (postedToday.indexOf(targetSlot) !== -1) {
    return "Slot " + targetSlot + " already posted on " + todayIst;
  }

  // Prevent hammering GitHub workflow_dispatch while a run is already in progress (cooldown: 25 mins)
  const dispatchedByDate = history.dispatched_slots_by_date || {};
  const dayDispatches = dispatchedByDate[todayIst] || {};
  const lastDispatchMs = dayDispatches[targetSlot] || 0;
  if (nowUtcMs - lastDispatchMs < 25 * 60 * 1000) {
    return "Cooldown active for " + targetSlot + " (dispatched recently)";
  }

  // Check if there is at least 1 video in the Queue before dispatching (pass null so settings file is untouched)
  const queueInfo = getQueueInfo(null);
  if (queueInfo.count === 0) {
    return "Queue is empty";
  }

  // Trigger GitHub workflow_dispatch for targetSlot and only record dispatch in post_history.json on HTTP 2xx
  const statusCode = triggerGitHubWorkflowDispatch(false, targetSlot);
  if (statusCode >= 200 && statusCode < 300) {
    if (!history.dispatched_slots_by_date) history.dispatched_slots_by_date = {};
    if (!history.dispatched_slots_by_date[todayIst]) history.dispatched_slots_by_date[todayIst] = {};
    history.dispatched_slots_by_date[todayIst][targetSlot] = nowUtcMs;

    // Retain only the 7 most recent dispatch dates
    const dispatchDates = Object.keys(history.dispatched_slots_by_date).sort();
    for (let i = 0; i < dispatchDates.length - 7; i++) {
      delete history.dispatched_slots_by_date[dispatchDates[i]];
    }

    savePostHistory(history);
    return "Dispatched GitHub Actions (HTTP " + statusCode + ") for slot: " + targetSlot + " at " + hour + ":" + minute + " IST";
  }

  const errMsg = "⚠️ Exact-time scheduler failed to dispatch `" + targetSlot + "` to GitHub Actions (HTTP " + statusCode + "). Check GITHUB\\_TOKEN in Apps Script.";
  Logger.log("[EXACT SCHEDULER] " + errMsg);
  sendTelegramMessage(ALLOWED_CHAT_ID, errMsg);
  return "Dispatch failed (HTTP " + statusCode + ") for slot: " + targetSlot;
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
