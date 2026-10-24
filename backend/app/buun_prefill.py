"""Opt-in Buun prefill probe; not wired into production chat routes.

Use the same worker for template application and completion.  This deliberately
rejects multimodal input until its template equivalence is demonstrated.
"""
from dataclasses import dataclass
import httpx

class PrefillUnsupported(RuntimeError):
    pass

@dataclass(frozen=True)
class PrefillResult:
    prompt_tokens: int | None
    generated_tokens: int

async def prefill_messages(client: httpx.AsyncClient, worker_url: str, messages: list[dict], *, slot_id: int = 0, tools: list[dict] | None = None) -> PrefillResult:
    if not messages or not all(isinstance(m, dict) and m.get('role') in ('system','user','assistant','tool') and isinstance(m.get('content'), str) for m in messages):
        raise PrefillUnsupported('Only nonempty text-only messages are supported')
    if not isinstance(slot_id, int) or isinstance(slot_id, bool) or slot_id < 0:
        raise ValueError('Invalid slot')
    base = worker_url.rstrip('/')
    payload = {'messages': messages, 'add_generation_prompt': False}
    if tools:
        payload['tools'] = tools
    try:
        r = await client.post(f'{base}/apply-template', json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
        prompt = data.get('prompt')
        if not isinstance(prompt, (str, list)) or not prompt:
            raise PrefillUnsupported('No usable formatted prompt returned')
        r = await client.post(f'{base}/completion', json={'prompt': prompt, 'n_predict': 0, 'cache_prompt': True, 'id_slot': slot_id, 'stream': False}, timeout=300)
        r.raise_for_status()
        output = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PrefillUnsupported(f'Buun prefill API unavailable: {exc}') from exc
    generated = output.get('tokens_predicted', output.get('timings', {}).get('predicted_n'))
    if generated != 0 or output.get('content'):
        raise PrefillUnsupported('Prefill unexpectedly generated output')
    return PrefillResult(prompt_tokens=output.get('tokens_evaluated'), generated_tokens=0)
