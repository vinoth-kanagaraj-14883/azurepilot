# AzurePilot — Demo Script

*A 10-minute walkthrough for engineering leadership*

---

## Setup (before the meeting)

```bash
git clone https://github.com/vinoth-kanagaraj-14883/azurepilot.git
cd azurepilot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn api.main:app --port 8000 &
python -m http.server 3000 --directory ui
```

Open: **http://localhost:3000** (UI) and **http://localhost:8000/docs** (API)

---

## Script

### Opening (1 min)

> "Every team running workloads on Azure has the same problem:
> you have Resource Health on one screen, metrics dashboards on another,
> and an alert inbox that's too noisy to trust.
> The result is that engineers spend hours correlating signals that should have
> been correlated automatically — and they find out about real incidents too late.
>
> AzurePilot is a copilot that does that correlation for you in real time,
> and tells you not just *what* is broken but *why* and *what to do next*."

---

### KPI Strip (1 min)

Point to the KPI strip at the top:

> "At a glance, I can see:
> - We have **N resources** monitored — VMs, App Services, Storage Accounts.
> - **N incidents** are active right now, **N of them critical**.
> - The estimated cost impact of these incidents is **$X**.
>   This is what we're burning if we don't act on these today."

---

### Top Risky Resources (2 min)

Point to the left panel:

> "The list is sorted by risk score — 0 to 100.
> The score combines Resource Health status with metric anomaly signals.
> Red means it needs attention now."

Click on the highest-risk resource (e.g., `stprodlogs` — Storage unavailable):

> "Let's look at this storage account. It has a risk score of 85 — Critical.
> Azure Resource Health is reporting it as Unavailable, and the Availability
> metric has dropped from 99.9% to around 60%."

---

### Incident Detail (3 min)

Walk through each section of the detail panel:

**Summary**
> "The AI has generated a plain-English summary of the incident — exactly what
> you'd want in a Slack notification or incident ticket."

**Contributing Metrics**
> "These are the metric signals that drove the risk score.
> Each one shows the current value vs the 24-hour baseline and a z-score —
> how many standard deviations above normal we are.
> The bar underneath shows each metric's contribution to the overall risk score."

**Root Cause Hypothesis**
> "This is the key differentiator. AzurePilot doesn't just say 'something is wrong'.
> It tells you whether this looks like a platform issue — Azure's fault —
> or a workload/configuration issue that your team needs to fix.
> That distinction alone saves 30-60 minutes of triage time per incident."

**Recommended Actions**
> "Three concrete next steps, ordered by priority.
> No need to go hunting through runbooks — the first action to take is right here."

**Cost Impact**
> "We estimate this incident is costing approximately $X in wasted or lost spend
> while it's unresolved.  This makes the business case for acting immediately,
> and gives you something concrete to put in the post-mortem."

---

### Second incident — workload issue (2 min)

Click on `vm-prod-web-01` (high CPU VM):

> "This one is different. Resource Health says the VM is Degraded,
> but this is *not* a platform issue — it's a CPU spike caused by the workload.
> The risk score is driven entirely by the Percentage CPU metric being
> 2-3 standard deviations above its 24-hour baseline.
>
> The recommended action tells you exactly where to start:
> SSH in, run top, and identify the offending process.
> If it's legitimate traffic, scale the VM."

---

### API Docs (1 min)

Open **http://localhost:8000/docs**:

> "Because this is built on FastAPI, we get OpenAPI documentation automatically.
> Every endpoint is explorable — this makes it easy to integrate with
> existing tooling: PagerDuty, Teams, ServiceNow, whatever you use today."

---

### Closing — ROI narrative (1 min)

> "The KPIs we track from day one:
>
> - **MTTR reduction** — engineers get root cause and next step immediately,
>   not after 45 minutes of dashboard triage.
>
> - **Alert fatigue reduction** — instead of N individual metric alerts,
>   you get one prioritised incident with context.
>
> - **Cost savings** — the cost overlay makes the impact of each incident
>   visible in dollar terms, so it's not just an engineering metric anymore.
>
> - **Engineer hours saved** — we estimate 2-4 hours per major incident
>   currently spent on correlation and root cause analysis.
>   AzurePilot compresses that to minutes.
>
> This is v1, running on demo data. The next step is wiring it to your
> real Azure subscription — which is one env var change."

---

## Q&A Prep

**"Does it require AI/LLM credits?"**
→ No. The mock summarizer produces realistic text without any API keys.
  LLM integration is opt-in and adds higher-quality narrative text.

**"How does it get the data?"**
→ Azure Resource Health API + Azure Monitor Metrics API.
  Same data your dashboards show — just correlated automatically.

**"What about alert fatigue — won't this just create more noise?"**
→ The opposite. Multiple metric signals for the same resource are collapsed
  into one incident. The risk score filters out low-signal events.

**"Is this production-ready?"**
→ This is a v1 prototype. The integration code is real and correct;
  what needs hardening for production is: persistent state, background
  polling, auth hardening, and notification integrations.
