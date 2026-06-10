# 失物櫃台：Caption-first 的活動場館失物歸還工作台

## 一句話

**失物櫃台讓活動場館、conference、健身房、共享空間、學校與前台人員，把「一件物品一張照片」的失物建檔流程變成可搜尋的歸還工作台；認領者透過私密對話補完整描述，工作人員在後台審核候選匹配並完成線下交還。**

這不是「AI 幫你猜主人」的系統。它是一個讓工作人員少翻箱子、少猜訊息、少來回詢問的 return workflow。AI 的工作是把一堆失物縮小成幾個有理由的候選，最後的判斷和交還仍然由工作人員完成。

---

## 問題：每個場館都有同一種無聊但高摩擦的工作

活動結束後，櫃台常常會留下：水壺、外套、充電器、badge、袋子、耳機盒、鑰匙、雨傘、筆記本和各種配件。

認領訊息通常不是精確資料，而是這種句子：

> I lost a bottle, maybe in Room B.

對工作人員來說，麻煩不在於「完全不知道怎麼辦」，而在於每次都要做很多小事：翻照片、翻箱子、回訊息、追問細節、確認身份、避免誤領。這是一個很適合 Backyard AI 的問題：真實、瑣碎、非技術使用者每天都會遇到，而且小模型就足夠有用。

---

## 最終產品流程

```text
工作人員一件物品拍一張照片
  -> MiniCPM-V 產生 caption
  -> item 進入 inventory
  -> 認領者進入 Claim Assistant 對話
  -> MiniCPM5 問安全 follow-up 問題
  -> claim summary 進入 staff inbox
  -> MiniCPM5 把 claim 與 inventory captions 放進同一個 prompt 找候選
  -> staff-only review board 顯示照片、caption、理由
  -> app 草擬安全確認訊息
  -> 工作人員線下確認並記錄 handoff
```

這條流程有三個核心原則：

1. **One item, one photo**：工作人員拍照時就把物品分開。
2. **One item, one caption**：VLM 產生一段可搜尋、可閱讀、可比對的描述。
3. **Staff-controlled handoff**：候選只給工作人員看，系統不判定歸屬。

---

## 主要設計決策

### 1. 從「學校與家長」擴展成「venue / event front desk」

最早的版本很像學校 lost-and-found：老師拍物品，家長傳訊息，系統幫忙找候選。後來我們把主場景擴展到 conference、gym、coworking space、event venue、sports club 和 school office。

原因是 lost-and-found 不是單一教育場景的痛點，而是任何前台都會遇到的營運雜務。這個改動讓產品更通用，也更適合比賽：它可以服務真實的非技術使用者，而且 demo 可以在任何活動場地重現。

### 2. 不做 segmentation：一件物品一張照片

我們刻意移除了「拍一張桌面照，系統自動切出 25 件物品」的設計。

這聽起來很酷，但在 hackathon 裡風險很高：失物會重疊、反光、被桌面顏色吃掉，切錯後 caption 和 matching 都會壞。更重要的是，前台人員其實可以很自然地一件一件拍，這比讓 segmentation 成為核心技術風險更符合現場。

所以新的規則是：

> **one item, one photo**

這讓 app 的重點回到真正有價值的地方：快速建檔、產生可搜尋描述、收集更好的認領描述、幫 staff 找候選。

### 3. 不做 OCR pipeline：VLM caption 直接處理可見文字

我們也移除了獨立 OCR component。

MVP 不需要把所有文字欄位抽成結構化資料。MiniCPM-V 的任務是產生一段人和模型都看得懂的 caption。當照片裡有姓名、電話、badge ID、access card、student label 之類的敏感文字時，它不應該轉錄，而是只寫：

```text
visible identifying text present
```

這樣保留 privacy signal，但不新增一條 OCR pipeline，也不鼓勵系統把私人資訊變成公開 trace。

### 4. 不建 embedding index：MVP 用 prompt-packed inventory search

原本有 local embeddings + deterministic matcher 的想法。後來我們把 MVP 改成：對 25 到 100 件物品的 demo inventory，直接把 unclaimed item captions 放進 MiniCPM5 的 prompt。

```text
claim summary + inventory captions + safety rules -> ranked staff candidates
```

原因有三個：

