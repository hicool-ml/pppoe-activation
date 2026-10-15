// i18n核心逻辑
console.log("i18n.js loaded");

let currentLang = "zh";
let messages = {};
let i18nInitialized = false;

// 加载语言文件
async function loadLang(lang) {
  console.log("loading lang:", lang);
  
  try {
    const res = await fetch(`/static/i18n/${lang}.json`);
    if (!res.ok) {
      throw new Error(`Failed to load language file: ${lang}`);
    }
    messages = await res.json();
    currentLang = lang;
    
    console.log("loaded messages:", messages);
    
    // 保存语言偏好
    localStorage.setItem('language', lang);
    
    // 应用翻译
    applyI18n();
    
    // 只在第一次初始化时触发i18nReady事件
    if (!i18nInitialized) {
      i18nInitialized = true;
      window.initI18nDone = true;
      document.dispatchEvent(new Event('i18nReady'));
      console.log("i18nReady event dispatched");
    }
  } catch (err) {
    console.error('Failed to load language:', err);
    // 如果加载失败，回退到中文
    if (lang !== 'zh') {
      loadLang('zh');
    }
  }
}

// 获取翻译文本
function t(key) {
  const value = key.split('.').reduce((o, k) => o?.[k], messages);
  if (!value) {
    console.warn("i18n missing key:", key);
  }
  return value || key;
}

// 应用翻译到页面
function applyI18n() {
  console.log("applying i18n for language:", currentLang);

  // 更新所有带 data-i18n 属性的元素
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    const translation = t(key);

    if (translation === key) {
      console.warn("i18n missing key:", key);
    }

    el.textContent = translation;
  });

  // 更新所有带 data-i18n-placeholder 属性的元素
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    const translation = t(key);

    if (translation === key) {
      console.warn("i18n missing key:", key);
    }

    el.placeholder = translation;
  });

  // 同步更新 document.documentElement.lang
  document.documentElement.lang = currentLang === 'zh' ? 'zh-CN' : currentLang;

  // 更新错误码映射
  window.errorMessages = t('errorCodes') || {};
}

// 自动检测浏览器语言
function detectBrowserLanguage() {
  const browserLang = navigator.language || navigator.userLanguage || 'zh';
  // 提取语言代码的前两位（例如：en-US -> en）
  const langCode = browserLang.split('-')[0].toLowerCase();
  
  // 支持的语言映射
  const supportedLangs = {
    'zh': 'zh',  // 中文
    'en': 'en',  // English
    'fr': 'fr',  // Français
    'es': 'es',  // Español
    'ko': 'ko',  // 한국어
    'vi': 'vi',  // Tiếng Việt
    'ms': 'ms',  // Bahasa Melayu
    'th': 'th',  // ไทย
    'ur': 'ur',  // اردو
    'hi': 'hi',  // हिन्दी
    'ja': 'ja'   // 日本語
  };
  
  // 返回支持的语言，如果不支持则返回中文
  return supportedLangs[langCode] || 'zh';
}

// 初始化i18n
async function initI18n() {
  console.log("initI18n called");
  
  const savedLanguage = localStorage.getItem('language');
  let initialLanguage = 'zh'; // 默认中文
  
  if (savedLanguage) {
    // 如果有保存的语言偏好，使用保存的
    initialLanguage = savedLanguage;
    console.log("using saved language:", initialLanguage);
  } else {
    // 否则自动检测浏览器语言
    initialLanguage = detectBrowserLanguage();
    console.log("detected browser language:", initialLanguage);
  }
  
  // 设置初始语言
  const languageSelector = document.getElementById('languageSelector');
  if (languageSelector) {
    languageSelector.value = initialLanguage;
    console.log("set languageSelector value to:", initialLanguage);
  } else {
    console.error("languageSelector not found");
  }
  
  // 加载语言文件
  await loadLang(initialLanguage);
}

// 使用 DOMContentLoaded 确保 DOM 已加载
document.addEventListener('DOMContentLoaded', () => {
  console.log("DOMContentLoaded fired");
  
  const languageSelector = document.getElementById('languageSelector');
  if (!languageSelector) {
    console.error("languageSelector not found in DOMContentLoaded");
    return;
  }
  
  languageSelector.addEventListener('change', (e) => {
    console.log("language changed to:", e.target.value);
    loadLang(e.target.value);
  });
  
  // 初始化i18n
  initI18n();
});
