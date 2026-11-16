#!/usr/bin/env node
/* 前端静态冒烟检查：脚本语法、DOM 引用、核心界面与品牌残留。 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'backend', 'index.html'), 'utf8');

// 页面已拆成按序加载的同源模块；这里按 HTML 中的真实顺序拼接后统一检查，
// 这样「脚本语法」「DOM 引用」「接口字面量」仍然是对整份前端代码做校验。
const MODULE_ORDER = ['core', 'ai-config', 'nav', 'ai-explain', 'plans',
  'diary', 'account', 'ai-modal', 'boot', 'agent-ui'];
const moduleTags = [...html.matchAll(/<script src="(static\/js\/[a-z-]+\.js)"><\/script>/g)]
  .map(m => m[1]);
const moduleFiles = moduleTags.map(rel => path.join(ROOT, 'backend', rel));
const moduleTexts = moduleFiles.map(abs => (fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : ''));
const script = moduleTexts.join('\n');
const results = [];
const check = (name, cond, extra = '') => {
  results.push((cond ? 'PASS  ' : 'FAIL  ') + name + (extra ? '  → ' + extra : ''));
};

check('页面按顺序引用前端模块',
  moduleTags.join(',') === MODULE_ORDER.map(n => 'static/js/' + n + '.js').join(','),
  moduleTags.join(','));
check('每个模块文件都存在且非空',
  moduleTexts.length === MODULE_ORDER.length && moduleTexts.every(t => t.trim().length > 0),
  moduleTexts.filter(t => !t.trim()).length + ' 个为空');
check('每个模块都有职责注释',
  moduleTexts.every(t => /^\/\* 节碳家 · [a-z-]+\.js — /.test(t)),
  '缺少注释的模块数 ' + moduleTexts.filter(t => !/^\/\* 节碳家 · /.test(t)).length);
try {
  new vm.Script(script, { filename: 'frontend-modules.js' });
  check('模块合并后语法可解析', true);
} catch (err) {
  check('模块合并后语法可解析', false, err.message);
}

const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1])
  .filter(id => !id.includes("' +"));
const refs = [...script.matchAll(/getElementById\(['"]([^'"]+)['"]\)/g)].map(m => m[1]);
const missing = [...new Set(refs)].filter(id => !ids.includes(id));
check('脚本引用的静态元素均存在', missing.length === 0, missing.join(', '));

const tabs = [...html.matchAll(/class="tab[^"]*" data-tab="([^"]+)"/g)].map(m => m[1]);
check('只有三个主入口', tabs.length === 3 && tabs.join(',') === 'plans,diary,records', tabs.join(','));
check('默认入口为节能方案', /class="jt-panel active" id="panel-plans"/.test(html));
check('页面标题已切换为节碳家', /<title>节碳家 · AI 家庭减碳助手<\/title>/.test(html));
check('页面包含家庭评估表单', /id="planForm"/.test(html) && /id="monthlyKwhInput"/.test(html));
check('页面包含三档结果容器', /id="planCards"/.test(html));
check('页面包含政策依据容器', /id="policyList"/.test(html));
check('页面包含碳迹日记', /id="hpInput"/.test(html) && /碳迹日记/.test(html));
check('碳迹区分已完成与计划执行', /id="entryType"/.test(html) && /计划执行/.test(html) && /不会被展示成已完成/.test(html));
check('碳迹计划可标记为已完成', /data-act="done"/.test(script) && /hpMarkDone/.test(script));
check('移动端保留 AI 设置入口', /\.tabs-ai\{display:inline-flex/.test(html) && /\.topbar-in\{flex-wrap:wrap/.test(html));
check('连续请求会丢弃过期 AI 结果', /requestId !== aiRequestSeq/.test(script));
check('AI 解释走流式并带事件流请求头',
  /stream: 1/.test(script) && /text\/event-stream/.test(script) && /ReadableStream/.test(script));
check('流式不可用时回退一次性接口',
  /fetchAiExplanation/.test(script) && /await fetchAiExplanation/.test(script));
check('逐字渲染有可见光标', /\.ai-cursor\{/.test(html) && /ai-cursor/.test(script));
check('政策原文链接只允许 HTTP(S)', /\/\^https\?:\\\/\\\/\//.test(script) || /sourceUrl = \/\^https/.test(script));
check('页面包含年/月/日归档区', /id="recTree"/.test(html) && /id="recDate"/.test(html));
check('页面明确标注政策候选边界', /不代表获批/.test(html) && /条件待确认/.test(html));
check('页面明确标注数值为估算', /不能替代家庭实测/.test(html) && /估算/.test(html));
check('页面说明仅接入西安市地方政策', /仅接入西安市/.test(html) && /不展示地方补贴/.test(html));
check('页面展示官方来源入口', /生态环境部/.test(script) && /陕西阶梯电价来源/.test(script));
check('措施分类使用固定列', /grid-template-columns:minmax\(0,1fr\) 56px 14px/.test(html));
check('必选字段带红色星号', (html.match(/class="req"/g) || []).length >= 3 && /为必选字段/.test(html));
check('方案摘要初始隐藏', /class="jt-hero no-preview" id="jtHero"/.test(html)
  && /id="heroPreview"[^>]*hidden/.test(html));
check('生成成功后才展示摘要', /heroPreview'\)\.hidden = false/.test(script));

const requiredEndpoints = ['/api/energy/plans', '/api/energy/meta', '/api/energy/explain', '/api/auth/login', '/api/carbon-entries'];
requiredEndpoints.forEach(api => check('包含接口 ' + api, script.includes(api)));
const forbidden = ['/api/create-order', '/api/stores', '/api/blindbox', '/api/plans/llm'];
forbidden.forEach(api => check('已移除旧接口 ' + api, !script.includes(api)));

const brandWords = ['麦当劳', 'MCD_', '麦盒日记', 'HappyTime', '餐品盲盒', '官方核价'];
brandWords.forEach(word => check('无品牌/餐饮残留：' + word, !html.includes(word)));
check('页面不引用第三方脚本', !/<script[^>]+src="(?:https?:)?\/\//.test(html)
  && !/<script[^>]+src="(?!static\/js\/)/.test(html));
check('前端不允许通过参数改写接口地址', !/qs\.get\(['"]api['"]\)/.test(script) && !script.includes('jtc_api_base'));
check('模型 Key 不会发往可替换的第三方地址', script.includes('const API_BASE = DEFAULT_API_BASE'));
check('页面声明中文语言和视口', /<html lang="zh-CN">/.test(html) && /name="viewport"/.test(html));

const htmlIds = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1])
  .filter(id => !id.includes("' +"));
const duplicateIds = [...new Set(htmlIds.filter((id, i) => htmlIds.indexOf(id) !== i))];
check('静态 DOM ID 不重复', duplicateIds.length === 0, duplicateIds.join(', '));

// 在最小 DOM 桩里加载 AI 模块，验证 SSE 解析与「未生成完也能取到文字」的能力
const aiCtx = {
  console: console, setTimeout: setTimeout, clearTimeout: clearTimeout,
  TextDecoder: TextDecoder, AbortController: AbortController,
  document: {
    getElementById: () => ({
      hidden: false, textContent: '', innerHTML: '', dataset: {},
      querySelectorAll: () => [], classList: { toggle: () => {} }
    })
  },
  window: { ReadableStream: function () {}, TextDecoder: TextDecoder },
  esc: v => String(v == null ? '' : v),
  apiUrl: p => p, requestJson: () => {}, fetch: () => {},
  aiReady: () => true, aiJsonHeaders: () => ({}), aiPair: () => ({})
};
vm.createContext(aiCtx);
try {
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'backend/static/js/ai-explain.js'), 'utf8'), aiCtx);
  const parsed = aiCtx.parseSseBlock('event: delta\ndata: {"text":"半句话"}');
  check('SSE 事件块可解析', parsed && parsed.event === 'delta' && parsed.data.text === '半句话', parsed);
  check('未闭合 JSON 也能取出已生成文字',
    aiCtx.partialIntro('{"intro": "正在生成的解释"') === '正在生成的解释');
  check('无 intro 字段时不展示半成品', aiCtx.partialIntro('{"tierNotes": [') === '');
} catch (err) {
  check('AI 模块可在无浏览器环境解析', false, err.message);
}

console.log(results.join('\n'));
const passed = results.filter(x => x.startsWith('PASS')).length;
console.log('\n' + passed + '/' + results.length + ' passed');
process.exit(passed === results.length ? 0 : 1);
