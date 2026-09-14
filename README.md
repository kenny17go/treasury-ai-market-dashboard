# Treasury AI 市場一頁通 V1

一個可直接部署到 GitHub Pages 的市場晨報 Dashboard。前端只讀取 `data/*.json`，GitHub Actions 負責定時更新資料。

## V1 已包含
- S&P 500 / Nasdaq / Dow Jones / SOX
- 台灣加權 / 櫃買
- 美債 2Y / 10Y / 30Y（FRED）
- Gold / Silver / Copper / Brent / WTI
- DXY 與主要匯率，含 USD/TWD
- 24 檔自選股 + Sparkline
- Google News RSS 新聞雷達
- 今日重要經濟事件（Trading Economics guest feed 可用時）
- 規則式 Morning View；可選擇加入 OpenAI API 自動摘要
- 手機 / iPad / 桌面響應式版面

## 最快上線方式
1. 建立新的 GitHub repository。
2. 把 ZIP 解壓後的「所有檔案」上傳到 repository 根目錄；`.github` 資料夾也要一起上傳。
3. GitHub → **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。
4. GitHub → **Actions → Update market data → Run workflow**，先手動執行一次。
5. 等待 `Deploy GitHub Pages` 完成，即可開啟 Pages 網址。

> 若 Actions 顯示無法 push，請到 **Settings → Actions → General → Workflow permissions** 選 **Read and write permissions**（本專案也已在 workflow 宣告 `contents: write`）。

## 自動更新頻率
`.github/workflows/update-market.yml` 預設週一至週五每 30 分鐘執行一次。GitHub 排程不是秒級準時，忙碌時可能延遲。

## 修改 24 檔自選股
編輯 `config/market.yml` 的 `stocks:` 區塊即可。`symbol` 使用 Yahoo Finance ticker；`label` 是頁面顯示文字。

## OpenAI AI 摘要（選用）
不設定 API Key 也能使用，系統會以規則式摘要產生 Morning View。

如要開啟 AI 摘要：
1. Repository → **Settings → Secrets and variables → Actions**。
2. 新增 Repository secret：`OPENAI_API_KEY`。
3. 可選擇新增 Repository variable：`OPENAI_MODEL`，預設為 `gpt-5.6-luna`。
4. 再執行一次 `Update market data`。

API 使用會產生 OpenAI API 費用，與 ChatGPT 訂閱分開計費。

## 資料來源與限制
- Yahoo Finance / yfinance：指數、股票、商品、外匯。可能延遲、變更 ticker、或短暫限流。
- FRED：美國公債殖利率，日頻率，非即時報價。
- Google News RSS：新聞標題與連結。
- Trading Economics guest feed：僅作 V1 經濟日曆的無金鑰備援，若 guest feed 不回傳當日資料，頁面會顯示空狀態。

本網站不是交易系統，也不應作為唯一價格來源。

## 主要檔案
```text
index.html
assets/style.css
assets/app.js
assets/icon.svg
config/market.yml
scripts/update_data.py
requirements.txt
data/*.json
.github/workflows/update-market.yml
.github/workflows/pages.yml
```

## V1.1 建議
- 將經濟日曆改為你指定的付費 / 公司內部資料源
- 加入 VIX、MOVE、SOFR、2s10s、Fed funds futures
- 加入台灣外資期貨淨部位
- 自訂 Watchlist UI（直接在網頁編輯）
- 新聞分類 / 搜尋 / 去重優化
