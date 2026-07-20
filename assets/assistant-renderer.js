(function (global) {
  "use strict";

  function normalizeAssistantText(value) {
    let text = String(value ?? "").replace(/\r\n?/g, "\n");

    // AI models sometimes wrap an inline formula onto its own lines.
    text = text.replace(/\\\(([\s\S]*?)\\\)/g, function (_, formula) {
      return "\\(" + formula.replace(/[ \t]*\n[ \t]*/g, " ").trim() + "\\)";
    });
    text = text.replace(/([^\n])\n[ \t]*(?=\\\()/g, "$1 ");
    text = text.replace(/(\\\))\n[ \t]*(?=[^\n])/g, "$1 ");
    return text.replace(/\n{3,}/g, "\n\n").trim();
  }

  function appendTextBlock(parent, text) {
    const paragraph = document.createElement("p");
    paragraph.className = "message-paragraph";
    paragraph.textContent = text;
    parent.appendChild(paragraph);
  }

  function render(container, value) {
    const text = normalizeAssistantText(value);
    const displayMath = [];
    const protectedText = text.replace(/\\\[[\s\S]*?\\\]/g, function (formula) {
      const token = "@@ASSISTANT_DISPLAY_MATH_" + displayMath.length + "@@";
      displayMath.push(formula);
      return "\n\n" + token + "\n\n";
    });

    container.replaceChildren();
    protectedText.split(/\n{2,}/).forEach(function (block) {
      const trimmed = block.trim();
      if (!trimmed) return;

      const mathMatch = trimmed.match(/^@@ASSISTANT_DISPLAY_MATH_(\d+)@@$/);
      if (mathMatch) {
        const mathBlock = document.createElement("div");
        mathBlock.className = "message-math";
        mathBlock.textContent = displayMath[Number(mathMatch[1])];
        container.appendChild(mathBlock);
        return;
      }

      let paragraphLines = [];
      let list = null;
      let listType = "";
      const flushParagraph = function () {
        if (paragraphLines.length) {
          appendTextBlock(container, paragraphLines.join(" "));
          paragraphLines = [];
        }
      };
      const flushList = function () {
        if (list) {
          container.appendChild(list);
          list = null;
          listType = "";
        }
      };

      trimmed.split("\n").forEach(function (line) {
        const bullet = line.match(/^\s*[-*•·]\s+(.+)$/);
        const numbered = line.match(/^\s*\d+[.、)]\s+(.+)$/);
        if (bullet || numbered) {
          flushParagraph();
          const nextType = numbered ? "ol" : "ul";
          if (!list || listType !== nextType) {
            flushList();
            list = document.createElement(nextType);
            list.className = "message-list";
            listType = nextType;
          }
          const item = document.createElement("li");
          item.textContent = (bullet || numbered)[1];
          list.appendChild(item);
          return;
        }
        flushList();
        if (line.trim()) paragraphLines.push(line.trim());
      });
      flushParagraph();
      flushList();
    });
  }

  const api = { normalizeAssistantText, render };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    global.AssistantRenderer = api;
  }
})(typeof globalThis === "undefined" ? window : globalThis);
