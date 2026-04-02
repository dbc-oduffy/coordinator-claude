# Research Output Evaluation Rubric

Adapted from Anthropic's multi-agent research system eval methodology.
Used by the /eval-output skill to score pipeline outputs.

## Criteria (each scored 0.0-1.0)

### 1. Factual Accuracy
Do claims in the output match the cited sources? Are there unsupported assertions?
- 1.0: All claims verified against cited sources, no unsupported assertions
- 0.7: Most claims verified, minor unsupported qualifications
- 0.4: Several claims lack source support or contradict sources
- 0.0: Pervasive unsupported or contradicted claims

### 2. Citation Accuracy
Do cited sources actually say what the output claims they say?
- 1.0: All citations accurately represent source content
- 0.7: Most citations accurate, minor misrepresentations
- 0.4: Several citations misrepresent sources
- 0.0: Citations are decorative, not substantive

### 3. Completeness
Are all aspects of the research question covered?
- 1.0: All requested aspects covered with depth
- 0.7: Most aspects covered, minor gaps acknowledged
- 0.4: Significant aspects missing without acknowledgment
- 0.0: Major portions of the question unanswered

### 4. Source Quality
Did the research use authoritative, primary sources over secondary/SEO content?
- 1.0: Primarily official docs, peer-reviewed, primary sources
- 0.7: Mix of primary and quality secondary sources
- 0.4: Heavy reliance on blogs, forums, or SEO content
- 0.0: Sources are unreliable, outdated, or AI-generated

### 5. Source Diversity
Did the research present multiple perspectives, including criticism?
- 1.0: Multiple viewpoints with adversarial/critical sources included
- 0.7: Some diversity, adversarial perspective present but thin
- 0.4: Single perspective dominates, criticism absent
- 0.0: Echo chamber — only confirming sources used

## Scoring
- **Pass:** Average >= 0.7 AND no single criterion below 0.4
- **Marginal:** Average 0.5-0.7 OR one criterion below 0.4
- **Fail:** Average < 0.5 OR two+ criteria below 0.4

## Usage
The /eval-output skill dispatches a Sonnet agent with this rubric plus
the research output. The agent reads the output, samples 3-5 citations
for verification (WebFetch), and scores each criterion with evidence.
