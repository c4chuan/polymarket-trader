---
name: polymarket-trader
description: "在 Polymarket 预测市场上交易。支持浏览市场、管理钱包、执行买卖、追踪持仓盈亏、AI 对冲分析。基于 Polygon 链上操作 + CLOB 订单簿。包含完整的踩坑记录和解决方案。"
version: 0.1.0
author: c4chuan
requirements:
  - uv
  - python3
tags:
  - trading
  - prediction-markets
  - polymarket
  - polygon
  - web3
---

# Polymarket Trader

在 Polymarket 预测市场上进行交易的完整 skill。通过 Polygon 链上操作 + CLOB 订单簿实现买卖。

## 架构概述

Polymarket 交易分两层：
1. **链上层（Polygon）**：拆分 USDC.e → YES/NO 代币，合约授权，余额查询
2. **CLOB 层（中心化 API）**：订单簿挂单/吃单，卖出不需要的代币

买入流程：`USDC.e → splitPosition → 得到 YES + NO → 通过 CLOB 卖掉不要的那边`

## 前置条件

### 1. 钱包准备

需要一个 EVM 钱包（Polygon 链）：

```python
from eth_account import Account
import secrets

private_key = '0x' + secrets.token_hex(32)
account = Account.from_key(private_key)
print(f'Address: {account.address}')
print(f'Private Key: {private_key}')
```

⚠️ **安全警告**：
- 专门创建一个新钱包用于交易，不要用主钱包
- 私钥泄露 = 钱没了
- 只放能承受损失的金额

### 2. 钱包充值

钱包里需要：
- **USDC.e**（Polygon）：交易资金，最少 $10
- **POL**：Gas 费，0.5-1 个就够（约 ¥3）

从交易所提币时注意选 **Polygon 网络**，不是 Ethereum。

### 3. 环境变量

在 skill 目录创建 `.env`：

```bash
# Polygon RPC 节点（必需）
CHAINSTACK_NODE="https://polygon.drpc.org"

# 钱包私钥（必需）
POLYCLAW_PRIVATE_KEY="0x你的私钥"

# CLOB 代理（重要！见下方"地区限制"）
HTTPS_PROXY="http://你的非封禁地区代理"

# AI 对冲分析用（可选）
OPENROUTER_API_KEY="你的key"
```

### 4. 安装依赖

```bash
cd {baseDir}/../polyclaw-cli
uv sync
```

### 5. 链上授权（首次必须）

```bash
uv run python scripts/polyclaw.py wallet approve
```

这会提交 6 笔授权交易到 Polygon，花费约 0.01 POL gas。只需做一次。

授权的合约：
- USDC.e → CTF（条件代币框架）
- USDC.e → CTF_EXCHANGE（交易网关）
- USDC.e → NEG_RISK_CTF_EXCHANGE（负风险交易网关）
- CTF → CTF_EXCHANGE
- CTF → NEG_RISK_CTF_EXCHANGE
- CTF → NEG_RISK_ADAPTER

## 使用方法

### 查看钱包状态

```bash
uv run python scripts/polyclaw.py wallet status
```

输出：地址、余额（POL + USDC.e）、授权状态

### 浏览市场

```bash
# 热门市场（按交易量排序）
uv run python scripts/polyclaw.py markets trending

# 搜索市场
uv run python scripts/polyclaw.py markets search "Bitcoin"
uv run python scripts/polyclaw.py markets search "NBA"

# 市场详情
uv run python scripts/polyclaw.py market <market_id>
```

### 买入

```bash
# 买 $5 的 YES
uv run python scripts/polyclaw.py buy <market_id> YES 5

# 买 $3 的 NO
uv run python scripts/polyclaw.py buy <market_id> NO 3
```

买入流程：
1. 用 USDC.e 调用 `splitPosition` 拆分成 YES + NO 代币
2. 通过 CLOB 订单簿卖掉不需要的那边
3. 如果 CLOB 卖出失败，你会同时持有 YES 和 NO（需要手动处理）

### 查看持仓

```bash
uv run python scripts/polyclaw.py positions
uv run python scripts/polyclaw.py positions --all
```

### 对冲扫描（需要 OPENROUTER_API_KEY）

```bash
uv run python scripts/polyclaw.py hedge scan
uv run python scripts/polyclaw.py hedge scan --query "election"
uv run python scripts/polyclaw.py hedge analyze <id1> <id2>
```

---

## ⚠️ 踩坑记录

### 坑 1：CLOB 地区限制（最大的坑）

**问题**：Polymarket CLOB API 按 IP 地理位置封禁，封禁地区包括美国、英国、法国、德国、澳大利亚等。

**症状**：
```
PolyApiException[status_code=403, error_message={'error': 'Trading restricted in your region'}]
```

**影响**：链上操作（split、approve）不受影响，但 CLOB 卖单会失败。导致买入时 split 成功但卖不掉不需要的代币，资金被锁。

**检测方法**：
```bash
curl -s "https://polymarket.com/api/geoblock"
# 返回 {"blocked": true/false, "ip": "...", "country": "...", "region": "..."}
```

