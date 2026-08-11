const BUTTON_ID = "product-rag-local-collector";
const PHONE = /(?<!\d)1[3-9]\d{9}(?!\d)/g;

function clean(value, limit = 5000) {
  if (typeof value !== "string") return null;
  const normalized = value.replace(/\s+/g, " ").replace(PHONE, "[REDACTED_PHONE]").trim();
  return normalized ? normalized.slice(0, limit) : null;
}

function meta(name) {
  return clean(document.querySelector(`meta[property="${name}"], meta[name="${name}"]`)?.content || "");
}

function structuredProduct() {
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const value = JSON.parse(script.textContent || "null");
      const candidates = Array.isArray(value) ? value : value?.["@graph"] || [value];
      const product = candidates.find((entry) => {
        const type = entry?.["@type"];
        return type === "Product" || (Array.isArray(type) && type.includes("Product"));
      });
      if (product) return product;
    } catch (_) {
      // 页面可能包含非 JSON 的结构化脚本，忽略即可。
    }
  }
  return null;
}

function isGenericPageText(value) {
  const text = (value || "").replace(/\s+/g, "").toLowerCase();
  return !text || text === "为你推荐" || text === "闲鱼" || text.startsWith("闲鱼，中国领先的闲置二手交易平台");
}

function blockingPageReason() {
  const url = location.href.toLowerCase();
  const body = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
  if (/(^|[/?=&])login([/?=&]|$)|passport|sso/.test(url) || /请先登录|登录后查看|登录后继续/.test(body)) {
    return "闲鱼登录已失效，请先在 Chrome 中完成登录";
  }
  if (/captcha|verify|security|risk/.test(url) || /验证码|安全验证|滑块验证|人机验证|风险验证/.test(body)) {
    return "闲鱼页面需要人工完成验证码或安全验证";
  }
  return null;
}

function itemIdHint() {
  const params = new URL(location.href).searchParams;
  for (const name of ["itemId", "itemid", "id"]) {
    const value = params.get(name);
    if (value && /^[A-Za-z0-9_-]{1,64}$/.test(value)) return value;
  }
  const match = location.href.match(/(?<![A-Za-z0-9])(\d{6,20})(?![A-Za-z0-9])/);
  return match?.[1] || "";
}

function itemIdFromUrl(value) {
  try {
    const url = new URL(value, location.href);
    for (const name of ["itemId", "itemid", "id"]) {
      const candidate = url.searchParams.get(name);
      if (candidate && /^[A-Za-z0-9_-]{1,64}$/.test(candidate)) return candidate;
    }
    const match = url.href.match(/(?<![A-Za-z0-9])(\d{6,20})(?![A-Za-z0-9])/);
    return match?.[1] || "";
  } catch (_) {
    return "";
  }
}

function extractSearchLinks(limit = 20) {
  const result = [];
  const seen = new Set();
  for (const anchor of document.querySelectorAll("a[href]")) {
    const href = anchor.href;
    if (!href || !new URL(href, location.href).hostname.endsWith("goofish.com")) continue;
    const itemId = itemIdFromUrl(href);
    if (!itemId || seen.has(itemId)) continue;
    const url = new URL(href, location.href);
    if (!url.pathname.includes("item") && !/[?&](itemId|itemid|id)=/.test(url.search)) continue;
    seen.add(itemId);
    result.push({ item_id: itemId, source_url: href });
    if (result.length >= limit) break;
  }
  return result;
}

function findText(selectors, limit = 5000) {
  for (const selector of selectors) {
    const node = document.querySelector(selector);
    const text = clean(node?.innerText || node?.textContent || "", limit);
    if (text) return text;
  }
  return null;
}

function findPrice() {
  const product = structuredProduct();
  const structuredPrice = product?.offers?.price || product?.offers?.lowPrice;
  if (structuredPrice != null && /^\d+(\.\d{1,2})?$/.test(String(structuredPrice))) return String(structuredPrice);
  const structured = meta("product:price:amount");
  if (structured && /^\d+(\.\d{1,2})?$/.test(structured)) return structured;
  const mainPrice = clean(document.querySelector('[class^="price--"]')?.textContent || "", 30);
  if (mainPrice && /^\d+(\.\d{1,2})?$/.test(mainPrice)) return mainPrice;
  const text = findText(["[class*='price']", "[class*='Price']"], 200) || "";
  return text.match(/[¥￥]\s*(\d+(?:\.\d{1,2})?)/)?.[1] || null;
}

function findSpecs() {
  const specs = {};
  const product = structuredProduct();
  for (const property of product?.additionalProperty || []) {
    const key = clean(property?.name, 100);
    const value = clean(property?.value, 500);
    if (key && value && Object.keys(specs).length < 30) specs[key] = value;
  }
  document.querySelectorAll('[class^="item--"]').forEach((row) => {
    const label = clean(row.querySelector('[class^="label--"]')?.textContent || "", 100);
    const value = clean(row.querySelector('[class^="value--"]')?.textContent || "", 500);
    if (label && value && Object.keys(specs).length < 30) specs[label] = value;
  });
  document.querySelectorAll("dl").forEach((list) => {
    const names = list.querySelectorAll("dt");
    const values = list.querySelectorAll("dd");
    names.forEach((name, index) => {
      const key = clean(name.textContent || "", 100);
      const value = clean(values[index]?.textContent || "", 500);
      if (key && value && Object.keys(specs).length < 30) specs[key] = value;
    });
  });
  return Object.keys(specs).length ? specs : null;
}

