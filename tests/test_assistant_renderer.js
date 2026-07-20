const assert = require("node:assert/strict");
const { normalizeAssistantText } = require("../assets/assistant-renderer.js");

const source = [
  "在牛顿环实验中，核心公式用于计算透镜曲率半径",
  "\\(R\\)。",
  "",
  "- 基于暗环条件，第",
  "\\(k\\)",
  "级暗环的半径",
  "",
  "\\[",
  "r_k^2 = k\\lambda R",
  "\\]",
].join("\n");

const expected = [
  "在牛顿环实验中，核心公式用于计算透镜曲率半径 \\(R\\)。",
  "",
  "- 基于暗环条件，第 \\(k\\) 级暗环的半径",
  "",
  "\\[",
  "r_k^2 = k\\lambda R",
  "\\]",
].join("\n");

assert.equal(normalizeAssistantText(source), expected);
console.log("assistant renderer normalization: ok");
