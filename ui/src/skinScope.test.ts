import test from "node:test";
import assert from "node:assert/strict";
import { skinStrengthOptions, skinMaskUnavailable } from "./skinScope.ts";
import { readFileSync } from "node:fs";

test("skin panel explicitly selects the semantic channel", () => {
  assert.deepEqual(skinStrengthOptions(), { channel: "skin" });
});
test("empty skin masks are unavailable, unknown old metadata is not invented", () => {
  assert.equal(skinMaskUnavailable({ skin: 0 }), true);
  assert.equal(skinMaskUnavailable({ skin: 1 }), false);
  assert.equal(skinMaskUnavailable(undefined), false);
});
test("actual panel uses the tested scope and availability helpers", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /setStrength\(strengthRef\.current, skinStrengthOptions\(\)\)/);
  assert.match(app, /skinMaskUnavailable\(pc\?\.mask_nonzero_pixels\)/);
});

test("ordinary import preserves neutral defaults and each saved recipe", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /\[strength, setStrengthV\] = useState\(0\.0\)/);
  assert.match(app, /await loadImage\(p, \{ maxPx, precompute: "auto" \}\)/);
  assert.doesNotMatch(app, /loadImage\(p, \{[^}]*strength/);
});

test("main retouch panel never submits stale whole-document skin parameters", async () => {
  const { skinEditOptions, skinMaskReady } = await import("./skinScope.ts");
  assert.deepEqual(skinEditOptions({radius:20}),{channel:"skin",interactionKey:"radius",radius:20});
  assert.deepEqual(skinEditOptions({strength:.5}),{channel:"skin",interactionKey:"strength"});
  assert.equal(skinMaskReady(["skin"],{skin:10}),true);
  assert.equal(skinMaskReady(["skin"],{skin:0}),false);
  assert.equal(skinMaskReady(["skin"]),false);
  assert.equal(skinMaskReady([],{skin:10}),false);
  const panel=readFileSync(new URL("./components/RetouchPanel.tsx",import.meta.url),"utf8");
  assert.match(panel,/setStrength\(patch.strength, skinEditOptions\(patch\)\)/);
  assert.match(panel,/if \(skinWhy\)/);
  assert.doesNotMatch(panel,/patch.strength \?\? doc.strength/);
});
