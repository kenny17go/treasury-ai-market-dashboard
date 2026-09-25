# Market Brief 參考網站選稿觀察（2026-09-25）

目的：以可追溯的 Git 歷史學習旺來 Daily Report 的新聞呈現，不將外部網站的新聞標題視為已獨立查證的事實，也不臆測未公開的選稿演算法。

## 實際檢查的八個快照

| 時段 | commit | Top 5 的選稿特徵 |
|---|---|---|
| 09/23 早盤 | [202767e93](https://github.com/wowwow3100-ctrl/daily-report/commit/202767e93) | 美股、台積電 ADR、國際會談、前日台股與法人 |
| 09/23 盤後 | [455ef117d](https://github.com/wowwow3100-ctrl/daily-report/commit/455ef117d) | 台股收盤、三大法人、強勢股、企業事件、工業生產 |
| 09/23 夜間 | [1e2496287](https://github.com/wowwow3100-ctrl/daily-report/commit/1e2496287) | 夜盤期貨、國際會談、OECD、能源、利率 |
| 09/24 早盤 | [08b6c3a0e](https://github.com/wowwow3100-ctrl/daily-report/commit/08b6c3a0e) | 美債／美股、貿易談判、國際事件、PMI、能源 |
| 09/24 收盤 | [725f0cf65](https://github.com/wowwow3100-ctrl/daily-report/commit/725f0cf65) | 台股收盤、個股券商觀點、盤中強勢股、散熱 |
| 09/24 盤後 | [d5a7c844e](https://github.com/wowwow3100-ctrl/daily-report/commit/d5a7c844e) | 法人買賣超、台股收盤、政策、個股券商觀點 |
| 09/24 夜間 | [c931432e7](https://github.com/wowwow3100-ctrl/daily-report/commit/c931432e7) | 國際會談、聯發科券商觀點、台積電盤後交易、光通訊、法人 |
| 09/25 早盤 | [7d8ac6131](https://github.com/wowwow3100-ctrl/daily-report/commit/7d8ac6131) | 國際會談與貿易、海外股債、歐股；前日台股不再占據 Top 5 |

## 觀察與限制

1. **時段重新選稿**：同日盤後與夜間的 Top 5 可以大幅不同；次日早盤再以隔夜國際與跨資產事件為主。
2. **Top 5 + 可展開另外 5 則**：首頁讓使用者先讀少量焦點，但保留第二層新聞。
3. **不是嚴格時間排序**：例如 09/25 早盤 Top 5 的新聞時間依序是 06:00、00:09、01:27、前日 21:57、01:21。
4. **仍有同題多則現象**：09/25 早盤前三則均圍繞美中會談／延伸議題，顯示不能直接假定其已完成事件級去重。
5. **盤前快訊與今日焦點分開更新**：09/25 盤前快訊與早盤焦點分別有獨立的 commit；前者保留新聞來源及原始連結，後者是帶摘要的精選清單。
6. **無法確認精確選稿權重**：公開首頁是完成的 HTML，已檢查的公開 workflows／tools 未提供完整新聞生成器；以上僅為結果反推。

## 對本專案的最低成本改進方向（尚未實作）

- 維持 Google News + Bing RSS、原有來源品質與簡單去重，暫不擴充 Importance Engine。
- 先在現有排程內加入「盤前／盤後／夜間」的**搜尋 query 組合切換**，而不是新增多套資料抓取流程。
- Top 5 保持首屏簡潔；若日後加入第二層新聞，應先確認現有 UI 和資料量。
- 對相同事件的不同標題建立人工比對案例；僅在確認漏掉重要新聞或重複占位時，才微調去重規則。
- 觀察至少數個交易日並記錄：參考網站 Top 5、本站 Top 5、漏選原因、重複原因、調整後差異。
- **正式修改前先檢查最新 GitHub 狀態與既有排程，並以最小變更測試，不動其他 Dashboard 功能。**
