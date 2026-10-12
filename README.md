# TeamMind --- Collaborative Multi-Agent Decision Intelligence

TeamMind turns decisions into structured, reviewable reports. It
combines manual decision inputs and Omi voice conversations with
semantic memory and a multi-agent workflow to help users compare
options, examine risks, and understand what could change a
recommendation.

> **Build track:** Collaborative Multi-Agent Workflows\
> **Hackathon stack:** Omi × Qdrant × Lyzr

## Live Demo

-   **Frontend:** https://team-mind-eta.vercel.app
-   **Backend API:** https://teammind-2z8p.onrender.com
-   **Repository:** https://github.com/Sumit182004/TeamMind

The backend may take a short time to wake up if it is on a free hosting
tier.

## The Problem

Important decisions are often made from scattered conversations,
incomplete context, and unexamined assumptions. A single AI response may
not clearly expose alternative options, counterarguments, evidence gaps,
or failure scenarios.

TeamMind brings decision context together and runs it through
specialized agents. The resulting report includes a recommendation,
trade-offs, counterarguments, uncertainties, next steps, and a stress
test.

## What TeamMind Does

-   **Create a decision manually:** Enter a title, problem statement,
    and options.
-   **Capture voice context with Omi:** Receive transcript segments
    through an Omi webhook and review/select the segments relevant to a
    decision.
-   **Remember useful context:** Store and retrieve semantically
    relevant memories using Qdrant.
-   **Run a multi-agent workflow:** Specialized agents research,
    analyze, challenge, verify, stress-test, and synthesize the
    decision.
-   **Review the final report:** See the recommendation and its
    reasoning, trade-offs, counterarguments, uncertainties, next steps,
    and stress-test scenarios.
-   **Keep a decision history:** Reopen saved decisions and their
    reports.

## Architecture

``` mermaid
flowchart TD
    U[User] --> UI[React + TypeScript + MUI frontend]
    O[Omi app / voice conversation] -->|Webhook: transcript segments| API[FastAPI backend]
    UI -->|REST API: create or run decision| API

    API --> DB[(SQLite: decisions and app records)]
    API --> EMB[FastEmbed: text embeddings]
    EMB --> Q[(Qdrant vector memory)]
    API -->|Relevant retrieved memories + decision context| WF[Decision workflow]
    WF --> R[Researcher agent]
    WF --> A[Analyst agent]
    WF --> D[Dissent Engine agent]
    WF --> V[Verifier agent]
    WF --> S[Stress Tester agent]
    R --> SYN[Synthesizer / final report]
    A --> SYN
    D --> SYN
    V --> SYN
    S --> SYN
    SYN --> API
    API -->|Report and agent runs| UI

    WF -. orchestrated agent calls .-> L[ Lyzr agent / workflow services ]
```

### Architecture walkthrough

1.  **Input:** A user creates a decision in the frontend or brings in a
    conversation captured by Omi.
2.  **Webhook ingestion:** Omi sends transcript data to the FastAPI
    endpoint. The backend processes the received segments and makes them
    available to the app's memory/decision flow.
3.  **Memory:** Text is embedded with FastEmbed and stored in Qdrant.
    When a decision runs, the backend can retrieve semantically relevant
    context.
4.  **Decision workflow:** The backend coordinates specialized agents:
    -   **Researcher** --- gathers considerations and relevant context.
    -   **Analyst** --- compares the options against the stated
        criteria.
    -   **Dissent Engine** --- challenges the leading choice and
        surfaces counterarguments.
    -   **Verifier** --- checks assumptions, consistency, and evidence
        gaps.
    -   **Stress Tester** --- explores failure scenarios, severity,
        mitigations, and decision triggers.
    -   **Synthesizer** --- combines the agent results into the final
        decision report.
5.  **Persistence and presentation:** The backend saves decision records
    and returns the report and agent outputs. The frontend displays the
    report, agent runs, stress test, and decision history.

> The diagram describes the intended application flow. Exact agent call
> order and data flow are implemented in the backend workflow code;
> consult `backend/` for the current implementation.

