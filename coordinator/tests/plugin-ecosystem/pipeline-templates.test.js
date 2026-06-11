// SCOPE: These tests validate structural integrity only.
//
// What IS covered:
//   - File existence: all expected pipeline template files are present
//   - Field population: [BRACKETED_FIELDS] in UPPER_SNAKE_CASE are extractable
//   - Conditional block matching: every [IF X:] has a corresponding [END IF X]
//   - Section ordering: specialist template sections appear in the correct sequence
//   - Cross-template consistency: artifacts referenced in one template are referenced
//     in the others that consume them (e.g. atlas-sketch outputs, survey.md)
//   - repo-driver.md structural properties: step numbering, template references, mode implication docs
//
// What is NOT covered:
//   - Behavioral correctness: a template can pass every test here and still instruct
//     agents incorrectly — wrong sequencing logic, missing context handoffs, bad prompts
//   - Agent output quality: nothing here validates what agents actually produce
//   - Runtime behavior: whether the pipeline executes as intended end-to-end
//
// IMPORTANT: Green CI from these tests is NOT behavioral validation.
// The Research Pipeline Benchmark (experiment-research-pipeline-benchmark-spec.md)
// is the mechanism for behavioral validation, especially for Pipeline B. Do not
// interpret passing tests as evidence that Pipeline B is working correctly.

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { PLUGINS_ROOT, fileExists } = require('./helpers/fs');

const DEEP_RESEARCH_DIR = path.join(PLUGINS_ROOT, 'coordinator-claude', 'deep-research');
const PIPELINES_DIR = path.join(DEEP_RESEARCH_DIR, 'pipelines');
// Pipeline B driver moved from commands/repo.md into pipelines/repo-driver.md in commit
// 13f723e9 (2026-05-06, skill-budget Phase C: collapse /web /repo /structured into
// /research --mode flag). Step numbering, mode implications, template refs, and the
// phased lifecycle all live in repo-driver.md now.
const REPO_DRIVER_PATH = path.join(PIPELINES_DIR, 'repo-driver.md');

// Helper: read file content
function readFile(filePath) {
  return fs.readFileSync(filePath, 'utf-8');
}

// Helper: extract all [BRACKETED_FIELDS] from content (excluding markdown links, code fences, etc.)
function extractTemplateFields(content) {
  const fields = new Set();
  // Match [WORD_WORD] patterns — template fields are UPPER_SNAKE_CASE
  const re = /\[([A-Z][A-Z0-9_]+)\]/g;
  let match;
  while ((match = re.exec(content)) !== null) {
    fields.add(match[1]);
  }
  return fields;
}

// Helper: extract all conditional blocks [IF X:] ... [END IF X]
function extractConditionalBlocks(content) {
  const opens = [];
  const closes = [];
  const openRe = /\[IF ([A-Z_ ]+):\]/g;
  const closeRe = /\[END IF ([A-Z_ ]+)\]/g;
  let match;
  while ((match = openRe.exec(content)) !== null) {
    opens.push(match[1].trim());
  }
  while ((match = closeRe.exec(content)) !== null) {
    closes.push(match[1].trim());
  }
  return { opens, closes };
}