function currentCapture() {
  const blocked = blockingPageReason();
  if (blocked) throw new Error(blocked);
  const product = structuredProduct();
  const pageTitle = clean(document.title.replace(/[_-]\s*闲鱼\s*$/, ""), 200);
  const candidates = [
    clean(product?.name, 200),
    pageTitle,
    findText(["[itemprop='name']", "h1", "[class*='title']", "[class*='Title']"], 200),
    meta("og:title")
  ];
  const title = candidates.find((candidate) => candidate && !isGenericPageText(candidate));
  if (!title) throw new Error("未识别到真实商品标题，请等待详情页加载后再采集");
  const price = findPrice();
  const structuredDescription = clean(product?.description, 5000);
  const descriptionCandidates = [
    structuredDescription,
    findText(["[itemprop='description']", "[class^='desc--']", "[class*='desc']", "[class*='Desc']", "[class*='detail']"], 5000)
  ];
  const description = descriptionCandidates.find((candidate) => candidate && !isGenericPageText(candidate)) || null;
  const specs = findSpecs();
  const condition = clean(product?.itemCondition, 100) || specs?.["成色"] || findText(["[itemprop='itemCondition']", "[class*='condition']", "[class*='Condition']"], 100);
  const category = clean(product?.category, 100) || meta("product:category") || specs?.["类目"] || specs?.["品类"] || null;
  const includedRaw = specs?.["配件"] || specs?.["包装清单"] || specs?.["包含"] || null;
  const includedItems = includedRaw == null ? null : (Array.isArray(includedRaw) ? includedRaw.map(String) : [String(includedRaw)]);
  const availability = product?.offers?.availability || "";
  const inventoryStatus = /outofstock|soldout|售罄|下架/i.test(String(availability)) ? "out_of_stock" : /instock|在售|有货/i.test(String(availability)) ? "in_stock" : "unknown";
  const shippingText = findText(["[class*='shipping']", "[class*='Shipping']", "[class*='运费']", "[class*='物流']"], 300) || "";
  const shipping = /包邮/.test(shippingText) ? { free_shipping: true, dispatch_sla_hours: null, carrier: null, fee: "0" } : null;
  const pricePayload = price ? { sale_price: price, currency: "CNY" } : null;
  return {
    schema_version: 1,
    source_url: location.href,
    item_id_hint: itemIdHint(),
    collected_at: new Date().toISOString(),
    visible: {
      title,
      description,
      specs,
      condition,
      category,
      included_items: includedItems,
      inventory: inventoryStatus === "unknown" ? null : { status: inventoryStatus, quantity: null },
      shipping,
      after_sale: null,
      faq: null,
      price: pricePayload,
      pricing: pricePayload,
      specifications: specs,
      image_urls: [...document.images].filter((image) => image.offsetParent !== null).map((image) => image.currentSrc).filter((url) => url && !url.startsWith("data:")).slice(0, 12),
      visible_text: clean(document.body.innerText || "", 12000)
    }
  };
}

function showStatus(button, text, error = false) {
  const original = button.dataset.label || "采集当前商品";
  button.textContent = text;
  button.style.background = error ? "#b42318" : "#176b4d";
  window.setTimeout(() => { button.textContent = original; button.style.background = "#176b4d"; }, 2500);
}

function mountButton() {
  if (document.getElementById(BUTTON_ID) || !itemIdHint()) return;
  const button = document.createElement("button");
  button.id = BUTTON_ID;
  button.dataset.label = "采集当前商品";
  button.textContent = button.dataset.label;
  button.type = "button";
  button.title = "采集当前页面可见商品资料到本机 RAG 测试集";
  Object.assign(button.style, {
    position: "fixed", right: "20px", bottom: "24px", zIndex: "2147483647",
    border: "0", borderRadius: "4px", padding: "10px 14px", background: "#176b4d",
    color: "#fff", fontSize: "14px", lineHeight: "20px", cursor: "pointer", boxShadow: "0 3px 10px rgba(0,0,0,.2)"
  });
  button.addEventListener("click", () => {
    let capture;
    try { capture = currentCapture(); } catch (error) { showStatus(button, error.message, true); return; }
    chrome.runtime.sendMessage({ type: "submit-capture", capture }, (response) => {
      if (chrome.runtime.lastError) showStatus(button, "扩展通信失败", true);
      else showStatus(button, response?.ok ? "已采集" : response?.error || "采集失败", !response?.ok);
    });
  });
  document.documentElement.append(button);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "extract-current-page") {
    try { sendResponse({ ok: true, capture: currentCapture() }); }
    catch (error) { sendResponse({ ok: false, error: error.message }); }
    return;
  }
  if (message.type === "extract-search-links") {
    const blocked = blockingPageReason();
    if (blocked) { sendResponse({ ok: false, error: blocked }); return; }
    sendResponse({ ok: true, items: extractSearchLinks(Math.max(1, Number(message.limit) || 20)) });
    return;
  }
  if (message.type === "scroll-search") {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "instant" });
    sendResponse({ ok: true });
  }
});

mountButton();
