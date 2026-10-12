
import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
  Checkbox,
} from "@mui/material";
import {
  createDecision,
  getDecisions,
  getDecisionReport,
  runDecision,
  saveDecisionSourceTranscript,
  analyzeOmiSession,
  extractOmiTranscript,
  getOmiSessions,
  getOmiSegments,
  type Decision,
  type OmiSession,
  type OmiSegment,
} from "./services/api";
import "./App.css";

const agentNames = [
  "Researcher",
  "Analyst",
  "Dissent Engine",
  "Verifier",
  "Stress Tester",
  "Synthesizer",
];

function parseAgentOutput(value: unknown): any {
  if (typeof value !== "string") return value;

  const cleaned = value
    .trim()
    .replace(/^```(?:json|markdown|md)?\s*/i, "")
    .replace(/\s*```$/, "");

  try {
    return JSON.parse(cleaned);
  } catch {
    // Some model responses are Markdown rather than the requested JSON.
    // Convert known report headings into the same shape the report UI expects,
    // so the full Markdown document is never shown as the recommendation.
    const extractSection = (patterns: RegExp[]) => {
      for (const pattern of patterns) {
        const match = cleaned.match(pattern);
        if (match?.[1]) {
          return match[1]
            .trim()
            .replace(/^```(?:json)?\s*/i, "")
            .replace(/\s*```$/, "")
            .trim();
        }
      }
      return "";
    };

    const recommendation = extractSection([
      /(?:^|\n)\s*#{1,4}\s*Recommendation\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
    ]);
    const keyFacts = extractSection([
      /(?:^|\n)\s*#{1,4}\s*Key Facts from Memory\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
    ]);
    const tradeoffs = extractSection([
      /(?:^|\n)\s*#{1,4}\s*Options Comparison\s*\n+([\s\S]*?)(?=\n\s*#{1,2}\s+|$)/i,
      /(?:^|\n)\s*#{1,4}\s*Key trade-offs\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
    ]);
    const counterarguments = extractSection([
      /(?:^|\n)\s*#{1,4}\s*Counterarguments?\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
      /(?:^|\n)\s*#{1,4}\s*Strongest counterargument\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
    ]);
    const uncertainties = extractSection([
      /(?:^|\n)\s*#{1,4}\s*(?:Evidence Gaps and Uncertainty|Uncertainties)\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
    ]);
    const nextSteps = extractSection([
      /(?:^|\n)\s*#{1,4}\s*Practical Next Steps\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
      /(?:^|\n)\s*#{1,4}\s*Next steps\s*\n+([\s\S]*?)(?=\n\s*#{1,4}\s+|$)/i,
    ]);

    if (recommendation) {
      return {
        recommendation,
        reasoning: keyFacts || "",
        tradeoffs,
        counterarguments,
        uncertainties,
        next_steps: nextSteps,
        raw_markdown: cleaned,
      };
    }

    // Preserve ordinary non-report agent text as-is.
    return value;
  }
}

function humanizeKey(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}


function formatOutput(value: unknown): string {
  if (value == null) {
    return "No details provided.";
  }

  if (typeof value === "string") {
    return value
      // Display Markdown content cleanly even when an agent returns plain text.
      .replace(/^\s*#{1,6}\s+/gm, "")
      .replace(/^\s*[-*+]\s+/gm, "• ")
      .replace(/^\s*\d+[.)]\s+/gm, (match) => match.trim() + " ")
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/__(.*?)__/g, "$1")
      .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .trim();
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value
      .map((item, index) => `${index + 1}. ${formatOutput(item)}`)
      .join("\n\n");
  }

  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        return `${humanizeKey(key)}:\n${formatOutput(item)}`;
      })
      .join("\n\n");
  }

  return String(value);
}