- demo inventory 小，沒有必要先做 retrieval infrastructure；
- prompt-packed search 更容易讓評審理解；
- 核心價值不是搜尋引擎，而是安全、可審核、能完成 handoff 的工作流。

未來如果 inventory 變成幾千件，可以在 prompt 前加 retrieval layer。但 MVP 不需要先把系統變複雜。

### 5. Public Claim Form 改成 Claim Assistant

靜態表單太平，因為使用者常常只會寫：

```text
I lost a bottle.
```

所以我們把 public form 改成 conversational intake。Claim Assistant 會問開放式 follow-up 問題，例如：

```text
What color was it?
Where did you last see it?
Do you remember any sticker, logo, brand, cap color, scratch, label, contents, or other distinctive mark?
```

但它有一條重要限制：

> 它可以問「缺少哪一類資訊」，但不能透露 inventory 裡尚未由認領者提到的具體物品細節。

安全問法：

```text
Do you remember any sticker or logo? Please describe it.
```

不安全問法：

```text
Did it have a white conference sticker?
```

除非認領者自己已經先提到 white conference sticker，否則 claimant-facing assistant 不應該主動洩漏。

### 6. Staff-controlled handoff

系統永遠不向認領者說：

```text
This is yours.
```

它只對 staff 說：

```text
This is a likely candidate. Review privately and confirm offline.
```

原因很現實：實體物品歸還牽涉責任、隱私和誤領風險。AI 的工作是縮小搜尋範圍，不是做 ownership decision。

### 7. MiniCPM-V + MiniCPM5，而不是雲端商業 LLM

模型選擇也是產品論述的一部分：

- **MiniCPM-V 4.6** 負責 item photo captioning。
- **MiniCPM5-1B** 負責 Claim Assistant、candidate reasoning 和 message drafting。
- 預設不需要商業 hosted LLM API。
- 模型規模保持在 tiny / edge AI 的敘事裡。

這讓專案更適合 Off the Grid / Tiny Titan 類型的獎項：它不是把問題丟給大型雲端 API，而是用小模型解一個非常具體的前台工作流。

### 8. Portable runtime：ZeroGPU / CUDA / MPS

這個 app 被設計成同一套 backend 可以跑在：

- Hugging Face ZeroGPU
- 一般 CUDA GPU
- Mac Apple Silicon MPS
- explicit mock mode for tests and CPU-only UI review

技術上我們加了一個 runtime adapter：

```text
runtime/device.py       -> auto-detect zerogpu / cuda / mps / cpu
runtime/gpu.py          -> maybe_zerogpu() only imports spaces on ZeroGPU
models/minicpm_v.py     -> MiniCPM-V adapter
models/minicpm5.py      -> MiniCPM5 adapter
models/mock.py          -> explicit mock implementation
```

預設啟動就是：

```bash
LFD_MODEL_MODE=real LFD_DEVICE=auto python app.py
```

Mock mode 只作為 reviewer / CPU-only / test path，不再是產品預設。Real-model failure 預設會直接浮出錯誤；只有明確設定 `LFD_ALLOW_MOCK_FALLBACK=1` 時才會走 rule-based mock fallback。

### 9. Gradio Server mode + compiled Svelte frontend

這不是單頁模型 demo，所以我們不用 `gr.Blocks` 當主要 UI。它需要 dashboard、intake、claim chat、inbox、review、return log。

因此 app 使用 `gradio.Server`：

- FastAPI routes 處理 CRUD、file uploads、static frontend。
- `@app.api()` endpoints 處理模型工作。
- Svelte frontend 呼叫 REST routes 與 Gradio API endpoints。
- 編譯後的 Svelte app 已經放在 `static/`，所以 Hugging Face Space 不需要 Node build step。Staff item photos 不掛成公開靜態目錄；前端用 staff password 透過 staff-only photo route 抓取 blob，再轉成瀏覽器內部 object URL 顯示。這讓 Claim Assistant 不會取得 inventory photo URLs。

在 ZeroGPU 環境裡，前端會把模型重的操作切到 `@gradio/client` 呼叫 Gradio API endpoint。這樣符合 Gradio Server mode 對 browser + ZeroGPU quota handling 的官方建議。

---

## Information Architecture

### Page 1: Return Desk

工作人員主控台。

顯示：

- items catalogued
- claims received
- ready for review
- returned
- recent items
- open claims
- public claim link

### Page 2: Item Intake