**封禁地区完整列表**：
AU, BE, BY, BI, CF, CD, CU, DE, ET, FR, GB, IR, IQ, IT, KP, LB, LY, MM, NI, NL, RU, SO, SS, SD, SY, VE, YE, ZW（完全封禁）
PL, SG, TH, TW（仅可平仓）
US（完全封禁，包括所有州）

**未封禁的常用地区**：中国大陆(CN)、香港(HK)、日本(JP)、韩国(KR)、加拿大(CA)

**解决方案**：
- `HTTPS_PROXY` 设置为非封禁地区的代理
- 代码已内置代理支持（`lib/clob_client.py` 自动读取 `HTTPS_PROXY`）
- ⚠️ 注意：很多"全局代理"出口是美国 IP，美国是封禁的！必须确认代理出口 IP 不在封禁列表

### 坑 2：Nonce 冲突（wallet approve）

**问题**：`wallet approve` 连续发 6 笔交易，如果 RPC 节点有缓存延迟，`get_transaction_count` 返回旧 nonce，导致 "nonce too low" 错误。

**症状**：
```
Error: {'message': 'nonce too low: next nonce 3, tx nonce 2', 'code': -32000}
```

**解决方案**：已修复。使用 `get_transaction_count(address, "pending")` 获取初始 nonce，然后手动递增：
```python
nonce = w3.eth.get_transaction_count(address, "pending")
for tx in transactions:
    tx['nonce'] = nonce
    nonce += 1
```

### 坑 3：RPC 节点选择

**问题**：很多公共 Polygon RPC 需要 API key 或已废弃。

**测试过的 RPC**：
- ❌ `polygon-rpc.com` — 401 Unauthorized
- ❌ `rpc.ankr.com/polygon` — 需要 API key
- ❌ `polygon.llamarpc.com` — 超时
- ✅ `polygon.drpc.org` — 免费可用
- ✅ `1rpc.io/matic` — 有时可用
- ✅ Chainstack 付费节点 — 最稳定

推荐：开发测试用 `polygon.drpc.org`，生产环境用 Chainstack 付费节点。

### 坑 4：Split 成功但 CLOB 失败

**问题**：买入操作分两步（split + CLOB sell），如果第一步成功第二步失败，你会同时持有 YES 和 NO 代币。

**影响**：假设买 $3 YES，实际花了 $6（$3 在 YES，$3 卡在 NO 里）。

**处理方式**：
1. 等市场结算 — 无论结果如何，YES 或 NO 其中一个值 $1，另一个值 $0，总共回 $3
2. 用 `mergePositions` 把 YES + NO 合并回 USDC.e（需要等量）
3. 解决 CLOB 代理问题后手动卖出

### 坑 5：系统级代理污染

**问题**：服务器设置了系统级环境变量（`http_proxy`/`https_proxy`），导致所有请求都走代理，即使代码里没指定。

**检查**：
```bash
env | grep -i proxy
```

**影响**：
- 链上 RPC 请求走代理可能变慢
- CLOB 请求走了错误地区的代理被封

**解决方案**：在 `WalletManager` 的 Web3 初始化中显式禁用代理：
```python
Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60, "proxies": {}}))
```

### 坑 6：Polyclaw 平台 vs 开源 CLI

**区别**：
- **Polyclaw 平台**（polyclaw.ai）：SaaS 服务，AI 自动交易，需要 AI Credits，交易跑在他们服务器上
- **polyclaw-cli**（本地）：开源 CLI 工具，自己控制，直接跟 Polygon + CLOB 交互

Polyclaw 平台的坑：
- 需要额外购买 AI Credits 才能运行分析
- Low risk 模式（≥75% 置信度）可能长时间不下单
- Agent API Key 只显示一次，丢了就没了

---

## 合约地址（Polygon Mainnet）

| 合约 | 地址 |
|------|------|
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| CTF | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| CTF Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk CTF Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |

## 交易策略参考

文章来源：QuantML 公众号

1. **气象套利** — 对接 NOAA 气象模型，发现天气市场定价错误
2. **预言机滞后** — 监控大交易所价格异动，在 Polymarket 散户反应前抢跑
3. **终局交易** — 事件基本确定（>95%）时大手笔扫货，赚最后 1-5%
4. **情绪逆向** — NLP 抓取恐慌情绪，在市场极度扭曲时逆向下注

## 文件结构

```
polyclaw-cli/
├── .env                    # 环境变量配置
├── pyproject.toml          # Python 依赖
├── lib/
│   ├── clob_client.py      # CLOB 订单簿客户端（含代理+重试）
│   ├── contracts.py        # Polygon 合约地址和 ABI
│   ├── coverage.py         # 对冲覆盖率计算
│   ├── gamma_client.py     # Polymarket Gamma API 客户端
│   ├── llm_client.py       # LLM 对冲分析
│   ├── position_storage.py # 持仓本地存储
│   └── wallet_manager.py   # 钱包管理（余额、授权、签名）
└── scripts/
    ├── polyclaw.py         # CLI 入口
    ├── markets.py          # 市场浏览/搜索
    ├── trade.py            # 买入执行
    ├── positions.py        # 持仓查看
    ├── wallet.py           # 钱包状态/授权
    └── hedge.py            # AI 对冲扫描
```
