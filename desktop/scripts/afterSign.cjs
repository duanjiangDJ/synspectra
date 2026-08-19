"use strict";

// Ad-hoc signs the macOS app bundle when no Developer ID certificate is
// available. Apple Silicon refuses to run completely unsigned apps, which
// surfaces as "app is damaged and can't be opened". electron-builder runs
// this hook after packing the app and before creating the .dmg.

const { execSync } = require("node:child_process");

exports.default = async function afterSign(context) {
  if (process.platform !== "darwin") return;
  const appOutDir = context.appOutDir;
  if (!appOutDir) return;
  console.log("[afterSign] ad-hoc signing " + appOutDir);
  execSync(`codesign --force --deep --sign - ${JSON.stringify(appOutDir)}`, {
    stdio: "inherit",
  });
};
