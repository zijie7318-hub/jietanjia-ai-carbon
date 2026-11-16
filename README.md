# 节碳家 · AI 家庭减碳助手

> 把家庭节能想法，变成算得清、可执行、可回看的方案。

节碳家是第九届“传智杯”AI Web 网页开发赛道的参赛项目。用户填写城市、住房情况、家庭人口、用电量和预算后，应用会生成“轻量起步 / 均衡优选 / 深度减碳”三档方案，展示投入、节电、费用、减碳量和回收周期，并给出带状态的补贴政策初筛。

- 赛道：AI Web 应用开发（赛道页面编号 `10037`）
- 团队：Crownbreaker（成员和指导教师以赛事报名信息为准）
- 技术形态：单端口 Flask Web 应用，前端沿用原项目零构建单页架构
- 许可协议：MIT

> 当前仓库中的节能参数、排放因子、电价和补贴政策均为**演示数据**。它们用于验证产品流程，不构成节电承诺、真实政策或申领依据。

## 直接分享的离线演示网页

如果只需要让队友或评审快速查看效果，可直接发送：

`docs/节碳家_离线演示.html`

该文件无需安装 Python、无需服务器、无需联网或模型 Key，双击即可在浏览器中体验三档方案、政策初筛、碳迹保存和计划转完成。离线版明确不在浏览器中伪造 AI 调用，完整 AI 解释与账号归档需运行 Flask 完整版。

重新生成离线版：

```bash
python scripts/build_offline_demo.py
```

## 功能

1. **家庭节能评估**：月用电量和月电费至少填写一项，缺少时使用醒目标注的演示基线。
2. **三档节能方案**：每档包含 3–5 项措施，展示前期投入、年节电、年节省电费、年减碳量和回收周期。
3. **补贴规则初筛**：按城市、日期、住房条件和措施匹配政策，展示通过或未通过原因、材料条件和更新时间。
4. **AI 方案解释**：模型只基于服务端计算结果和检索条款组织解释，不参与数值和资格判断。
5. **碳迹日记**：区分“已完成”和“计划执行”，按年 / 月 / 日归档，支持搜索、日期筛选、复制和删除。
6. **规则降级**：没有模型 Key、模型超时或乱答时，三档方案、政策初筛和碳迹记录仍可正常使用。

## AI 工作流与边界

```text
家庭输入
  ↓ 服务端输入校验与默认值标记
本地措施筛选 → 确定性三档计算
  ↓
政策规则初筛 → 元数据过滤 + 本地条款检索
  ↓
（可选）LLM 组织方案解释
  ↓ 服务端过滤未知档位/政策 ID
展示结果与来源状态
```

- 节电量、金额、减碳量与资格由 `energy_service.py` 计算。
- `policy_retriever.py` 以城市、日期、住房和措施先做元数据过滤，再检索政策条款片段。
- LLM 仅可使用检索到的片段写摘要；未知档位和政策 ID 会被丢弃。
- 模型地址采用服务端白名单；默认只允许代码中列出的公开模型服务，自建地址须显式配置。
- 用户模型 Key 默认仅存本机 sessionStorage，勾选“记住”才存 localStorage；服务端不落盘、不写日志。

## 快速启动

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example backend/.env
python backend/app.py
```

打开 <http://localhost:5000>。默认无需模型 Key，也无需外部业务接口。

### 环境变量

后端只读取 `backend/.env`，模板见根目录 `.env.example`。

| 变量 | 必填 | 说明 |
|---|---|---|
| `JTC_SHARE_CODE` / `JTC_SHARE_CODES` | 否 | 可选访问码，多码用英文逗号分隔 |
| `JTC_RATE_LIMIT` / `JTC_RATE_WINDOW` | 否 | 模型、账户和能源接口限流，默认 40 次 / 300 秒 |
| `JTC_TRUST_PROXY` | 否 | 仅在可信反向代理后开启，避免伪造代理头 |
| `JTC_ENABLE_CORS` | 否 | 默认关闭；同源部署无需开启 |
| `HT_DB_PATH` | 生产建议 | SQLite 路径，生产环境必须指向持久化磁盘 |
| `HT_TOKEN_SECRET` | 生产必填 | 登录令牌独立签名密钥，建议 32 字符以上高熵值 |
| `JTC_LLM_ALLOWED_BASE_URLS` | 否 | 额外允许的 OpenAI 兼容 base_url，英文逗号分隔 |
| `PORT` | 否 | 服务端口，默认 5000 |
| `HT_DEBUG` | 否 | 仅排查部署问题时开启账户自检接口 |

`HT_TOKEN_SECRET` 留空时服务使用进程级随机密钥，重启后已有登录态会失效。

## 项目结构

```text
backend/
├─ app.py                 # Flask 入口、静态页、安全中间件、能源与解释接口
├─ energy_service.py      # 输入校验、三档计算、政策规则初筛
├─ policy_retriever.py    # 元数据过滤后的本地政策条款检索
├─ llm_review.py          # OpenAI 兼容传输层
├─ llm_steps.py           # 方案解释、碳迹反馈、结构化输出校验
├─ ht_api.py              # 账号与碳迹记录（SQLite）
├─ index.html             # 单文件前端：页面、样式和交互
└─ catalog/
   ├─ actions.json        # 12 项演示节能措施
   ├─ policies.json       # 3 条西安市演示政策
   └─ factors.json        # 演示排放因子、电价和基线参数
