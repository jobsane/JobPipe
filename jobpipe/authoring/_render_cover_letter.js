#!/usr/bin/env node
/**
 * Render a cover letter .docx from JSON on stdin.
 * Usage: node _render_cover_letter.js <output_path>
 * Input (stdin): JSON with keys: recipientName, senderName, date, body (string[])
 */

const { Document, Packer, Paragraph, TextRun, AlignmentType } = require("docx");
const fs = require("fs");

async function main() {
  const outputPath = process.argv[2];
  if (!outputPath) {
    process.stderr.write("Usage: node _render_cover_letter.js <output_path>\n");
    process.exit(1);
  }

  let raw = "";
  for await (const chunk of process.stdin) raw += chunk;

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (e) {
    process.stderr.write("Invalid JSON on stdin: " + e.message + "\n");
    process.exit(1);
  }

  const { recipientName = "", senderName = "", date = "", body = [] } = payload;

  const paragraphs = [
    new Paragraph({
      children: [new TextRun({ text: date })],
    }),
    new Paragraph({ text: "" }),
    new Paragraph({
      children: [new TextRun({ text: recipientName })],
    }),
    new Paragraph({ text: "" }),
    ...body.map(
      (line) =>
        new Paragraph({
          children: [new TextRun({ text: line })],
          alignment: AlignmentType.JUSTIFIED,
        })
    ),
    new Paragraph({ text: "" }),
    new Paragraph({
      children: [new TextRun({ text: senderName })],
    }),
  ];

  const doc = new Document({
    sections: [
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 }, // A4 in DXA
          },
        },
        children: paragraphs,
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
}

main().catch((e) => {
  process.stderr.write(e.message + "\n");
  process.exit(1);
});