## Technology Stack

  -----------------------------------------------------------------------
  Area                    Technology              Purpose
  ----------------------- ----------------------- -----------------------
  Frontend                React, TypeScript,      Decision form, Omi
                          Vite, Material UI       transcript review,
                                                  report, and history UI

  Backend                 Python, FastAPI,        REST API, webhook
                          Uvicorn                 receiver, workflow
                                                  coordination

  Persistent application  SQLite                  Store
  data                                            decision/application
                                                  records

  Semantic memory         Qdrant                  Vector storage and
                                                  similarity retrieval

  Embeddings              FastEmbed               Convert text into
                                                  vectors for semantic
                                                  search

  Agent orchestration     Lyzr / Lyzr ADK         Run specialized AI
                          integration             reasoning steps

  Voice input             Omi                     Capture conversations
                                                  and send transcript
                                                  webhooks

  Frontend hosting        Vercel                  Host the web app

  Backend hosting         Render                  Host the FastAPI
                                                  service
  -----------------------------------------------------------------------

## How to Use the App

### A. Run a manual decision

1.  Open the [TeamMind live demo](https://team-mind-eta.vercel.app).
2.  Create a decision with a concise title and a clear problem
    statement.
3.  Add the options you want to compare.
4.  Run the decision workflow.
5.  Review the recommendation, trade-offs, counterargument,
    uncertainties, next steps, and stress-test results.
6.  Open the agent outputs if you want to inspect the workflow's
    individual findings.

### B. Use an Omi conversation

1.  Open the Omi app and capture a conversation that describes a real
    decision, its options, constraints, and priorities.
2.  Configure the Omi webhook to point to the deployed backend endpoint:
    `https://teammind-2z8p.onrender.com/api/omi/webhook`
3.  After Omi sends the transcript, open TeamMind and review the
    available conversation segments.
4.  Select the relevant segments and use the app's
    decision-extraction/run flow.
5.  Review the resulting decision and report.

Omi payload formats can vary by webhook/event type. The backend endpoint
and the configured Omi webhook must match the current implementation. Do
not expose webhook secrets or API keys in screenshots or source control.

## Running Locally

### Prerequisites

-   Python 3.11 recommended
-   Node.js and npm
-   Git
-   Access credentials for the Lyzr and Qdrant services used by your
    configuration
-   Omi app and Developer Mode access if testing voice ingestion

### 1. Clone the repository

``` bash
git clone https://github.com/Sumit182004/TeamMind.git
cd TeamMind
```

### 2. Configure the backend

``` bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

**Windows PowerShell**

``` powershell
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux**

``` bash
source .venv/bin/activate
```

Install the backend requirements:

``` bash
pip install -r requirements.txt
```

Create a local `.env` file in the backend directory, using the variable
names expected by the current backend code. Typical deployment
configuration includes:

``` dotenv
LYZR_API_KEY=replace_with_your_key
QDRANT_URL=replace_with_your_qdrant_url
QDRANT_API_KEY=replace_with_your_qdrant_key
```

Never commit real credentials. If the backend code uses additional
variables (for example, an agent/workflow identifier), add them to your
local `.env` as required by that code. Keep `.env` excluded by
`.gitignore`.

Start the backend from the `backend` directory using the entry point
defined by the project. For the current FastAPI app, the usual command
is:

``` bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

If the project entry point or import path has changed, use the command
that matches the current `backend/main.py` configuration.

### 3. Configure the frontend

Open a second terminal:

``` bash
cd frontend
npm install
```

Create `frontend/.env.local`:

``` dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Start Vite:

``` bash
npm run dev
```

Open the local URL printed by Vite in your terminal.

### 4. Test the integration

-   Create and run a manual decision.
-   Check that the final report and agent outputs are displayed.
-   Send a test Omi conversation to the configured webhook.
-   Confirm that the transcript is received and relevant memory can be
    retrieved.
-   Check backend logs if the workflow fails.

> **Note:** Exact environment-variable names, endpoint paths, and
> startup commands must match the current source code. Use the actual
> names in `backend/main.py`, `backend/qdrant_memory.py`, and
> `frontend/` if they differ from these examples.

## Deployment

### Frontend --- Vercel

-   Project URL: https://team-mind-eta.vercel.app
-   Configure `VITE_API_URL` to point to the deployed backend URL.
-   Redeploy the frontend after changing React, TypeScript, CSS, or
    frontend environment variables.

### Backend --- Render

-   Service URL: https://teammind-2z8p.onrender.com
-   Configure the required Lyzr and Qdrant environment variables in the
    Render dashboard.
-   Backend changes require a new Render deployment if automatic
    deployment is not enabled.
-   Update the Omi webhook whenever the backend URL or webhook path
    changes.

Do not place API keys in frontend environment variables or commit them
to GitHub. Any variable prefixed with `VITE_` is exposed to the browser
bundle and must not contain secrets.

## Security and Privacy Notes

-   Keep API keys in backend environment variables.
-   Never commit `.env`, database files containing private user data, or
    credentials.
-   Restrict memory retrieval by the appropriate user/session identity
    where supported.
-   Avoid sending unnecessary personal or sensitive information to
    external AI services.
-   Provide a way to review and remove stored data before using the
    system with real users; verify deletion behavior in the current
    implementation before promising it.

## Troubleshooting

  -----------------------------------------------------------------------
  Problem                             What to check
  ----------------------------------- -----------------------------------
  Frontend cannot reach backend       Confirm `VITE_API_URL`, backend
                                      health, CORS configuration, and the
                                      browser console

  Omi transcript is not appearing     Confirm the webhook URL/path, Omi
                                      Developer Mode settings, payload
                                      format, and Render logs

  Qdrant embedding/vector error       Confirm FastEmbed is installed and
                                      that the collection vector
                                      dimension matches the embedding
                                      model

  Lyzr authentication or workflow     Verify backend environment
  failure                             variables and that the configured
                                      key has access to the required
                                      agent/workflow

  Report format looks different       Check the deployed frontend version
                                      and the actual output returned by
                                      the backend workflow

  Works locally but not in production Compare environment variables,
                                      deployed commit/version, CORS,
                                      database state, and service logs
  -----------------------------------------------------------------------

## Repository Structure

``` text
TeamMind/
├── backend/
│   ├── main.py                 # FastAPI API and webhook routes
│   ├── qdrant_memory.py        # Qdrant memory and embedding helpers
│   ├── decision_workflow.py    # Multi-agent decision workflow
│   ├── requirements.txt        # Python dependencies
│   └── ...                     # Other backend modules
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Main React application
│   │   └── ...                 # Components and styles
│   ├── package.json
│   └── ...
├── .gitignore
└── README.md
```

This is a representative structure; filenames can vary as the project
evolves. Check the repository for the current exact file list.

## Hackathon Integration Summary

  -----------------------------------------------------------------------
  Required technology                 How TeamMind uses it
  ----------------------------------- -----------------------------------
  **Omi**                             Voice conversation capture and
                                      transcript delivery to the backend
                                      webhook

  **Qdrant**                          Persistent vector memory and
                                      semantic retrieval of relevant
                                      context

  **Lyzr**                            Agent reasoning/orchestration for
                                      the multi-stage decision workflow
  -----------------------------------------------------------------------

The integrated concept is **voice → memory → multi-agent reasoning →
decision report**. The Omi webhook, Qdrant retrieval, and Lyzr workflow
should all be demonstrated in the final walkthrough.

## Demo Walkthrough

A concise demo can follow this order:

1.  Introduce a decision and its options.
2.  Show an Omi conversation arriving in TeamMind.
3.  Select the relevant transcript segments or show how context is used.
4.  Run the multi-agent workflow.
5.  Show the final recommendation, trade-offs, uncertainties, and
    stress-test scenarios.
6.  Open agent outputs to demonstrate that the result is produced
    through specialized steps.
7.  Briefly explain Omi, Qdrant, and Lyzr's roles in the architecture.

## Limitations

-   AI-generated recommendations depend on the quality of the decision
    statement, retrieved memories, and agent outputs.
-   Retrieved memory may be irrelevant or outdated; important
    constraints should be verified.
-   A completed workflow indicates that execution finished, not that
    every claim is necessarily correct.
-   Hosted free-tier services may have cold starts or resource limits.

## License

Add a license file before describing this repository as open source. If
no license is present, all rights remain with the copyright holder by
default.
