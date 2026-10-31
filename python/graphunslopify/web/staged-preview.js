// Image progress has an attempt identity and never carries a final verdict.
export function createStagedPreview({token, client, current, mount}) {
  let enabled = false, sequence = 0, active = null;
  function invalidate() {
    sequence++;
    active?.abort();
    active = null;
  }
  return {
    configure(value) { enabled = value === true; },
    invalidate,
    begin(identity) {
      invalidate();
      const owner = sequence, controller = new AbortController();
      const ticket = enabled ? crypto.randomUUID().replaceAll("-", "") : null;
      let pending = true, decoding = null;
      const isCurrent = () => {
        const now = current();
        return owner === sequence && now.generation === identity.generation &&
          now.data_id === identity.data_id && now.palette_id === identity.palette_id;
      };
      function finish() {
        pending = false;
        controller.abort();
        if (decoding) decoding.src = "";
      }
      active = {abort: finish};
      async function watch() {
        if (!ticket) return;
        const query = new URLSearchParams({client, generation: identity.generation});
        try {
          while (pending && isCurrent()) {
            const response = await fetch(`/stage/${ticket}?${query}`, {
              headers: {"X-Preview-Token": token}, signal: controller.signal,
            });
            if (response.status === 404) {
              await new Promise(resolve => setTimeout(resolve, 20));
              continue;
            }
            if (!response.ok) return;
            const stage = await response.json();
            if (!pending || !isCurrent()) return;
            if (stage.phase === "pending") continue;
            if (stage.phase !== "unverified" || stage.verified !== false ||
                stage.ticket !== ticket || stage.generation !== identity.generation ||
                stage.data_id !== identity.data_id || !/^[0-9a-f]{32}$/.test(stage.attempt) ||
                !/^[0-9a-f]{64}$/.test(stage.image?.sha256)) return;
            const imageQuery = new URLSearchParams({...Object.fromEntries(query),
              token, attempt: stage.attempt});
            const url = `/stage/${ticket}/png?${imageQuery}`;
            decoding = new Image();
            decoding.src = url;
            await decoding.decode();
            if (decoding.naturalWidth !== stage.image.width ||
                decoding.naturalHeight !== stage.image.height) return;
            if (pending && isCurrent()) mount({url, stage, identity});
            return;
          }
        } catch {
          // Optional progress failure cannot replace or fail the original render.
        }
      }
      return {isCurrent, finish, start: () => { void watch(); },
        payload: ticket ? {stage_id: ticket} : {}};
    },
  };
}
