const DEFAULT_ENDPOINT = "http://127.0.0.1:8765/captures";
let automationPolling = false;
let pollTimer = null;

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function settings() {
  return chrome.storage.local.get({ endpoint: DEFAULT_ENDPOINT, token: "" });
}

function controlOrigin(endpoint) {
  return new URL(endpoint).origin;
}

async function submitCapture(capture) {
  const configured = await settings();
  if (!configured.token) {
    throw new Error("请先在扩展设置中填写本机采集令牌");
  }
  const response = await fetch(configured.endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Collector-Token": configured.token },
    body: JSON.stringify(capture)
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `本机接收服务返回 HTTP ${response.status}`);
  }
  return body;
}

async function submitTaskCapture(taskId, capture) {
  const configured = await settings();
  const endpoint = new URL(configured.endpoint);
  endpoint.pathname = `/captures/${encodeURIComponent(taskId)}`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Collector-Token": configured.token },
    body: JSON.stringify(capture)
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `本机接收服务返回 HTTP ${response.status}`);
  return body;
}

async function postTaskEvent(taskId, payload) {
  const configured = await settings();
  if (!configured.token) return;
  const url = `${controlOrigin(configured.endpoint)}/automation/tasks/${encodeURIComponent(taskId)}/events`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Collector-Token": configured.token },
    body: JSON.stringify(payload)
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `本机控制服务返回 HTTP ${response.status}`);
}

function waitForTabLoad(tabId, timeout = 30000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => finish(new Error("页面加载超时")), timeout);
    const finish = (error, tab) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      error ? reject(error) : resolve(tab);
    };
    const listener = (updatedTabId, changeInfo, tab) => {
      if (updatedTabId === tabId && changeInfo.status === "complete") finish(null, tab);
    };
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime.lastError) finish(new Error(chrome.runtime.lastError.message));
      else if (tab?.status === "complete") finish(null, tab);
    });
  });
}

async function sendToTab(tabId, message, attempts = 20) {
  let lastError = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const response = await new Promise((resolve) => {
      chrome.tabs.sendMessage(tabId, message, (result) => {
        const error = chrome.runtime.lastError;
        resolve(error ? { ok: false, error: error.message } : (result || { ok: false, error: "页面没有返回结果" }));
      });
    });
    if (response?.ok) return response;
    lastError = response?.error || "页面采集脚本未就绪";
    await sleep(500);
  }
  throw new Error(lastError || "页面采集脚本未就绪");
}

function isBlockingPageError(error) {
  return /登录|验证码|安全验证|风控|captcha|verify|login/i.test(String(error));
}

async function runAutomationTask(task) {
  let tabId = null;
  let collected = 0;
  let failed = 0;
  try {
    await postTaskEvent(task.id, { state: "running", message: "打开闲鱼搜索页" });
    const tab = await chrome.tabs.create({ url: task.search_url, active: true });
    tabId = tab.id;
    if (!tabId) throw new Error("无法创建浏览器标签页");
    await waitForTabLoad(tabId);
    await sleep(1200);
    for (let index = 0; index < 3; index += 1) {
      await sendToTab(tabId, { type: "scroll-search" });
      await sleep(800);
    }
    const links = (await sendToTab(tabId, { type: "extract-search-links", limit: task.max_items })).items || [];
    await postTaskEvent(task.id, { state: "running", discovered: links.length, message: `发现 ${links.length} 个商品` });
    if (!links.length) throw new Error("搜索页未发现商品详情链接");

    for (const [index, item] of links.entries()) {
      try {
        await postTaskEvent(task.id, { state: "running", discovered: links.length, collected, failed, message: `采集第 ${index + 1}/${links.length} 个商品` });
        await chrome.tabs.update(tabId, { url: item.source_url, active: true });
        await waitForTabLoad(tabId);
        await sleep(1200);
        const result = await sendToTab(tabId, { type: "extract-current-page" });
        await submitTaskCapture(task.id, result.capture);
        collected += 1;
        await postTaskEvent(task.id, { state: "running", discovered: links.length, collected, failed, message: `已采集 ${collected} 条` });
      } catch (error) {
        failed += 1;
        await postTaskEvent(task.id, { state: "running", discovered: links.length, collected, failed, message: `商品 ${item.item_id} 失败：${error.message}` });
        if (isBlockingPageError(error)) throw new Error(`页面需要人工处理：${error.message}`);
      }
      if (task.delay_seconds) await sleep(task.delay_seconds * 1000);
    }
    await postTaskEvent(task.id, { state: "completed", discovered: links.length, collected, failed, message: "自动采集完成" });
  } catch (error) {
    const blocked = isBlockingPageError(error);
    await postTaskEvent(task.id, { state: blocked ? "blocked" : "failed", collected, failed, message: error.message });
  } finally {
    if (tabId) chrome.tabs.remove(tabId).catch(() => {});
  }
}

async function pollAutomation() {
  if (automationPolling) return;
  automationPolling = true;
  try {
    const configured = await settings();
    if (!configured.token) return;
    const response = await fetch(`${controlOrigin(configured.endpoint)}/automation/next`, {
      headers: { "X-Collector-Token": configured.token }
    });
    if (response.status === 200) await runAutomationTask(await response.json());
  } catch (_) {
    // 本机服务未启动时静默重试；任务错误会通过事件上报。
  } finally {
    automationPolling = false;
    scheduleAutomationPolling();
  }
}

function scheduleAutomationPolling(delay = 1200) {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(() => {
    pollTimer = null;
    pollAutomation();
  }, delay);
}

function startAutomationPolling() {
  chrome.alarms.create("automation-poll", { periodInMinutes: 0.5 });
  scheduleAutomationPolling(0);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "submit-capture") {
    submitCapture(message.capture)
      .then((body) => sendResponse({ ok: true, file: body.file }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get({ endpoint: "" }, ({ endpoint }) => {
    if (!endpoint) chrome.storage.local.set({ endpoint: DEFAULT_ENDPOINT });
  });
  startAutomationPolling();
});

chrome.runtime.onStartup.addListener(() => {
  startAutomationPolling();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "automation-poll") pollAutomation();
});

// A service worker can be started by an extension reload without onInstalled/onStartup.
// Start polling here as well so a queued terminal task is picked up immediately.
startAutomationPolling();
