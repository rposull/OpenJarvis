/**
 * FormSubmit webhook → ntfy push alert on new estimate requests.
 *
 * Netlify env (Site configuration → Environment variables):
 *   NTFY_TOPIC  — private topic from ntfy app (required for alerts)
 *   NTFY_SERVER — optional, default https://ntfy.sh
 */

const DEFAULT_SERVER = "https://ntfy.sh";

function parseBody(raw, contentType = "") {
  if (!raw) return {};
  const ct = contentType.toLowerCase();
  if (ct.includes("application/json")) {
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }
  const params = new URLSearchParams(raw);
  return Object.fromEntries(params.entries());
}

export async function handler(event) {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  const topic = (process.env.NTFY_TOPIC || "").trim();
  if (!topic) {
    return { statusCode: 200, body: "ok (NTFY_TOPIC not set)" };
  }

  const data = parseBody(event.body, event.headers["content-type"] || event.headers["Content-Type"]);
  const name = data.name || "Unknown";
  const phone = data.phone || "—";
  const town = data.town || "—";
  const project = data.project || "—";
  const email = data.email || "—";
  const message = (data.message || "").slice(0, 400);

  const body = [
    `Name: ${name}`,
    `Phone: ${phone}`,
    `Email: ${email}`,
    `Town: ${town}`,
    `Project: ${project}`,
    message ? `\n${message}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  const server = (process.env.NTFY_SERVER || DEFAULT_SERVER).replace(/\/$/, "");

  try {
    const resp = await fetch(`${server}/${topic}`, {
      method: "POST",
      headers: {
        Title: "New estimate request",
        Priority: "high",
        Tags: "construction,money",
      },
      body,
    });
    if (!resp.ok) {
      console.error("ntfy failed", resp.status, await resp.text());
    }
  } catch (err) {
    console.error("ntfy error", err);
  }

  return { statusCode: 200, body: "ok" };
}
