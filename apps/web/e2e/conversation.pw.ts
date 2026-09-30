import { expect, test, type Page, type Request } from "@playwright/test";

const kb = process.env.CW_BROWSER_KB!;
const version = process.env.CW_BROWSER_VERSION!;
async function open(page: Page, base = process.env.CW_BROWSER_TEST_URL!) {
  await page.goto(`${base}/kb/${kb}`);
  await page
    .getByLabel("访问令牌", { exact: true })
    .fill("synthetic-browser-token-not-a-secret");
  await page.getByRole("button", { name: "进入工作空间" }).click();
  await page.getByRole("checkbox", { name: /Synthetic metadata/ }).check();
  await page.getByRole("button", { name: "开始会话", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "新会话", exact: true }),
  ).toBeVisible();
}
async function submit(page: Page, question: string) {
  await page.getByLabel("下一条问题或澄清回复").fill(question);
  await page.getByRole("button", { name: "发送会话问题", exact: true }).focus();
  await page.keyboard.press("Enter");
}
function submissions(page: Page) {
  const requests: Request[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/turns"))
      requests.push(request);
  });
  return requests;
}

test("documentary → PDF → durable follow-up → Trace → reload → insufficiency", async ({
  page,
}, info) => {
  const requests = submissions(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await open(page);
  await submit(page, "What does the receiver do?");
  await expect(page.getByText("文档答案", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(1);
  expect(requests[0].postDataJSON()).toEqual({
    question: "What does the receiver do?",
    expected_head: null,
    scope: { kb_id: kb, version_ids: [version] },
  });
  const citation = page.getByRole("button", {
    name: "查看引用 E1",
    exact: true,
  });
  await citation.click();
  await expect(page.locator(".evidence-highlight")).toHaveCount(1);
  await expect(page.locator(".pdf-page")).toHaveAttribute(
    "data-page-index",
    "0",
  );
  await expect(page.getByLabel("原始 PDF 第 1 页")).toBeVisible();
  await page.getByText("来源与版本详情", { exact: true }).click();
  await expect(page.locator(".pdf-viewer .source-details")).toContainText(
    version,
  );
  const evidence = await page
    .locator(".evidence-highlight")
    .getAttribute("data-evidence-id");
  await page.getByText("Trace Inspector · 持久记录", { exact: true }).click();
  await expect(
    page.getByText("CURRENT_PACK_PHYSICAL_ONLY", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("NOT_ASSESSED", { exact: true })).toBeVisible();
  const path = requests[0].url().replace(/\/turns$/, "");
  const conversation = await (await page.request.get(path)).json();
  await page.screenshot({
    path: info.outputPath("documentary-pdf.png"),
    fullPage: true,
  });
  await submit(page, "Clarify receiver");
  await expect(page.getByText("需要澄清", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[1].postDataJSON().expected_head).toBe(conversation.head_id);
  expect(requests[1].headers()["idempotency-key"]).not.toBe(
    requests[0].headers()["idempotency-key"],
  );
  await citation.click();
  await expect(page.locator(".evidence-highlight")).toHaveAttribute(
    "data-evidence-id",
    evidence!,
  );
  await page.reload();
  await expect(page.getByText("需要澄清", { exact: true })).toBeVisible();
  await expect(page.getByText("文档答案", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(2);
  await page
    .getByText("Trace Inspector · 持久记录", { exact: true })
    .last()
    .click();
  await expect(page.locator(".conversation-turn").last()).toContainText(
    "未记录 / 不可用",
  );
  await submit(page, "No matching evidence");
  await expect(
    page.getByText("当前授权证据不足", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".conversation-turn").last().locator(".inline-citation"),
  ).toHaveCount(0);
  expect(requests).toHaveLength(3);
  await page.setViewportSize({ width: 390, height: 844 });
  await citation.click();
  await expect(page.locator(".evidence-highlight")).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("small-window.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("lost receipt → reload → same-key recovery publishes exactly one accepted Run", async ({
  page,
}) => {
  const requests = submissions(page);
  await open(page);
  await submit(page, "Lose receipt after commit");
  await expect(page.getByRole("alert")).toContainText("未确认");
  await expect(page.getByText("文档答案", { exact: true })).toHaveCount(0);
  expect(requests).toHaveLength(1);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "使用同一提交身份恢复" }),
  ).toBeEnabled();
  expect(requests).toHaveLength(1);
  await page.getByRole("button", { name: "使用同一提交身份恢复" }).click();
  await expect(page.getByText("文档答案", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[0].postDataJSON()).toEqual(requests[1].postDataJSON());
  expect(requests[0].headers()["idempotency-key"]).toBe(
    requests[1].headers()["idempotency-key"],
  );
  await page.reload();
  await expect(page.locator(".conversation-turn")).toHaveCount(1);
  expect(requests).toHaveLength(2);
});

test("default production runtime remains unavailable without inventing failure", async ({
  page,
}) => {
  const requests = submissions(page);
  await open(page, process.env.CW_BROWSER_DEFAULT_URL!);
  await submit(page, "Default must stay unavailable");
  await expect(page.getByRole("alert")).toContainText("运行时不可用");
  await expect(page.locator(".conversation-turn")).toHaveCount(0);
  await page.getByRole("button", { name: "使用同一提交身份恢复" }).click();
  await expect(page.getByRole("alert")).toContainText("运行时不可用");
  expect(requests).toHaveLength(2);
  expect(requests[0].headers()["idempotency-key"]).toBe(
    requests[1].headers()["idempotency-key"],
  );
  const current = await (
    await page.request.get(requests[0].url().replace(/\/turns$/, ""))
  ).json();
  expect(current.head_id).toBeNull();
  expect(current.active_run_id).toBeNull();
});
