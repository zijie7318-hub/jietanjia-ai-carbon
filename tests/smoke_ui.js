#!/usr/bin/env node
/* 前端静态冒烟检查：脚本语法、DOM 引用、核心界面与品牌残留。 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'backend', 'index.html'), 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
const script = scriptMatch ? scriptMatch[1] : '';
const results = [];
const check = (name, cond, extra = '') => {
  results.push((cond ? 'PASS  ' : 'FAIL  ') + name + (extra ? '  → ' + extra : ''));
};

check('页面包含内联脚本', !!scriptMatch);
try {
  new vm.Script(script, { filename: 'index-inline.js' });
  check('页面脚本语法可解析', true);
} catch (err) {
  check('页面脚本语法可解析', false, err.message);
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
check('政策原文链接只允许 HTTP(S)', /\/\^https\?:\\\/\\\/\//.test(script) || /sourceUrl = \/\^https/.test(script));
check('页面包含年/月/日归档区', /id="recTree"/.test(html) && /id="recDate"/.test(html));
check('页面明确标注演示政策边界', /演示政策，不构成申领依据/.test(html));
check('页面明确标注数值为估算', /不构成节电承诺或申领依据/.test(html));

const requiredEndpoints = ['/api/energy/plans', '/api/energy/meta', '/api/energy/explain', '/api/auth/login', '/api/carbon-entries'];
requiredEndpoints.forEach(api => check('包含接口 ' + api, script.includes(api)));
const forbidden = ['/api/create-order', '/api/stores', '/api/blindbox', '/api/plans/llm'];
forbidden.forEach(api => check('已移除旧接口 ' + api, !script.includes(api)));

const brandWords = ['麦当劳', 'MCD_', '麦盒日记', 'HappyTime', '餐品盲盒', '官方核价'];
brandWords.forEach(word => check('无品牌/餐饮残留：' + word, !html.includes(word)));
check('页面无外部脚本依赖', !/<script[^>]+src=/.test(html));
check('前端不允许通过参数改写接口地址', !/qs\.get\(['"]api['"]\)/.test(script) && !script.includes('jtc_api_base'));
check('模型 Key 不会发往可替换的第三方地址', script.includes('const API_BASE = DEFAULT_API_BASE'));
check('页面声明中文语言和视口', /<html lang="zh-CN">/.test(html) && /name="viewport"/.test(html));

const htmlIds = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1])
  .filter(id => !id.includes("' +"));
const duplicateIds = [...new Set(htmlIds.filter((id, i) => htmlIds.indexOf(id) !== i))];
check('静态 DOM ID 不重复', duplicateIds.length === 0, duplicateIds.join(', '));

console.log(results.join('\n'));
const passed = results.filter(x => x.startsWith('PASS')).length;
console.log('\n' + passed + '/' + results.length + ' passed');
process.exit(passed === results.length ? 0 : 1);