tests/
├─ smoke_api.py           # 账号、记录、安全、分享码与限流
├─ test_energy.py         # 三档计算、预算、政策日期与资格
├─ test_ai.py             # 检索、AI 解释、输出过滤与降级
└─ smoke_ui.js            # 前端语法、DOM、接口与品牌残留
docs/
├─ 技术报告.md / 最终版.docx  # 技术报告源稿与可编辑 Word
├─ 演示视频脚本.md        # 5–8 分钟录制脚本
├─ 提交检查清单.md        # 省赛提交前核对项
├─ 验收记录.md            # 本地测试与浏览器验收结果
└─ screenshots/           # 技术文档截图
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查，不返回任何密钥 |
| `GET` | `/api/energy/meta` | 数据版本、措施/政策数量和免责声明 |
| `POST` | `/api/energy/plans` | 家庭条件 → 三档方案 + 政策初筛 |
| `POST` | `/api/energy/explain` | 重算方案 → 条款检索 → 可选 AI 解释 |
| `POST` | `/api/auth/register` | 注册 |
| `POST` | `/api/auth/login` | 登录 |
| `POST` | `/api/auth/logout` | 登出并吊销令牌 |
| `GET` | `/api/auth/me` | 当前用户 |
| `GET/POST` | `/api/carbon-entries` | 查询 / 新增碳迹 |
| `DELETE` | `/api/carbon-entries/<id>` | 删除本人碳迹 |
| `POST` | `/api/llm/carbon-feedback` | 可选 AI 碳迹反馈 |

除 `/api/health` 外，模型、能源和账户接口均受可选分享码与 IP 限流保护。记录接口依靠用户令牌隔离。

## 测试

测试全部离线运行，不需要模型 Key、外部业务接口或网络：

```bash
python tests/smoke_api.py    # 39 项
python tests/test_energy.py  # 43 项
python tests/test_ai.py      # 26 项
node tests/smoke_ui.js       # 38 项
```

当前结果：**146/146 通过**。

测试覆盖重点：

- 三档计算、预算裁剪、租房限制、默认基线和数字边界；
- 政策城市、有效期、住房条件和演示状态；
- 模型乱答、超时、不可达及输出 ID 过滤；
- 密码登录、令牌吊销、用户记录隔离和限流；
- 品牌残留、DOM 引用、接口路径和前端脚本语法。

## 部署

### 方式一：Docker（推荐）

SQLite 需要持久化磁盘，因此生产部署必须是**单实例**。

```bash
docker build -t jietanjia .
docker run -d --name jietanjia \
  -p 8000:8000 \
  -v jietanjia_data:/data \
  -e HT_DB_PATH=/data/records.db \
  -e HT_TOKEN_SECRET='替换为至少32字符的高熵随机值' \
  jietanjia
```

访问 <http://localhost:8000>。

### 方式二：云平台

- 选择支持持久化磁盘的 Python 单实例环境；
- 启动命令：`gunicorn --chdir backend --workers 1 --threads 4 --bind 0.0.0.0:$PORT app:app`；
- 将 `HT_DB_PATH` 指向持久化磁盘；
- 配置独立 `HT_TOKEN_SECRET`。

**不建议直接部署到无持久磁盘的 serverless 环境。**若必须使用 Vercel，需要把 SQLite 替换为托管数据库，不能沿用本仓库的默认存储方案。

## 数据、隐私与安全

- 账号只保存用户名、密码散列和本人碳迹；密码使用 PBKDF2-SHA256 和独立随机盐。
- 碳迹按 `user_id` 隔离，删除操作同时校验用户归属。
- 不采集详细地址、证件、手机号或账单原图；当前版本没有 OCR 和图片上传。
- 所有节能、费用和减碳数值均标注为估算；演示政策不伪造官方链接。
- “计划执行”不会被展示成已完成的减碳结果。
- 真实订单、支付、设备控制和自动申领能力均已移除。

## 已知限制

- 节能参数、排放因子、电价和政策目前是演示数据，不能用于真实决策或申报。
- 首批政策演示数据只覆盖西安市，不能宣称全国或实时政策覆盖。
- 方案采用简化年度估算，不考虑气候区、建筑朝向、设备型号和实际使用强度的全部差异。
- 租住约束仅根据住房类型做基础过滤，实际施工仍需房东和物业确认。
- 未接入账单 OCR、智能家居、实时电网数据和多端实时同步。
- 前端保留零构建单页架构，未迁移 TypeScript 或现代组件框架。

## 原创与权利边界

本项目在团队既有自研 Web 系统基础上进行业务领域重构，保留通用账号、记录、模型调用和安全中间件，重新实现家庭节能、政策初筛、AI 解释与碳迹领域逻辑。仓库不包含第三方品牌素材、官方接口凭据、用户数据或部署密钥。

第三方资源通过包管理器或远程 API 使用，许可信息在技术文档中另行汇总。代码以 MIT License 开放。
