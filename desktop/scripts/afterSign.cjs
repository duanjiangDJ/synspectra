"use strict";

// Ad-hoc signs the macOS app bundle when no Developer ID certificate is
// available. Apple Silicon refuses to run completely unsigned apps, which
// surfaces as "app is damaged and can't be opened". electron-builder runs
// this hook after packing the app and before creating the .dmg.

const { execSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

exports.default = async function afterSign(context) {
  if (process.platform !== "darwin") return;
  const appOutDir = context.appOutDir;
  if (!appOutDir) return;
  // appOutDir is the directory that contains the .app bundle
  // (release/mac-arm64/), not the bundle itself.
  const appBundle = path.join(appOutDir, "SynSpectra.app");
  if (!fs.existsSync(appBundle)) {
    console.log("[afterSign] app bundle not found at " + appBundle);
    return;
  }
  console.log("[afterSign] ad-hoc signing " + appBundle);
  execSync(`codesign --force --deep --sign - ${JSON.stringify(appBundle)}`, {
    stdio: "inherit",
  });
};
