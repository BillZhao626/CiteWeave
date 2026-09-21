import { expect, it } from "vitest";
import { citationForPart, citationParts } from "./citation-tokens";

it("links only positive ASCII E tokens backed by final citations", () => {
  const citations = [{ label: "E1" }, { label: "E2" }, { label: "E17" }];
  const text =
    'Sources [RFC7252] [HTTP] [MQTT-3.1.2-18] [ ":" port ] [fake] [E2][E1][E17] [E999]';
  const parts = citationParts(text);
  expect(parts.join("")).toBe(text);
  expect(
    parts.map((part) => citationForPart(part, citations)).filter(Boolean),
  ).toEqual([citations[1], citations[0], citations[2]]);
  expect(citationForPart("[E999]", citations)).toBeUndefined();
});

it.each([
  "[Efoo]",
  "[E-1]",
  "[E0]",
  "[E01]",
  "[E１]",
  "[E1 ]",
  "[E1",
  "[fake]",
])("does not turn malformed or ordinary %s into a citation button", (token) => {
  expect(citationParts(token)).toEqual([token]);
  expect(
    citationForPart(token, [{ label: token.slice(1, -1) }]),
  ).toBeUndefined();
});
