const endpoint = document.getElementById("endpoint");
const token = document.getElementById("token");
const status = document.getElementById("status");

chrome.storage.local.get({ endpoint: "http://127.0.0.1:8765/captures", token: "" }, (settings) => {
  endpoint.value = settings.endpoint;
  token.value = settings.token;
});

function setStatus(message, error = false) {
  status.textContent = message;
  status.style.color = error ? "#b42318" : "#176b4d";
}

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set({ endpoint: endpoint.value.trim(), token: token.value.trim() }, () => setStatus("设置已保存"));
});

document.getElementById("collect").addEventListener("click", async () => {
  await chrome.storage.local.set({ endpoint: endpoint.value.trim(), token: token.value.trim() });
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.includes("goofish.com")) { setStatus("请先打开闲鱼商品详情页", true); return; }
  chrome.tabs.sendMessage(tab.id, { type: "extract-current-page" }, (result) => {
    if (chrome.runtime.lastError) { setStatus("页面采集脚本未加载，请刷新商品页", true); return; }
    if (!result?.ok) { setStatus(result?.error || "无法读取当前页面", true); return; }
    chrome.runtime.sendMessage({ type: "submit-capture", capture: result.capture }, (response) => {
      if (chrome.runtime.lastError) setStatus("扩展通信失败", true);
      else setStatus(response?.ok ? `已保存：${response.file}` : response?.error || "采集失败", !response?.ok);
    });
  });
});
