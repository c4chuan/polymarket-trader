# 🎯 Polymarket Trader

> OpenClaw Skill — 在 Polymarket 预测市场上交易、扫描机会、自动套利

[![Polygon](https://img.shields.io/badge/Chain-Polygon-8247E5?logo=polygon)](https://polygon.technology/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Polymarket Trader 是一个为 [OpenClaw](https://github.com/openclaw/openclaw) 打造的预测市场交易技能。通过 Polygon 链上操作 + CLOB 订单簿实现完整的交易流程，并内置每日自动扫描策略。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🔍 市场浏览 | 热门市场、关键词搜索、市场详情 |
| 💰 交易执行 | 链上 split + CLOB 卖单，支持 YES/NO 双向 |
| 📊 持仓追踪 | 实时盈亏、持仓历史 |
| 🛡️ AI 对冲 | LLM 驱动的对冲关系发现 |
| 🎯 每日扫描 | 三种自动化策略寻找交易机会 |
| ⏰ Cron 集成 | 定时扫描 + 自动执行 + 消息推送 |

## 🏗️ 架构

Polymarket 交易分两层：

```
用户下单 → Split USDC.e → YES + NO 代币 → CLOB 卖掉不要的那边
                ↑ 链上操作 (Polygon)          ↑ 中心化 API
```

- **链上层（Polygon）**：拆分 USDC.e → YES/NO 代币，合约授权，余额查询
- **CLOB 层（中心化 API）**：订单簿挂单/吃单，卖出不需要的代币

## 🚀 快速开始

### 1. 安装依赖

```bash
cd skills/polymarket-trader
uv sync
```

### 2. 配置环境变量

复制 `.env.example` 并填写：

```bash
cp .env.example .env
```

```env
# Polygon RPC（必需）
CHAINSTACK_NODE="https://polygon.drpc.org"

# 钱包私钥（必需）— 建议使用专用钱包，不要用主钱包
POLYCLAW_PRIVATE_KEY="0x你的私钥"

# CLOB 代理（如果服务器 IP 在封禁地区才需要）
# HTTPS_PROXY="http://非封禁地区代理"

# AI 对冲分析（可选）
# OPENROUTER_API_KEY="你的key"
```

### 3. 钱包准备

钱包里需要：
- **USDC.e**（Polygon）：交易资金，最少 $10
- **POL**：Gas 费，0.5-1 个就够

> ⚠️ 从交易所提币时选 **Polygon 网络**，不是 Ethereum！

### 4. 链上授权（首次必须）

```bash
uv run python scripts/polyclaw.py wallet approve
```

提交 6 笔授权交易，花费约 0.01 POL gas，只需做一次。

### 5. 验证

```bash
uv run python scripts/polyclaw.py wallet status
```

## 📖 使用方法

### 浏览市场

```bash
# 热门市场（按交易量排序）
polyclaw markets trending

# 搜索
polyclaw markets search "Bitcoin"
polyclaw markets search "NBA"

# 市场详情
polyclaw market <market_id>
```

### 交易

```bash
# 买 $5 的 YES
polyclaw buy <market_id> YES 5

# 买 $3 的 NO
polyclaw buy <market_id> NO 3
```

### 持仓

```bash
polyclaw positions list
polyclaw positions show <id>
```

### AI 对冲扫描

```bash
polyclaw hedge scan
polyclaw hedge scan --query "election"
polyclaw hedge analyze <id1> <id2>
```

## 🎯 每日扫描器（Daily Scanner）

自动扫描市场寻找交易机会，内置三种策略：

| 策略 | 触发条件 | 风险 |
|------|----------|------|
| 🏁 **终局交易** (endgame) | 市场 >90% 概率 | 低 — 买入近乎确定的赢家 |
| 💰 **定价偏差** (mispricing) | YES+NO < $0.95 | 极低 — 买两边套利 |
| ⏰ **即将结算** (expiring) | 24h 内结算 + >80% 方向 | 中 — 时间紧迫 |

```bash
# 扫描机会
polyclaw scan

# 按主题过滤
polyclaw scan --query "Bitcoin"

# 自动执行高置信度机会
polyclaw scan --auto --max-bet 3 --max-total 10

# 调整阈值
polyclaw scan --min-edge 0.08 --min-volume 10000

# JSON 输出（适合程序处理）
polyclaw scan --json
```

### Cron 定时任务

配合 OpenClaw cron 实现每日自动扫描：

```bash
openclaw cron add \
  --name "polymarket-daily-scan" \
  --cron "0 10 * * *" \
  --tz "Asia/Shanghai" \
  --message "运行 polymarket-trader 每日扫描，报告机会" \
  --announce --session isolated
```

## ⚠️ 踩坑指南

### CLOB 地区限制（最大的坑）

Polymarket CLOB API 按 IP 封禁，封禁地区包括美国、英国、法国、德国、澳大利亚等。

```bash
# 检测你的 IP 是否被封
curl -s "https://polymarket.com/api/geoblock"
```

**未封禁的常用地区**：🇨🇳 中国大陆 | 🇭🇰 香港 | 🇯🇵 日本 | 🇰🇷 韩国 | 🇨🇦 加拿大

> 链上操作（split、approve、查余额）不受影响，只有 CLOB 卖单会被拦。

### Split 成功但 CLOB 失败

如果买入时 split 成功但 CLOB 卖单失败，你会同时持有 YES 和 NO 代币。处理方式：
1. 解决代理问题后手动卖出
2. 等市场结算（YES 或 NO 其中一个值 $1）
3. 用 `mergePositions` 合并回 USDC.e

### RPC 节点选择

| 节点 | 状态 |
|------|------|
| `polygon.drpc.org` | ✅ 免费可用（推荐开发） |
| `1rpc.io/matic` | ⚠️ 有时可用 |
| Chainstack 付费 | ✅ 最稳定（推荐生产） |

## 📁 项目结构

```
polymarket-trader/
├── SKILL.md                    # OpenClaw skill 定义
├── README.md                   # 本文件
├── .env.example                # 环境变量模板
├── pyproject.toml              # Python 依赖
├── lib/
│   ├── clob_client.py          # CLOB 订单簿客户端（代理+重试）
│   ├── contracts.py            # Polygon 合约地址和 ABI
│   ├── coverage.py             # 对冲覆盖率计算
│   ├── gamma_client.py         # Polymarket Gamma API
│   ├── llm_client.py           # LLM 对冲分析
│   ├── position_storage.py     # 持仓本地存储
│   └── wallet_manager.py       # 钱包管理
└── scripts/
    ├── polyclaw.py             # CLI 入口
    ├── daily_scan.py           # 每日扫描器 🆕
    ├── markets.py              # 市场浏览/搜索
    ├── trade.py                # 买入执行
    ├── positions.py            # 持仓查看
    ├── wallet.py               # 钱包状态/授权
    └── hedge.py                # AI 对冲扫描
```

## 🔗 合约地址（Polygon Mainnet）

| 合约 | 地址 |
|------|------|
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| CTF | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| CTF Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk CTF Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |

## 📈 交易策略参考

1. **🏁 终局交易** — 事件基本确定（>95%）时大手笔扫货，赚最后 1-5%
2. **💰 定价偏差** — YES+NO 不等于 $1 时买两边套利，无风险收益
3. **🌤️ 气象套利** — 对接气象模型，发现天气市场定价错误
4. **📊 预言机滞后** — 监控大交易所价格异动，在散户反应前抢跑
5. **😱 情绪逆向** — 市场极度恐慌时逆向下注

## 📄 License

MIT

---

Built with 🦞 [OpenClaw](https://github.com/openclaw/openclaw)