function App() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [problem, setProblem] = useState("");
  const [options, setOptions] = useState("");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [omiTitle, setOmiTitle] = useState("");
  const [omiProblem, setOmiProblem] = useState("");
  const [omiOptions, setOmiOptions] = useState<string[]>([]);
  const [omiExtracted, setOmiExtracted] = useState(false);
  const [omiTranscript, setOmiTranscript] = useState("");
  const [originalOmiTranscript, setOriginalOmiTranscript] = useState("");
  const [sessionAnalysisLoading, setSessionAnalysisLoading] = useState(false);
  const [omiSessions, setOmiSessions] = useState<OmiSession[]>([]);
  const [omiSessionsLoading, setOmiSessionsLoading] = useState(true);
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [omiSegments, setOmiSegments] = useState<Record<string, OmiSegment[]>>({});
  const [selectedSegmentIds, setSelectedSegmentIds] = useState<Record<string, string[]>>({});
  const [segmentsLoading, setSegmentsLoading] = useState(false);

  async function refreshDecisions() {
    const data = await getDecisions();
    setDecisions(data);

    if (selected !== null && !data.some((d) => d.id === selected)) {
      setSelected(null);
    }
  }

  
  useEffect(() => {
    let active = true;

    const loadOmiSessions = async () => {
      try {
        const sessions = await getOmiSessions();

        if (active) {
          setOmiSessions(sessions);
        }
      } catch (error) {
        console.error("Failed to load Omi sessions:", error);
      } finally {
        if (active) {
          setOmiSessionsLoading(false);
        }
      }
    };

    void loadOmiSessions();
    void refreshDecisions().catch((error) => {
      console.error("Failed to load saved decisions:", error);
    });
    const intervalId = window.setInterval(() => {
      void loadOmiSessions();
    }, 3000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  async function handleCreate() {
    setError("");
    setMessage("");

    const optionList = options
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);

    if (!title.trim() || !problem.trim() || optionList.length < 2) {
      setError("Enter a title, problem, and at least two options.");
      return;
    }

    setLoading(true);
    try {
      const created = await createDecision({
        title: title.trim(),
        problem: problem.trim(),
        options: optionList,
      });

      setTitle("");
      setProblem("");
      setOptions("");
      setSelected(created.id);
      setReport(null);
      setMessage("Decision saved successfully.");
      await refreshDecisions();
    } catch (e: any) {
      setError(e.response?.data?.detail || "Could not create decision.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRun(id: number) {
    setError("");
    setMessage("");
    setRunning(true);
    setSelected(id);
    setReport(null);

    try {
      await runDecision(id);
      const result = await getDecisionReport(id);
      setReport(result);
      setMessage("All six agent roles finished.");
      await refreshDecisions();
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
          "Workflow failed. Check the backend terminal.",
      );
      await refreshDecisions().catch(() => {});
    } finally {
      setRunning(false);
    }
  }


  async function handleLoadSegments(sessionId: string) {
    setError("");

    if (expandedSessionId === sessionId) {
      setExpandedSessionId(null);
      return;
    }

    setExpandedSessionId(sessionId);

    if (omiSegments[sessionId]) {
      return;
    }

    setSegmentsLoading(true);

    try {
      const segments = await getOmiSegments(sessionId);

      setOmiSegments((previous) => ({
        ...previous,
        [sessionId]: segments,
      }));

      setSelectedSegmentIds((previous) => ({
        ...previous,
        [sessionId]: segments.map((segment) => segment.id),
      }));
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
          "Could not load transcript segments. Check the backend."
      );
    } finally {
      setSegmentsLoading(false);
    }
  }

  function handleToggleSegment(sessionId: string, segmentId: string) {
    setSelectedSegmentIds((previous) => {
      const current = previous[sessionId] ?? [];
      const updated = current.includes(segmentId)
        ? current.filter((id) => id !== segmentId)
        : [...current, segmentId];

      return {
        ...previous,
        [sessionId]: updated,
      };
    });
  }

  function handleSelectAllSegments(sessionId: string) {
    const segments = omiSegments[sessionId] ?? [];

    setSelectedSegmentIds((previous) => ({
      ...previous,
      [sessionId]: segments.map((segment) => segment.id),
    }));
  }

  function handleClearSegments(sessionId: string) {
    setSelectedSegmentIds((previous) => ({
      ...previous,
      [sessionId]: [],
    }));
  }

  async function handleAnalyzeOmiSession(sessionId: string) {
    setError("");
    setMessage("");

    const segmentIds = selectedSegmentIds[sessionId] ?? [];

    if (segmentIds.length === 0) {
      setError("Select at least one transcript segment to analyze.");
      return;
    }

    setSessionAnalysisLoading(true);

    try {
      const result = await analyzeOmiSession(sessionId, segmentIds);

      setSelected(result.decision_id);
      setReport(null);

      setMessage(
        `Selected transcript segments analyzed. Decision #${result.decision_id} created.`
      );

      await refreshDecisions();

      const reportResult = await getDecisionReport(result.decision_id);
      setReport(reportResult);
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
          e.message ||
          "Could not analyze the selected Omi segments."
      );
    } finally {
      setSessionAnalysisLoading(false);
    }
  }
    
  async function handleSaveOmiDecision() {
    setError("");
    setMessage("");

    const cleanedTitle = omiTitle.trim();
    const cleanedProblem = omiProblem.trim();
    const cleanedOptions = omiOptions
      .map((option) => option.trim())
      .filter(Boolean);

    if (
      !cleanedTitle ||
      !cleanedProblem ||
      cleanedOptions.length < 2 ||
      omiOptions.some((option) => !option.trim())
    ) {
      setError(
        "Enter a title, problem, and at least two non-empty options."
      );
      return;
    }

    setLoading(true);

    try {
      const created = await createDecision({
        title: cleanedTitle,
        problem: cleanedProblem,
        options: cleanedOptions,
      });
      if (originalOmiTranscript.trim()) {
        try {
          await saveDecisionSourceTranscript(
            created.id,
            originalOmiTranscript.trim(),
          );
        } catch {
          setSelected(created.id);
          setReport(null);
          setError(
            `Decision #${created.id} was saved, but its original transcript could not be saved to Qdrant. The decision was not lost.`
          );
          await refreshDecisions();
          return;
        }
      }

      setSelected(created.id);
      setReport(null);
      setOmiTranscript("");
      setOmiTitle("");
      setOmiProblem("");
      setOmiOptions([]);
      setOmiExtracted(false);

      setMessage(
        `Reviewed decision #${created.id} saved successfully.`
      );

      await refreshDecisions();
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
          "Could not save the reviewed decision."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleViewReport(id: number) {
    setError("");
    setMessage("");
    setSelected(id);
    setReport(null);

    try {
      const result = await getDecisionReport(id);
      setReport(result);
    } catch (e: any) {
      setError(e.response?.data?.detail || "Could not load report.");
    }
  }

  const activeDecision = decisions.find((d) => d.id === selected);

  return (
    <Box className="app-shell">
      <Box className="topbar">
        <Container maxWidth="xl" className="topbar-inner">
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Box className="brand-mark">T</Box>
            <Box>
              <Typography className="brand-name">TeamMind</Typography>
              <Typography className="brand-subtitle">
                Decision Intelligence Workspace
              </Typography>
            </Box>
          </Stack>
          <Chip label="MULTI-AGENT SYSTEM" className="header-chip" />
        </Container>
      </Box>

      <Container maxWidth="xl" className="main-content">
        <Box className="hero">
          <Typography className="eyebrow">
            THINK TOGETHER · CHALLENGE ASSUMPTIONS
          </Typography>
          <Typography className="hero-title">
            Better decisions start
            <br />
            with <span>better questions.</span>
          </Typography>
          <Typography className="hero-description">
            Bring a difficult decision. Let specialized AI agents analyze,
            challenge, and verify the options before you decide.
          </Typography>
        </Box>

        {error && (
          <Alert severity="error" onClose={() => setError("")} sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {message && (
          <Alert
            severity="success"
            onClose={() => setMessage("")}
            sx={{ mb: 2 }}
          >
            {message}
          </Alert>
        )}

        <Box className="dashboard-grid">
          <Stack spacing={3}>
            <Paper className="panel" elevation={0}>
              <Typography className="section-label">
                START A DECISION
              </Typography>
              <Typography className="panel-title">
                What are you deciding?
              </Typography>

              <Stack spacing={2.2} mt={2.5}>
                <TextField
                  label="Decision title"
                  placeholder="e.g. Authentication strategy"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  fullWidth
                  size="small"
                />
                <TextField
                  label="Describe the problem"
                  placeholder="Explain your goal, constraints, and priorities..."
                  value={problem}
                  onChange={(e) => setProblem(e.target.value)}
                  fullWidth
                  multiline
                  minRows={4}
                />
                <TextField
                  label="Options (one per line)"
                  placeholder={"Build it ourselves\nUse an existing service"}
                  value={options}
                  onChange={(e) => setOptions(e.target.value)}
                  fullWidth
                  multiline
                  minRows={3}
                />
                <Button
                  variant="contained"
                  onClick={handleCreate}
                  disabled={loading}
                  className="primary-button"
                  fullWidth
                >
                  {loading ? (
                    <CircularProgress size={22} color="inherit" />
                  ) : (
                    "Create decision"
                  )}
                </Button>
              </Stack>
            </Paper>
            
            <Paper className="panel" elevation={0}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                spacing={2}
              >
                <Box>
                  <Typography className="section-label">
                    OMI LIVE CAPTURE
                  </Typography>
                  <Typography className="panel-title">
                    Recent conversations
                  </Typography>
                </Box>

                <Chip
                  label="Auto-refresh · 3 sec"
                  size="small"
                  color="success"
                  variant="outlined"
                />
              </Stack>

              <Typography className="muted" sx={{ mt: 1, mb: 2 }}>
                Conversations captured by Omi appear here automatically.
              </Typography>

              {omiSessionsLoading ? (
                <Stack direction="row" spacing={1} alignItems="center">
                  <CircularProgress size={18} />
                  <Typography className="muted">
                    Loading Omi conversations...
                  </Typography>
                </Stack>
              ) : omiSessions.length === 0 ? (
                <Typography className="muted">
                  Waiting for an Omi conversation. Start speaking with Omi
                  and your transcript will appear here.
                </Typography>
              ) : (
                <Stack spacing={2}>
                  {omiSessions.map((session) => (
                    <Paper
                      key={session.session_id}
                      variant="outlined"
                      sx={{ p: 2, borderRadius: 2, bgcolor: "#0b1220", color: "#ffffff", borderColor: "#34415a" }}
                    >
                      <Stack
                        direction="row"
                        justifyContent="space-between"
                        alignItems="center"
                        spacing={2}
                      >
                        <Typography fontWeight={600} sx={{ color: "#ffffff" }}>
                          Omi conversation
                        </Typography>

                        <Chip
                          label={`${session.segment_count} segments`}
                          size="small"
                        />
                      </Stack>

                      <Typography
                        className="muted"
                        variant="caption"
                        sx={{ display: "block", mt: 0.5, mb: 1 }}
                      >
                        Last received:{" "}
                        {new Date(session.last_seen).toLocaleTimeString()}
                      </Typography>

                      <Typography
                        variant="body2"
                        sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}
                      >
                        {session.transcript || "Waiting for transcript..."}
                      </Typography>

                      <Stack direction="row" spacing={1} mt={2} flexWrap="wrap">
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => void handleLoadSegments(session.session_id)}
                        >
                          {expandedSessionId === session.session_id
                            ? "Hide segments"
                            : "Select transcript segments"}
                        </Button>
                      </Stack>

                      {expandedSessionId === session.session_id && (
                        <Box mt={2}>
                          {segmentsLoading ? (
                            <CircularProgress size={22} />
                          ) : (
                            <>
                              <Stack
                                direction="row"
                                spacing={1}
                                alignItems="center"
                                flexWrap="wrap"
                                mb={2}
                              >
                                <Typography variant="body2" className="muted">
                                  Selected:{" "}
                                  {(selectedSegmentIds[session.session_id] ?? []).length}
                                  {" / "}
                                  {(omiSegments[session.session_id] ?? []).length}
                                </Typography>

                                <Button
                                  size="small"
                                  onClick={() => handleSelectAllSegments(session.session_id)}
                                >
                                  Select all
                                </Button>

                                <Button
                                  size="small"
                                  onClick={() => handleClearSegments(session.session_id)}
                                >
                                  Clear selection
                                </Button>
                              </Stack>

                              <Stack spacing={1}>
                                {(omiSegments[session.session_id] ?? []).map((segment) => (
                                  <Paper
                                    key={segment.id}
                                    variant="outlined"
                                    sx={{ p: 1.5, borderRadius: 2, bgcolor: "#0b1220", color: "#ffffff", borderColor: "#34415a" }}
                                  >
                                    <Stack direction="row" alignItems="flex-start" spacing={1}>
                                      <Checkbox
                                        size="small"
                                        checked={(
                                          selectedSegmentIds[session.session_id] ?? []
                                        ).includes(segment.id)}
                                        onChange={() =>
                                          handleToggleSegment(session.session_id, segment.id)
                                        }
                                      />

                                      <Box flex={1} minWidth={0}>
                                        <Typography variant="caption" className="muted">
                                          {segment.speaker || "Speaker"}
                                          {segment.created_at
                                            ? ` · ${new Date(
                                                segment.created_at
                                              ).toLocaleString()}`
                                            : ""}
                                        </Typography>

                                        <Typography
                                          variant="body2"
                                          sx={{
                                            whiteSpace: "pre-wrap",
                                            overflowWrap: "anywhere",
                                          }}
                                        >
                                          {segment.transcript}
                                        </Typography>
                                      </Box>
                                    </Stack>
                                  </Paper>
                                ))}
                              </Stack>

        <Button
          variant="contained"
          className="primary-button"
          fullWidth
          sx={{ mt: 2 }}
          disabled={
            sessionAnalysisLoading ||
            (selectedSegmentIds[session.session_id] ?? []).length === 0
          }
          onClick={() =>
            void handleAnalyzeOmiSession(session.session_id)
          }
        >
          {sessionAnalysisLoading ? (
            <CircularProgress size={20} color="inherit" />
          ) : (
            "Analyze selected segments with TeamMind"
          )}
        </Button>
      </>
    )}
  </Box>
)}
                    </Paper>
                  ))}
                </Stack>
              )}
            </Paper>

            <Paper className="panel" elevation={0}>
              <Typography className="section-label">
                VOICE-TO-MEMORY
              </Typography>

              <Typography className="panel-title">
                Import an Omi conversation
              </Typography>
              <Divider sx={{ my: 2 }} />

            
              <Typography className="muted" sx={{ mt: 1, mb: 2 }}>
                Paste a conversation transcript to extract a decision
                and save its context to TeamMind memory.
              </Typography>

                <Stack spacing={2}>
                <TextField
                  label="Conversation transcript"
                  placeholder="Paste your Omi conversation transcript here..."
                  value={omiTranscript}
                  onChange={(e) => {
                    setOmiTranscript(e.target.value);
                    setOriginalOmiTranscript(e.target.value);
                    setOmiExtracted(false);
                  }}
                  multiline
                  minRows={5}
                  fullWidth
                />

                <Button
                  variant="outlined"
                  fullWidth
                  disabled={loading || !omiTranscript.trim()}
                  onClick={async () => {
                    setError("");
                    setMessage("");
                    setLoading(true);

                    try {
                      const result = await extractOmiTranscript(omiTranscript.trim());

                      setOmiTitle(result.title);
                      setOmiProblem(result.problem);
                      setOmiOptions(result.options);
                      setOmiExtracted(true);
                      setMessage("Transcript analyzed. Review the extracted decision below.");
                    } catch (e: any) {
                      setError(
                        e.response?.data?.detail ||
                          "Could not extract a decision from the transcript."
                      );
                    } finally {
                      setLoading(false);
                    }
                  }}
                >
                  {loading ? (
                    <CircularProgress size={20} />
                  ) : (
                    "Extract decision from transcript"
                  )}
                </Button>
              </Stack>

              {/* INSERT THE REVIEW FORM HERE */}
              {omiExtracted && (
                <Stack spacing={2} sx={{ mt: 3 }}>
                  <Divider />

                  <Typography className="section-label">
                    REVIEW EXTRACTED DECISION
                  </Typography>

                  <TextField
                    label="Decision title"
                    value={omiTitle}
                    onChange={(e) => setOmiTitle(e.target.value)}
                    fullWidth
                    required
                  />

                  <TextField
                    label="Problem description"
                    value={omiProblem}
                    onChange={(e) => setOmiProblem(e.target.value)}
                    multiline
                    minRows={3}
                    fullWidth
                    required
                  />

                  <Typography className="muted">
                    Possible options — edit each option below.
                  </Typography>

                  {omiOptions.map((option, index) => (
                    <TextField
                      key={index}
                      label={`Option ${index + 1}`}
                      value={option}
                      onChange={(e) => {
                        const updatedOptions = [...omiOptions];
                        updatedOptions[index] = e.target.value;
                        setOmiOptions(updatedOptions);
                      }}
                      fullWidth
                      required
                    />
                  ))}

                  <Button
                    variant="outlined"
                    fullWidth
                    onClick={() =>
                      setOmiOptions([...omiOptions, ""])
                    }
                  >
                    Add another option
                  </Button>

                  <Button
                    variant="outlined"
                    color="error"
                    fullWidth
                    disabled={omiOptions.length <= 2}
                    onClick={() =>
                      setOmiOptions(omiOptions.slice(0, -1))
                    }
                  >
                    Remove last option
                  </Button>

                  <Button
                    variant="contained"
                    className="primary-button"
                    fullWidth
                    disabled={
                      loading ||
                      !omiTitle.trim() ||
                      !omiProblem.trim() ||
                      omiOptions.length < 2 ||
                      omiOptions.some((option) => !option.trim())
                    }
                    onClick={handleSaveOmiDecision}
                  >
                    Save reviewed decision
                  </Button>
                </Stack>
              )}

            </Paper>


            <Paper className="panel" elevation={0}>
              <Stack direction="row" justifyContent="space-between" mb={2}>
                <Typography className="panel-title">
                  Decision history
                </Typography>
                <Chip label={`${decisions.length} saved`} size="small" />
              </Stack>

              {decisions.length === 0 ? (
                <Typography className="muted">
                  Your saved decisions will appear here.
                </Typography>
              ) : (
                <Stack spacing={1.2}>
                  {decisions.map((decision) => (
                    <Box
                      key={decision.id}
                      className={`decision-item ${
                        selected === decision.id ? "selected" : ""
                      }`}
                      onClick={() => handleViewReport(decision.id)}
                    >
                      <Stack
                        direction="row"
                        justifyContent="space-between"
                        alignItems="flex-start"
                        spacing={1}
                      >
                        <Box minWidth={0}>
                          <Typography className="decision-title">
                            {decision.title}
                          </Typography>
                          <Typography className="muted" variant="caption">
                            Decision #{decision.id}
                          </Typography>
                        </Box>
                        <Chip
                          label={decision.status}
                          size="small"
                          color={
                            decision.status === "completed"
                              ? "success"
                              : decision.status === "failed"
                                ? "error"
                                : "default"
                          }
                        />
                      </Stack>

                      <Typography className="decision-problem">
                        {decision.problem}
                      </Typography>

                      <Button
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRun(decision.id);
                        }}
                        disabled={running}
                      >
                        Run agents
                      </Button>
                      <Button
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleViewReport(decision.id);
                        }}
                      >
                        View report
                      </Button>
                    </Box>
                  ))}
                </Stack>
              )}
            </Paper>
          </Stack>

          <Stack spacing={3}>
            <Paper className="panel" elevation={0}>
              <Typography className="section-label">
                COLLABORATIVE WORKFLOW
              </Typography>
              <Typography className="panel-title">
                The decision room
              </Typography>
              <Typography className="muted" mt={0.8} mb={3}>
                Six specialized roles examine the decision, challenge
                assumptions, and test possible failure scenarios.
              </Typography>

              <Stack spacing={1.2}>
                {agentNames.map((name, index) => (
                  <Box className="agent-row" key={name}>
                    <Box className="agent-number">{`0${index + 1}`}</Box>
                    <Box flex={1}>
                      <Typography className="agent-name">{name}</Typography>
                      <Typography className="muted" variant="caption">
                        {
                          [
                            "Identify options and evidence",
                            "Compare trade-offs",
                            "Challenge the leading option",
                            "Flag unsupported claims",
                            "Test decisions against failure scenarios",
                            "Produce the final decision report",
                          ][index]
                        }
                      </Typography>
                    </Box>
                    <Chip
                      label={
                        running && selected === activeDecision?.id
                          ? "Processing"
                          : report &&
                              report.decision?.id === activeDecision?.id &&
                              report.decision?.status === "completed"
                            ? "Completed"
                            : report &&
                                report.decision?.id === activeDecision?.id &&
                                report.decision?.status === "failed"
                              ? "Failed"
                              : "Ready"
                      }
                      size="small"
                      className="agent-status"
                    />
                  </Box>
                ))}
              </Stack>

              {activeDecision && (
                <>
                  <Divider sx={{ my: 2.5, borderColor: "#263247" }} />
                  <Typography className="section-label">
                    SELECTED DECISION
                  </Typography>
                  <Typography className="panel-title" mt={1}>
                    {activeDecision.title}
                  </Typography>
                  <Typography className="muted" mt={1}>
                    {activeDecision.problem}
                  </Typography>
                  <Button
                    variant="contained"
                    fullWidth
                    className="primary-button"
                    sx={{ mt: 2.5 }}
                    disabled={running}
                    onClick={() => handleRun(activeDecision.id)}
                  >
                    {running ? (
                      <>
                        <CircularProgress
                          size={18}
                          color="inherit"
                          sx={{ mr: 1 }}
                        />
                        Running workflow...
                      </>
                    ) : (
                      "Run decision workflow"
                    )}
                  </Button>
                </>
              )}
            </Paper>

            <Paper className="panel report-panel" elevation={0}>
              <Typography className="section-label">
                DECISION INTELLIGENCE
              </Typography>
              <Typography className="panel-title">
                Final report
              </Typography>

              {!report ? (
                <Typography className="muted" mt={2}>
                  Create or select a decision, then run the workflow to see
                  the agent findings and recommendation here.
                </Typography>
              ) : (
                <Stack spacing={2} mt={2}>
                  <Alert severity="success" sx={{ bgcolor: "#123327", color: "#b9f6d0", "& .MuiAlert-icon": { color: "#6ee7a0" } }}>
                    Workflow status: {report.decision.status}
                  </Alert>

                  
                {(() => {
                  const parsedReport = parseAgentOutput(
                    report.decision.recommendation
                  );

                  const recommendation =
                    parsedReport &&
                    typeof parsedReport === "object" &&
                    !Array.isArray(parsedReport)
                      ? parsedReport
                      : null;

                  return (
                    <Paper className="recommendation-card" elevation={0} sx={{ bgcolor: "#0b1220", color: "#edf2ff", border: "1px solid #34415a", borderRadius: 2, p: 2.5 }}>
                      <Typography className="section-label">
                        RECOMMENDATION
                      </Typography>

                      <Typography
                        className="output-text"
                        sx={{
                          whiteSpace: "pre-wrap",
                          overflowWrap: "anywhere",
                          fontWeight: 400,
                          fontSize: "13px",
                          lineHeight: 1.8,
                          color: "#cbd5e1",
                        }}
                      >
                        {formatOutput(
                          recommendation?.recommendation ??
                            (typeof parsedReport === "string"
                              ? parsedReport
                              : "No recommendation available.")
                        )
                          .replace(/\*\*/g, "")
                          .replace(/^#{1,6}\s+/gm, "")}
                      </Typography>

                      {recommendation?.reasoning && (
                        <Typography className="recommendation-reasoning">
                          {formatOutput(recommendation.reasoning)}
                        </Typography>
                      )}

                      {recommendation?.tradeoffs != null &&
                        recommendation.tradeoffs !== "" && (
                          <Box className="report-section">
                            <Typography className="report-heading">
                              Key trade-offs
                            </Typography>

                            {typeof recommendation.tradeoffs === "string" ||
                            typeof recommendation.tradeoffs === "number" ? (
                              <Typography className="output-text">
                                {formatOutput(recommendation.tradeoffs)}
                              </Typography>
                            ) : Array.isArray(recommendation.tradeoffs) ? (
                              recommendation.tradeoffs.map(
                                (item: unknown, index: number) => (
                                  <Box className="tradeoff-item" key={index}>
                                    <Typography className="tradeoff-title">
                                      Trade-off {index + 1}
                                    </Typography>
                                    <Typography className="output-text">
                                      {formatOutput(item)}
                                    </Typography>
                                  </Box>
                                )
                              )
                            ) : typeof recommendation.tradeoffs === "object" ? (
                              Object.entries(
                                recommendation.tradeoffs as Record<string, unknown>
                              ).map(([key, value]) => (
                                <Box className="tradeoff-item" key={key}>
                                  <Typography className="tradeoff-title">
                                    {humanizeKey(key)}
                                  </Typography>
                                  <Typography className="output-text">
                                    {formatOutput(value)}
                                  </Typography>
                                </Box>
                              ))
                            ) : (
                              <Typography className="output-text">
                                {formatOutput(recommendation.tradeoffs)}
                              </Typography>
                            )}
                          </Box>
                        )}

                      {recommendation?.counterarguments && (
                        <Box className="report-section">
                          <Typography className="report-heading">
                            Strongest counterargument
                          </Typography>
                          <Typography className="output-text">
                            {formatOutput(recommendation.counterarguments)}
                          </Typography>
                        </Box>
                      )}

                      {recommendation?.uncertainties && (
                        <Box className="report-section">
                          <Typography className="report-heading">
                            Uncertainties
                          </Typography>
                          <Typography className="output-text">
                            {formatOutput(recommendation.uncertainties)}
                          </Typography>
                        </Box>
                      )}

                      {recommendation?.next_steps && (
                        <Box className="report-section">
                          <Typography className="report-heading">
                            Next steps
                          </Typography>
                          <Typography className="output-text">
                            {formatOutput(recommendation.next_steps)}
                          </Typography>
                        </Box>
                      )}
                    </Paper>
                  );
                })()}

                {(() => {

                  const stressRun = [...(report.agent_runs ?? [])].reverse().find((run: any) =>
                    String(run.agent_name).toLowerCase().includes("stress")
                  );

                  const stressData = parseAgentOutput(stressRun?.output);

                  const stressObject =
                    stressData &&
                    typeof stressData === "object" &&
                    !Array.isArray(stressData)
                      ? stressData
                      : null;

                  return (
                    <Box className="stress-test-panel">
                      <Typography className="section-label">
                        DECISION STRESS TEST
                      </Typography>

                      <Typography className="panel-title">
                        How could this decision fail?
                      </Typography>

                      <Typography className="muted" sx={{ mb: 2 }}>
                        Review adverse scenarios, vulnerabilities, and conditions
                        that could change the recommendation.
                      </Typography>

                      {stressRun ? (
                        <Box className="stress-test-content">
                          {stressObject ? (
                            Object.entries(stressObject).map(([key, value]) => (
                              <Box className="stress-result-card" key={key}>
                                <Typography className="stress-result-title">
                                  {humanizeKey(key)}
                                </Typography>
                                <Typography className="output-text">
                                  {formatOutput(value)}
                                </Typography>
                              </Box>
                            ))
                          ) : (
                            <Typography className="output-text">
                              {formatOutput(stressData)}
                            </Typography>
                          )}
                        </Box>
                      ) : (
                        <Typography className="muted">
                          No stress-test output is available for this decision yet.
                          Run the workflow to generate it.
                        </Typography>
                      )}
                    </Box>
                  );
                })()}
                  <Typography className="section-label">
                    AGENT OUTPUTS
                  </Typography>
                  {(() => {
                    // A decision can have several workflow attempts. Show only the
                    // newest output for each agent instead of repeating old runs.
                    const latestByAgent = new Map<string, any>();
                    [...(report.agent_runs ?? [])].reverse().forEach((run: any) => {
                      const key = String(run.agent_name ?? "").trim().toLowerCase();
                      if (key && !latestByAgent.has(key)) latestByAgent.set(key, run);
                    });
                    const uniqueRuns = Array.from(latestByAgent.values()).reverse();
                    return uniqueRuns.map((run: any) => {
                    const isStressTest = String(run.agent_name)
                      .toLowerCase()
                      .includes("stress");

                    return (
                      <Box
                        component="details"
                        className={`agent-output ${isStressTest ? "stress-output" : ""}`}
                        key={run.id}
                      >
                        <Box component="summary" className="agent-output-summary">
                          <Box>
                            <Typography className="agent-name">
                              {run.agent_name}
                            </Typography>
                            <Typography variant="caption" className="muted">
                              {isStressTest
                                ? "Scenario analysis and failure conditions"
                                : "View detailed agent findings"}
                            </Typography>
                          </Box>

                          <Chip
                            label={isStressTest ? "Stress test" : "View output"}
                            size="small"
                          />
                        </Box>

                        <Box className="agent-output-content">
                          <Typography className="output-text">
                            {formatOutput(parseAgentOutput(run.output))}
                          </Typography>
                        </Box>
                      </Box>
                    );
                  });
                  })()}
                </Stack>
              )}
            </Paper>
          </Stack>
        </Box>

        <Typography className="footer">
          TeamMind · Collaborative Multi-Agent Decision Intelligence
        </Typography>
      </Container>
    </Box>
  );
}

export default App;
