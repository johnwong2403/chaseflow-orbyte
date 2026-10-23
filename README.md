# ChaseFlow for Orbyte

> An invoice-collections assistant for Malaysian SMEs: it spots overdue invoices, explains the risk with transparent rules, drafts a polite reminder in the customer's own language, and sends nothing until the owner approves. *(ChaseFlow is a working name.)*

---

## Team Information

| Field                  | Details                                                    |
| ---------------------- | ---------------------------------------------------------- |
| **Team Name**          | ZH                                                         |
| **Team Domain**        | Domain 2 — Orbyte Smart SME Challenge                      |
| **SDG Track (1–17)**   | SDG 8 — Decent Work and Economic Growth (targets 8.2, 8.3) |
| **Team Leader**        | Wong Zong Han                                              |
| **University**         | Asia Pacific University of Technology & Innovation (APU)   |
| **Number of Members**  | 1 (solo)                                                   |

## Links

| Resource          | Link                                                    |
| ----------------- | ------------------------------------------------------- |
| GitHub Repository | https://github.com/johnwong2403/chaseflow-orbyte        |
| Replit Project    | https://replit.com/@johnwong2403/chaseflow-orbyte       |
| Live Demo         | https://chaseflow-orbyte.replit.app                     |
| RunPod Endpoint   | Not used (no GPU workload, see "How We Use RunPod")     |
| Slide Deck        | [SDC2026 ZH ChaseFlow for Orbyte.pptx](submission/SDC2026%20ZH%20ChaseFlow%20for%20Orbyte.pptx) |
| Demo Video        | https://youtu.be/_GFfbwycyyA                            |

---

## Overview

### Problem

Many micro and small businesses chase late payments by hand: scrolling through spreadsheets, then writing WhatsApp messages one by one. Owners often do this in the evening, forget who was already reminded, and either send nothing or send a message that is too soft or too harsh for that customer. Late payments hurt cash flow, which is exactly what small businesses can least afford.

### Solution

ChaseFlow runs one complete journey: **trigger → connected data → decision → human approval → visible outcome**.

1. **Trigger:** "Check Overdue" scans all invoices that are past their due date and still unpaid.
2. **Connected data:** each invoice is joined with its customer (language, phone) and payment history (how often they paid late, and any payment promises they made).
3. **Decision:** a transparent **rule** sets the risk tier (low / medium / high). **Google Gemini** then explains the risk in plain English, recommends an action, and drafts the reminder in English, Bahasa Malaysia or Chinese. Gemini may move the tier by one level and must say why.
4. **Human approval:** the owner edits and approves. Sending is **simulated** and nothing leaves the app.
5. **Outcome:** the approved reminder is written to an Activity Log. If the customer replies with a date, the owner records a **payment promise**; the app works out by itself whether it was kept, paid late or broken, and the next draft takes that into account.

AI is used only where it adds value (explaining and writing). The risk rule, the status of each promise and all numbers are plain code, so the owner can check them by hand.

### Key Features

- **Overdue check and recovery queue** — riskiest invoices first, with the reason shown next to each one.
- **Transparent risk rule + AI explanation** — the rule and the AI's reasoning are labelled separately, and the badge shows when the AI changed the tier.
- **Three-language reminders** — English, Bahasa Malaysia, 中文, taken from the customer record; a rule-based fallback is used if the AI is unavailable.
- **Human approval and Activity Log** — every approved reminder is recorded with risk tier, language and approver.
- **Customers and Invoices pages** — outstanding amounts, payment record, timeline, search and filters, mark-as-paid with undo, CSV export.
- **Payment promises** — record "customer will pay on date X"; status (promised / kept / paid late / broken / replaced) is derived from the real payment, never typed in.
- **Dashboard** — overdue amount, ageing chart, risk mix and exposure by customer, all computed from the current data.
- **Reset demo data** — puts the synthetic data back to its starting state.

### Tech Stack

| Layer         | Technology                                              |
| ------------- | ------------------------------------------------------- |
| Frontend      | Server-rendered HTML (Jinja2), CSS, small vanilla JS; charts are inline SVG drawn on the server |
| Backend       | Python 3, Flask                                         |
| Database      | None for the prototype: in-memory synthetic data (see Limitations) |
| AI            | Google Gemini API (`gemini-flash-lite-latest`) called with `requests` |
| AI / Compute  | No GPU used; RunPod not used                            |
| Hosting / Dev | Replit (workspace + Autoscale deployment)               |

---

## Project Structure

```
.
├── src/
│   ├── main.py              # Flask routes: dashboard, overdue, draft, approve, customers, invoices, promises
│   ├── data.py              # Synthetic data + business logic (overdue, promises, mark paid / undo)
│   ├── reminder_ai.py       # Risk rule, Gemini call, retry, cache, rule-based fallback
│   └── charts.py            # Server-side SVG charts
├── templates/               # Jinja2 pages
├── static/                  # style.css, logo
├── submission/              # Submission documents (PRD, declaration, Replit proof, slide deck)
├── tests/
│   └── test_core.py         # Unit tests (risk rules, promises, undo, AI prompt, fallback)
├── .env.example             # Example environment variables
├── .gitignore
├── .replit                  # Replit run and deployment configuration
├── LICENSE                  # Apache License 2.0
├── requirements.txt         # Python dependencies
└── README.md
```

