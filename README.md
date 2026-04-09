# FCN票据DIY计算器

Sell Put + 100%现金保证金 = 自制FCN票据。输入股票代码、折扣、期限、本金，自动查询真实期权链并计算年化收益率。

## 使用方法

1. 输入**股票代码**（如 AAPL、TSLA、NVDA）
2. 设置**折扣**（如 10% 表示行权价 = 现价 × 90%）
3. 选择**期限**（月），自动匹配最近到期日
4. 输入**投资金额**，点击计算

## 输出结果

- 匹配到的实际行权价和到期日
- 期权 Bid/Ask 报价和隐含波动率
- 可卖合约数、占用保证金
- 收取期权金（票息）
- **年化收益率**
- 盈亏平衡价和下行保护幅度

## 原理

```
年化收益 = (期权金 / 行权价) × (365 / 天数)
```

卖出 Put 并存入 `行权价 × 100 × 合约数` 现金作为 100% 保证金，经济效果等同于一张 FCN（Fixed Coupon Note）票据。到期时股价高于行权价，全额收回本金 + 票息。

## 部署

### 前端
静态 HTML，部署到 GitHub Pages 或任意静态托管。

### API 代理（Cloudflare Worker）
浏览器无法直接访问 Yahoo Finance API（CORS 限制），需要部署 `worker.js` 作为代理：

```bash
npm install -g wrangler
wrangler login
wrangler deploy worker.js --name fcn-api
```

部署后将 Worker URL 填入 `index.html` 中的 `WORKER_URL` 变量。

## License

MIT
