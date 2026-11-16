/* 节碳家 · ai-config.js — 模型预设、Key 存储与 AI 开关状态 */
const LLM_PRESETS = [
  { id: 'deepseek', label: 'DeepSeek（推荐）', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { id: 'openai', label: 'OpenAI GPT', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { id: 'zhipu', label: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  { id: 'moonshot', label: 'Moonshot Kimi', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { id: 'qwen', label: '通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { id: 'custom', label: '自建 / 自定义服务（需服务端允许）', baseUrl: '', model: '' }
];
const AI_STORE_KEY = 'jtc_ai';
const AI_KEY_SESSION = 'jtc_ai_key_s';
const AI_KEY_LOCAL = 'jtc_ai_key_l';
function readKey() {
  try { return sessionStorage.getItem(AI_KEY_SESSION) || localStorage.getItem(AI_KEY_LOCAL) || ''; }
  catch (_) { return ''; }
}
function writeKey(key, remember) {
  try {
    if (remember) { localStorage.setItem(AI_KEY_LOCAL, key); sessionStorage.removeItem(AI_KEY_SESSION); }
    else { sessionStorage.setItem(AI_KEY_SESSION, key); localStorage.removeItem(AI_KEY_LOCAL); }
  } catch (_) {}
}
/** @returns {JtcAiState} */
function loadAi() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(AI_STORE_KEY) || '{}') || {}; } catch (_) {}
  return {
    mode: saved.mode === 'llm' ? 'llm' : (saved.mode === 'local' ? 'local' : ''),
    preset: saved.preset || 'deepseek',
    baseUrl: saved.baseUrl || '', model: saved.model || '',
    remember: !!saved.remember, key: readKey()
  };
}
/** @type {JtcAiState} */
let ai = loadAi();
function persistAi() {
  localStorage.setItem(AI_STORE_KEY, JSON.stringify({
    mode: ai.mode, preset: ai.preset, baseUrl: ai.baseUrl, model: ai.model, remember: !!ai.remember
  }));
}
function clearKey() {
  try { sessionStorage.removeItem(AI_KEY_SESSION); localStorage.removeItem(AI_KEY_LOCAL); } catch (_) {}
  ai.key = ''; ai.mode = ai.mode === 'llm' ? 'local' : ai.mode;
  persistAi(); syncAiUi();
}
/** @param {string} key @returns {string} */
function maskKey(key) {
  if (!key) return '未填写';
  return key.length <= 8 ? '****' : key.slice(0, 4) + '****' + key.slice(-4);
}
function currentLlm() {
  const p = LLM_PRESETS.find(x => x.id === ai.preset) || LLM_PRESETS[0];
  return { baseUrl: p.id === 'custom' ? ai.baseUrl : p.baseUrl,
           model: p.id === 'custom' ? ai.model : p.model, key: ai.key };
}
function aiReady() {
  if (ai.mode !== 'llm') return false;
  const c = currentLlm(); return !!(c.key && c.baseUrl && c.model);
}
function aiJsonHeaders() {
  return { 'Content-Type': 'application/json', 'X-LLM-Key': currentLlm().key };
}
function aiPair() { const c = currentLlm(); return { baseUrl: c.baseUrl, model: c.model }; }