### Architecture

```
Owner (browser)
   │
   ▼
Flask app on Replit ──► data.py  (synthetic customers, invoices, activity log, promises; in memory)
   │
   ├──► rules (risk tier, promise status)         ← plain code, no AI
   │
   └──► Gemini API (explain risk + draft message) ← only after the owner opens an invoice
            │
            └─ if it fails: one retry, then rule-based draft (never an empty screen)
   │
   ▼
Owner edits and approves ──► Activity Log   (sending is simulated; nothing is delivered)
```

In a real Orbyte deployment, customers would come from the People module and invoices and payments from the Connect module; here they are synthetic stand-ins in `src/data.py`.

---

## How to Run

### Option 1 — Run on Replit (Recommended)

1. Open the Replit project, or import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab and add the variable from `.env.example`:
   - `GEMINI_API_KEY`
3. Click **Run**. Replit uses the `.replit` file to start `python src/main.py`.

Without `GEMINI_API_KEY` the app still works, but drafts use the fixed rule-based templates and are labelled "Rule-based fallback".

### Option 2 — Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/johnwong2403/chaseflow-orbyte.git
cd chaseflow-orbyte

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
export GEMINI_API_KEY=your-key  # Windows PowerShell: $env:GEMINI_API_KEY="your-key"

# 5. Run the app
python src/main.py              # then open http://localhost:5000
```

### Run Tests

```bash
python -m unittest discover tests
```

---

## How We Use Replit *(Required)*

- **Development:** the code is edited and run in a Replit workspace; the Run button starts `python src/main.py` for live preview and testing.
- **Hosting:** the app is deployed with Replit **Autoscale** at the Live Demo link above (set to one machine so the in-memory demo data stays consistent).
- **Secrets:** the Gemini API key is stored in Replit Secrets and read from the environment. It is never kept in the code.

📄 Proof of use: [`submission/REPLIT PROOF OF USE.pdf`](submission/REPLIT%20PROOF%20OF%20USE.pdf)

## How We Use RunPod *(Required)*

RunPod is **not used**. The only AI component is the Google Gemini API, which runs on Google's servers; the project has no workload that needs a GPU (no model training, fine-tuning or self-hosted inference).

---

## Data, Privacy and Safety

- **All data is synthetic.** Customer names, phone numbers and invoices are made up for this prototype. No real personal, customer or company records are used.
- **Nothing is really sent.** "Approve & Send" only records the reminder in the Activity Log. There is no WhatsApp or email connection, and no real Orbyte connection.
- **Out of scope:** real payments, statutory filings, and legal or financial advice.
- **If deployed for real**, under Malaysia's PDPA the app would collect only the customer details needed for collection, keep them for a limited time, tell customers how their data is used, restrict who can view them by role, and avoid sending personal data to the AI beyond what the draft needs (for example, name, invoice number and amount).

## How AI Was Used

- **Inside the product:** Google Gemini explains the risk and drafts the reminder. Its JSON output is validated before use, and the owner always reviews the text.
- **To build the product:** the idea was brainstormed together with AI assistants, and most of the code was written by Claude (Anthropic) following the team leader's instructions. The team leader decided the scope, tested each version on the live site, and asked for fixes. The full list of tools is in the Technical & Tools Declaration.

## Limitations

- Data lives in memory, so it resets when the server restarts or sleeps; there is no database yet.
- Gemini's free quota can rate-limit rapid clicks. The app retries once, caches finished drafts, and falls back to rule-based text.
- The interface is English only; reminder messages come in three languages.
- Payments are recorded as one full payment per invoice; part-payments are not supported.
- Promises are entered by the owner; the app does not read WhatsApp replies.

---

## Challenges & Learnings

- **AI rate limits:** the first live tests fell back to template text because Gemini returned HTTP 429. We added one automatic retry, a draft cache, and a background warm-up of the other two languages.
- **State on Replit Autoscale:** with several machines, "mark as paid" appeared to undo itself because each machine had its own memory. We limited the deployment to one machine and added Undo and a Reset button.
- **Trust in AI output:** the model's answer is validated, its reasoning is shown separately from the rule, and a human approves every action.
- **Not inventing data:** we chose not to draw forecasts or trends the data cannot support.

## Future Improvements

- [ ] Replace in-memory data with a database (SQLite / Postgres)
- [ ] Connect to Orbyte's People and Connect modules instead of synthetic data
- [ ] Send approved reminders through WhatsApp Business after explicit owner approval
- [ ] Support part-payments and instalment promises
- [ ] Malay and Chinese user interface
- [ ] Test with real SME owners to validate the workflow and the time saved

## Team

| Name           | Role                         | GitHub                                    |
| -------------- | ---------------------------- | ----------------------------------------- |
| Wong Zong Han  | Solo: product, build, testing | [@johnwong2403](https://github.com/johnwong2403) |

---

## Submission Checklist

- [x] Team name, domain (Domain 2) and SDG track filled in
- [x] Slide deck link added
- [x] Demo video link added
- [x] Replit used, with proof of use in `submission/`
- [x] RunPod: not used, explained above
- [x] Submission template completed in `submission/`
- [ ] "How to Run" steps verified
- [ ] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
