// Whole graph
MATCH (n)-[r]->(m) RETURN n, r, m;

// Conversation order
MATCH (m:Message)<-[:SENT]-(a:Agent) RETURN m.step, a.name, left(m.content, 80) ORDER BY m.step;

// Decisions and the messages they were based on
MATCH (a:Agent)-[:DECIDED]->(d:Decision)-[:BASED_ON]->(m:Message) RETURN a.name, d.text, m.step ORDER BY m.step;

// Causal chain of the last message
MATCH (m:Message)-[:REPLIED_TO*0..10]->(c:Message) WITH m, c ORDER BY m.step DESC LIMIT 20 RETURN c.step, c.agent, left(c.content, 60);

// Tool output seen by each agent
MATCH (x:Artifact)-[:INPUT_TO]->(t:ToolCall)-[:OBSERVED_BY]->(m:Message) RETURN m.agent, t.result;

// COMPLIANCE: every decision that relied on tool output, with the tool, its result and the run
MATCH (r:Run)<-[:IN_RUN]-(m:Message)<-[:OBSERVED_BY]-(t:ToolCall)
MATCH (a:Agent)-[:DECIDED]->(d:Decision)-[:BASED_ON]->(m)
RETURN r.id AS run, m.step AS step, a.name AS agent, d.text AS decision, t.tool AS tool, left(t.result, 80) AS tool_result
ORDER BY run, step;

// COMPLIANCE: decisions that relied on a FAILED tool call (error, traceback, timeout or no output)
MATCH (r:Run)<-[:IN_RUN]-(m:Message)<-[:OBSERVED_BY]-(t:ToolCall)
WHERE t.result CONTAINS 'Traceback' OR t.result CONTAINS 'Error' OR t.result STARTS WITH '(timed out' OR t.result = '(no output)'
MATCH (a:Agent)-[:DECIDED]->(d:Decision)-[:BASED_ON]->(m)
RETURN r.id AS run, m.step AS step, a.name AS agent, d.text AS decision, left(t.result, 80) AS failure
ORDER BY run, step;

// COMPLIANCE: full provenance of one decision (set the id): artifact -> tool call -> message -> decision
MATCH (x:Artifact)-[:INPUT_TO]->(t:ToolCall)-[:OBSERVED_BY]->(m:Message)<-[:BASED_ON]-(d:Decision {id: $decision_id})
RETURN x, t, m, d;
