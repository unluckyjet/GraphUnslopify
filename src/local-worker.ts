/** Private bounded compiler RPC. The canonical dispatcher never reads datasets. */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { TextDecoder } from "node:util";
import { z } from "zod";

const PROTOCOL = 1;
const MAX_REQUEST = 4 * 1024 * 1024;
const MAX_FRAME = 16 * 1024 * 1024;
const envelope = z.object({
  protocol: z.literal(PROTOCOL),
  id: z.string().regex(/^[0-9a-f]{32}$/),
  payload: z.object({ operation: z.string(), payload: z.unknown().optional() }).strict(),
}).strict();
const message = (error: unknown) => error instanceof Error ? error.message : String(error);

export async function serveLocalWorker(
  dispatch: (operation: string, payload: unknown) => unknown,
  entry: string,
): Promise<void> {
  const max = Number(process.argv[3] ?? 64);
  if (process.argv.length > 4 || !Number.isSafeInteger(max) || max < 1 || max > 128)
    throw new Error("Translator worker request bound must be between1 and128");
  const source = createHash("sha256").update(readFileSync(new URL(entry))).digest("hex");
  async function send(body: Record<string, unknown>) {
    const frame = JSON.stringify({ protocol: PROTOCOL, ...body }) + "\n";
    if (Buffer.byteLength(frame, "utf8") > MAX_FRAME)
      throw new Error("Translator response exceeds the private frame budget");
    await new Promise<void>((resolve, reject) => {
      process.stdout.write(frame, error => error ? reject(error) : resolve());
    });
  }
  await send({
    ready: true, kind: "translator", pid: process.pid, node: process.version,
    bundle_sha256: source, max_requests: max,
    max_request_bytes: MAX_REQUEST, max_frame_bytes: MAX_FRAME,
  });
  const decode = new TextDecoder("utf-8", { fatal: true });
  let pending = Buffer.alloc(0), count = 0, identity: string | null = null;
  try {
    for await (const chunk of process.stdin) {
      pending = Buffer.concat([pending, chunk as Buffer]);
      let end: number;
      while ((end = pending.indexOf(10)) >= 0) {
        identity = null;
        if (end + 1 > MAX_REQUEST) throw new Error("Translator request exceeds the private frame budget");
        const raw = pending.subarray(0, end);
        pending = pending.subarray(end + 1);
        const parsed: unknown = JSON.parse(decode.decode(raw));
        if (parsed && typeof parsed === "object" && "id" in parsed && typeof parsed.id === "string")
          identity = parsed.id;
        const request = envelope.parse(parsed);
        let result: { ok: true; result: unknown } | { ok: false; error: string };
        try {
          result = { ok: true, result: dispatch(request.payload.operation, request.payload.payload ?? {}) };
        } catch (error) {
          // User validation/operation errors preserve the original one-shot response.
          result = { ok: false, error: message(error) };
        }
        const retire = ++count === max;
        await send({ id: request.id, ok: true, result, retire });
        if (retire) { process.stdin.destroy(); return; }
      }
      if (pending.length > MAX_REQUEST) throw new Error("Translator request exceeds the private frame budget");
    }
    if (pending.length) throw new Error("Translator request ended without its frame delimiter");
  } catch (error) {
    // Protocol/source/transport failures never become successful compiler results.
    await send({ id: identity, ok: false, error: message(error), retire: true });
    process.exitCode = 1;
    process.stdin.destroy();
  }
}
