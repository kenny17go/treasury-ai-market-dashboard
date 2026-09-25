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

## Market Brief 開發原則（2026-09-25，後續開發必讀）

**先學準 → 再做穩 → 再補不足 → 最後才談智慧化。**

本專案的 Market Brief 目標是讓使用者在數十秒內掌握當日主要市場事件，不是打造另一套投資研究模型。參考 [旺來 Daily Report](https://github.com/wowwow3100-ctrl/daily-report) 的新聞呈現方式，但不得宣稱已取得其未公開的上游選稿演算法，也不得直接複製未經驗證的推測。

### 已觀察到的參考網站行為
- 首頁將「盤前快訊」與「今日焦點」分開：前者是較廣泛的新聞清單，後者是精選 Top 5，另可展開 5 則。
- Git 歷史顯示新聞焦點隨盤後、夜間、次日早盤重新選稿；例如 2026-09-24 盤後偏台股收盤及法人／個股，夜間加入美中會談與券商觀點，2026-09-25 早盤轉向美中會談、美債及海外股市。
- 公開 repository 的首頁包含已整理完成的焦點 HTML；目前公開 workflow 主要是營收資料，未見完整新聞選稿產生器。上游可能另有程式或人工流程，**尚未確認**。

### 本站固定的新聞選擇原則
1. **先把來源與搜尋主題做好。** 優先使用可信、涵蓋宏觀與跨資產的新聞來源；保留原文連結、來源及時間。
2. **採簡單、可解釋的規則。** 現階段沿用來源品質、主題／關鍵字、時效、去重與基本主題分散；分數只供內部排序，**不把它當成客觀市場重要性或準確率**。
3. **時段式重選焦點。** 盤前、盤中／盤後、夜間、次日早盤應允許新重大事件取代舊聞；避免同一事件的多篇轉載占滿 Top 5。實際時段與頻率須以現有排程及資料品質為準，先觀察再調整。
4. **簡潔呈現。** 首屏以 Top 5 為主；較多新聞可展開，與價格、利率、匯率、商品及日曆等原有資料互相連結。關聯資產／入選原因可作為輔助，不要喧賓奪主。
5. **核心零 AI 依賴。** 抓取、去重、選稿及呈現不要求 AI；AI 僅供使用者主動要求的深入解讀。
6. **有證據才進化。** 先比較本站與參考網站連續數日的入選／漏選案例，記錄實際改善，再決定是否調整來源、搜尋 query 或簡單規則。

### 明確不做（除非使用者另行同意）
- 不新增 Market Importance Engine V2/V3、複雜加權評分、價格反應打分或缺乏驗證的預測模型。
- 不因單日案例大幅調整權重，不為了功能數量犧牲原本穩定的資料更新與 UI。
- 不將旺來「實際呈現行為」誤寫成已確認的內部演算法。

參考 commit：[2026-09-24 夜間更新](https://github.com/wowwow3100-ctrl/daily-report/commit/c931432e73)、[2026-09-25 早盤更新](https://github.com/wowwow3100-ctrl/daily-report/commit/7d8ac61311a9eb2953ce0d6c375b407820a5b3e2)。