describe('Pipeline B template integrity', () => {

  describe('template files exist', () => {
    const expectedTemplates = [
      'repo-scout-prompt-template.md',
      'repo-specialist-prompt-template.md',
      'repo-synthesizer-prompt-template.md',
      'repo-atlas-prompt-template.md',
      'repo-atlas-sketch-prompt-template.md',
      'repo-survey-prompt-template.md',
      'repo-team-protocol.md',
    ];

    for (const template of expectedTemplates) {
      it(`${template} exists`, () => {
        const p = path.join(PIPELINES_DIR, template);
        assert.ok(fileExists(p), `Missing template: ${p}`);
      });
    }

    it('repo-driver.md exists', () => {
      assert.ok(fileExists(REPO_DRIVER_PATH), `Missing driver: ${REPO_DRIVER_PATH}`);
    });
  });

  describe('repo-driver.md references all Pipeline B templates', () => {
    const repoMd = readFile(REPO_DRIVER_PATH);

    const expectedRefs = [
      'repo-scout-prompt-template.md',
      'repo-specialist-prompt-template.md',
      'repo-synthesizer-prompt-template.md',
      'repo-atlas-prompt-template.md',
      'repo-atlas-sketch-prompt-template.md',
      'repo-survey-prompt-template.md',
    ];

    for (const ref of expectedRefs) {
      it(`references ${ref}`, () => {
        assert.ok(
          repoMd.includes(ref),
          `repo-driver.md does not reference ${ref}`
        );
      });
    }
  });

  describe('conditional block matching', () => {
    const templates = [
      'repo-specialist-prompt-template.md',
      'repo-survey-prompt-template.md',
      'repo-atlas-sketch-prompt-template.md',
      'repo-atlas-prompt-template.md',
      'repo-synthesizer-prompt-template.md',
    ];

    for (const template of templates) {
      it(`${template} has matched IF/END IF blocks`, () => {
        const content = readFile(path.join(PIPELINES_DIR, template));
        const { opens, closes } = extractConditionalBlocks(content);

        // Every open must have a close
        for (const open of opens) {
          assert.ok(
            closes.includes(open),
            `[IF ${open}:] has no matching [END IF ${open}] in ${template}`
          );
        }

        // Every close must have an open
        for (const close of closes) {
          assert.ok(
            opens.includes(close),
            `[END IF ${close}] has no matching [IF ${close}:] in ${template}`
          );
        }

        // Same count
        assert.strictEqual(
          opens.length,
          closes.length,
          `Mismatched IF/END IF count in ${template}: ${opens.length} opens, ${closes.length} closes`
        );
      });
    }
  });

  describe('specialist template reading order', () => {
    const content = readFile(path.join(PIPELINES_DIR, 'repo-specialist-prompt-template.md'));

    it('survey section appears before deeper section', () => {
      const surveyPos = content.indexOf('[IF SURVEY MODE:]');
      const deeperPos = content.indexOf('[IF DEEPER MODE:]');
      if (surveyPos !== -1 && deeperPos !== -1) {
        assert.ok(surveyPos < deeperPos, 'Survey section should appear before deeper section');
      }
    });

    it('deeper section appears before deepest section', () => {
      const deeperPos = content.indexOf('[IF DEEPER MODE:]');
      const deepestPos = content.indexOf('[IF DEEPEST MODE:]');
      if (deeperPos !== -1 && deepestPos !== -1) {
        assert.ok(deeperPos < deepestPos, 'Deeper section should appear before deepest section');
      }
    });

    it('has all three conditional mode sections', () => {
      assert.ok(content.includes('[IF SURVEY MODE:]'), 'Missing [IF SURVEY MODE:]');
      assert.ok(content.includes('[IF DEEPER MODE:]'), 'Missing [IF DEEPER MODE:]');
      assert.ok(content.includes('[IF DEEPEST MODE:]'), 'Missing [IF DEEPEST MODE:]');
    });
  });

  describe('repo-driver.md step numbering', () => {
    const content = readFile(REPO_DRIVER_PATH);

    it('has sequential step numbers without gaps', () => {
      const stepRe = /^## Step (\d+(?:\.\d+)?)\b/gm;
      const steps = [];
      let match;
      while ((match = stepRe.exec(content)) !== null) {
        steps.push(match[1]);
      }
      // Should have steps 1 through 7 (plus 7.5)
      const wholeSteps = steps.filter(s => !s.includes('.')).map(Number);
      for (let i = 1; i < wholeSteps.length; i++) {
        assert.ok(
          wholeSteps[i] === wholeSteps[i - 1] + 1,
          `Step numbering gap: Step ${wholeSteps[i - 1]} followed by Step ${wholeSteps[i]}`
        );
      }
    });

    it('has no duplicate step numbers', () => {
      const stepRe = /^## Step (\d+(?:\.\d+)?)\b/gm;
      const steps = [];
      let match;
      while ((match = stepRe.exec(content)) !== null) {
        steps.push(match[1]);
      }
      const unique = new Set(steps);
      assert.strictEqual(steps.length, unique.size, `Duplicate step numbers: ${steps.join(', ')}`);
    });
  });

  describe('mode implication chain', () => {
    const repoMd = readFile(REPO_DRIVER_PATH);

    it('--deepest implies --deeper', () => {
      assert.ok(
        /--deepest[\s\S]{0,200}--deeper|--deeper[\s\S]{0,200}--deepest/.test(repoMd),
        'repo-driver.md should document that --deepest implies --deeper'
      );
    });

    it('--deepest implies --survey', () => {
      assert.ok(
        /--deepest.*--survey|--survey.*--deepest/s.test(repoMd),
        'repo-driver.md should document that --deepest implies --survey'
      );
    });
  });

  describe('atlas sketch artifacts referenced consistently', () => {
    const sketchTemplate = readFile(path.join(PIPELINES_DIR, 'repo-atlas-sketch-prompt-template.md'));
    const specialistTemplate = readFile(path.join(PIPELINES_DIR, 'repo-specialist-prompt-template.md'));
    const atlasTemplate = readFile(path.join(PIPELINES_DIR, 'repo-atlas-prompt-template.md'));

    const sketchArtifacts = [
      'atlas-sketch-file-index.md',
      'atlas-sketch-system-map.md',
      'atlas-sketch-connectivity-matrix.md',
    ];

    for (const artifact of sketchArtifacts) {
      it(`atlas sketch template outputs ${artifact}`, () => {
        assert.ok(
          sketchTemplate.includes(artifact),
          `Atlas sketch template missing reference to ${artifact}`
        );
      });

      it(`specialist template references ${artifact}`, () => {
        assert.ok(
          specialistTemplate.includes(artifact),
          `Specialist template missing reference to ${artifact}`
        );
      });
    }

    it('atlas refinement template references preliminary artifacts', () => {
      assert.ok(
        atlasTemplate.includes('PRELIMINARY_FILE_INDEX'),
        'Atlas template missing PRELIMINARY_FILE_INDEX reference'
      );
      assert.ok(
        atlasTemplate.includes('PRELIMINARY_SYSTEM_MAP'),
        'Atlas template missing PRELIMINARY_SYSTEM_MAP reference'
      );
      assert.ok(
        atlasTemplate.includes('PRELIMINARY_CONNECTIVITY_MATRIX'),
        'Atlas template missing PRELIMINARY_CONNECTIVITY_MATRIX reference'
      );
    });
  });

  describe('survey artifacts referenced consistently', () => {
    const surveyTemplate = readFile(path.join(PIPELINES_DIR, 'repo-survey-prompt-template.md'));
    const specialistTemplate = readFile(path.join(PIPELINES_DIR, 'repo-specialist-prompt-template.md'));

    it('survey template outputs to survey.md', () => {
      assert.ok(
        surveyTemplate.includes('survey.md'),
        'Survey template missing survey.md output path'
      );
    });

    it('specialist template references survey.md', () => {
      assert.ok(
        specialistTemplate.includes('survey.md'),
        'Specialist template missing survey.md reference'
      );
    });
  });

  describe('specialist atlas validation markers', () => {
    const specialistTemplate = readFile(path.join(PIPELINES_DIR, 'repo-specialist-prompt-template.md'));

    const markers = ['CONFIRMED', 'REFUTED', 'MISSING'];

    for (const marker of markers) {
      it(`specialist template instructs ${marker} marker usage`, () => {
        assert.ok(
          specialistTemplate.includes(`[${marker}`),
          `Specialist template missing [${marker}] marker instruction`
        );
      });
    }

    it('atlas refinement template consumes validation markers', () => {
      const atlasTemplate = readFile(path.join(PIPELINES_DIR, 'repo-atlas-prompt-template.md'));
      for (const marker of markers) {
        assert.ok(
          atlasTemplate.includes(`[${marker}]`),
          `Atlas template missing [${marker}] consumption instruction`
        );
      }
    });
  });

  describe('synthesizer deduplication rule', () => {
    const synthTemplate = readFile(path.join(PIPELINES_DIR, 'repo-synthesizer-prompt-template.md'));

    it('has deduplication rule section', () => {
      assert.ok(
        synthTemplate.includes('Deduplication Rule'),
        'Synthesizer template missing Deduplication Rule section'
      );
    });

    it('deduplication rule is scoped to comparison mode', () => {
      assert.ok(
        synthTemplate.includes('comparison mode only'),
        'Deduplication rule should be scoped to comparison mode only'
      );
    });

    it('preserves actionable recommendations for non-comparison runs', () => {
      assert.ok(
        synthTemplate.includes('Recommendations must be SPECIFIC and ACTIONABLE'),
        'Synthesizer must preserve actionable recommendations principle for non-comparison runs'
      );
    });
  });

  describe('phased team lifecycle', () => {
    const repoMd = readFile(REPO_DRIVER_PATH);

    it('atlas sketch is dispatched as a subagent, not a teammate', () => {
      // Should NOT have team_name in the atlas sketch Agent() call
      // The atlas sketch section should use plain Agent(model: "haiku") without team_name
      const sketchSection = repoMd.substring(
        repoMd.indexOf('Phase B: Atlas Sketch'),
        repoMd.indexOf('Phase C: Spawn Specialists')
      );
      assert.ok(
        !sketchSection.includes('team_name'),
        'Atlas sketch should be dispatched as a regular subagent (no team_name)'
      );
    });

    it('specialists are spawned in Phase C after atlas sketch', () => {
      const phaseBPos = repoMd.indexOf('Phase B: Atlas Sketch');
      const phaseCPos = repoMd.indexOf('Phase C: Spawn Specialists');
      assert.ok(phaseBPos !== -1, 'Missing Phase B: Atlas Sketch');
      assert.ok(phaseCPos !== -1, 'Missing Phase C: Spawn Specialists');
      assert.ok(phaseBPos < phaseCPos, 'Phase B should come before Phase C');
    });

    it('documents that non-deepest modes spawn all at once', () => {
      assert.ok(
        repoMd.includes('Spawn all 7 teammates in one message') ||
        repoMd.includes('all 7 teammates') ||
        repoMd.includes('spawn all teammates in one message'),
        'Should document that non-deepest modes spawn all teammates at once'
      );
    });
  });
});
