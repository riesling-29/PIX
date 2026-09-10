"use strict";

// Run npm ci --ignore-scripts, then this script. No network is used here.
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const version = "0.12.0";
const tarball = "https://registry.npmjs.org/elkjs/-/elkjs-0.12.0.tgz";
const integrity = "sha512-YZcKynxVxYoKIOEpywEPwCFdg+BTbxQRNf3pbwdDCvc8O3kQD8bmIwSxKU1eOTVc4Xo+VG9Te+575mlfvOrhEQ==";
const files = [
  ["lib/elk.bundled.js", "elk.bundled.js", "1222e44f953ce7746af23801e723708f8e6f436b8b377a6a5fc7552f34a307b3"],
  ["LICENSE.md", "ELK-LICENSE.md", "637e81f4a1b6b4079535c499fca05e238cf7605c1ff5b76d60d7da7ce96700c9"],
];
const source = path.join(__dirname, "node_modules", "elkjs");
const target = path.resolve(__dirname, "../../src/pix/viewer/assets/vendor");
const check = process.argv.includes("--check");
const lock = JSON.parse(fs.readFileSync(path.join(__dirname, "package-lock.json"), "utf8"));
const dependency = lock.packages["node_modules/elkjs"];
if (dependency.version !== version || dependency.resolved !== tarball || dependency.integrity !== integrity) {
  throw new Error("ELK lockfile does not match the reviewed dependency pin");
}
const installed = JSON.parse(fs.readFileSync(path.join(source, "package.json"), "utf8"));
if (installed.version !== version) throw new Error("Installed ELK version does not match pin");
const payloads = files.map(([from, to, expected]) => {
  const bytes = fs.readFileSync(path.join(source, from));
  const actual = crypto.createHash("sha256").update(bytes).digest("hex");
  if (actual !== expected) throw new Error(`Unexpected source SHA256: ${from}`);
  return { to, bytes, sha256: actual };
});
const provenance = {
  package: "elkjs", version, registry_tarball: tarball, registry_integrity: integrity,
  upstream: "https://github.com/kieler/elkjs", source_release: "https://github.com/kieler/elkjs/tree/0.12.0",
  source_commit: "ff5771d7165445c42c408bb8a090c8035272218c",
  license: "EPL-2.0 OR GPL-3.0-or-later", selected_license: "EPL-2.0", modified: false,
  verified_on: "2026-09-09", reproduction: "cd tools/viewer_vendor && npm ci --ignore-scripts && npm run vendor",
  files: payloads.map(item => ({ file: item.to, sha256: item.sha256, bytes: item.bytes.length })),
};
payloads.push({ to: "provenance.json", bytes: Buffer.from(JSON.stringify(provenance, null, 2) + "\n") });
if (!check) fs.mkdirSync(target, { recursive: true });
for (const item of payloads) {
  const destination = path.join(target, item.to);
  if (check) {
    if (!fs.readFileSync(destination).equals(item.bytes)) throw new Error(`Vendored file differs: ${item.to}`);
  } else fs.writeFileSync(destination, item.bytes);
}
process.stdout.write(`ELK ${version}: ${check ? "verified" : "vendored"} ${payloads.length} files\n`);