一件物品一張照片。

欄位只有：

- item photo
- found location
- optional staff note
- generated caption
- privacy note

不做 segmentation，不做 tag editor，不做 detailed schema。

### Page 3: Claim Assistant

給認領者使用的 conversational intake。

它會：

- 收集描述
- 問安全 follow-up 問題
- 產生 claim summary
- 收集聯絡方式
- 提交給 staff review

它不會：

- 展示失物照片
- 展示候選清單
- 告訴認領者「找到了」
- 透露 inventory 中尚未被認領者提到的細節

### Page 4: Claim Inbox + Match Review

staff-only 核心頁。

顯示：

- claim summary
- transcript
- candidate items
- item photo
- item caption
- why suggested
- staff next step
- safe claimant message
- mark returned after offline confirmation

### Page 5: Return Log / Field Report

給 demo 結尾和評審看的 closure page。

顯示：

- items catalogued
- claims received
- returned items
- auto-ownership decisions = 0
- public photo exposures = 0
- claimant-visible ranked candidates = 0
- return logs

---

## Evaluation Plan

| Metric | Target |
| --- | ---: |
| Top-3 match recall | >= 0.90 |
| Wrong strong-candidate rate | <= 0.03 |
| Sensitive text redaction recall | 1.00 |
| Caption usefulness judged by staff | >= 4/5 |
| Average intake time per item | <= 10 seconds |
| Staff search time reduction | >= 60% |
| Claimant-visible ranked candidates | 0 |
| Public item photo exposure | 0 |
| Auto-ownership decisions | 0 |

The key claim is not “the AI knows whose item this is.” The key claim is:

> **The AI cuts the pile down to a small, reviewable set with visible reasons, while staff keep control of confirmation and handoff.**

---

## Demo script

1. Staff opens Return Desk for a conference.
2. Staff adds a black bottle by uploading one photo.
3. MiniCPM-V produces: “Black insulated water bottle with a silver cap and a white conference sticker. Found near Workshop Room B.”
4. Claimant opens the QR link and says: “I lost a bottle.”
5. Claim Assistant asks for color and location.
6. Claimant answers: “Black, maybe Room B.”
7. Claim Assistant asks for open-ended distinctive marks.
8. Claimant answers: “White conference sticker and silver cap.”
9. Staff opens Claim Inbox and clicks Find candidates.
10. Candidate card shows item photo, caption, evidence, and safe next step.
11. Staff marks returned only after offline confirmation.
12. Report shows 0 auto-ownership decisions and 0 public photo exposures.

---

## Known limitations and honest tradeoffs

- Prompt-packed inventory search is ideal for small to medium event inventories. For larger archives, add retrieval before the prompt.
- VLM privacy behavior should be evaluated with real photos containing names, badges, and access cards before production use.
- Staff password is intentionally simple for a hackathon demo. Production should use real auth and role-based access.
- Local JSON storage is enough for demo. Production should use SQLite/Postgres and retention policies.
- Explicit mock mode keeps CPU-only UI review possible, but it is not a substitute for real MiniCPM model evaluation.

---

## Why this is a strong Backyard AI project

It has a real user, a visible workflow, and a measurable benefit. A front-desk volunteer or event staffer can understand the value without knowing anything about embeddings, OCR, segmentation, or model APIs.

The technical decisions are intentionally restrained:

- no segmentation because the user can photograph one item at a time;
- no OCR pipeline because captioning is enough for MVP;
- no embeddings because the inventory is small enough to prompt-pack;
- no public gallery because privacy matters;
- no AI ownership decision because the final handoff is a human responsibility.

The result is not a flashy model demo. It is a compact, field-ready operations tool.

---

## Sources

- Gradio Server mode guide: https://www.gradio.app/guides/server-mode
- Gradio Server docs: https://www.gradio.app/docs/gradio/server
- Gradio JavaScript client docs: https://www.gradio.app/docs/js-client
- Hugging Face ZeroGPU docs: https://huggingface.co/docs/hub/en/spaces-zerogpu
- MiniCPM-V 4.6 model card: https://huggingface.co/openbmb/MiniCPM-V-4.6
- MiniCPM5-1B model card: https://huggingface.co/openbmb/MiniCPM5-1B
- Svelte docs: https://svelte.dev/docs/svelte/overview
- Vite: https://vite.dev/
