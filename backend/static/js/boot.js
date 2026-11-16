/* 节碳家 · boot.js — 首屏初始化顺序 */
async function loadMeta() {
  try {
    const data = await requestJson('/api/energy/meta', {}, 10000);
    document.getElementById('dataVersionTag').textContent =
      data.actionCount + ' 项措施 · ' + data.policyCount + ' 条已接入政策';
  } catch (_) {
    document.getElementById('dataVersionTag').textContent = '规则数据暂时不可用';
  }
}

hpInit();
loadMeta();
switchTab((location.hash || '#plans').slice(1), { noScroll: true, silent: true });
