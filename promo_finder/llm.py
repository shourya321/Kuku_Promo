"""Model-agnostic LLM layer.

Every model call in the project goes through `LLM.json(role, system, user, schema)`.
Which model serves which role is set in models.yaml, so swapping Gemini for
Groq, OpenRouter, a local Ollama model or a Kuku-provided API is a config change.

Any OpenAI-compatible endpoint works (Gemini, Groq, OpenRouter, Ollama, vLLM,
Together, OpenAI...). Features:
  * JSON output validated against a Pydantic schema, with a repair retry
  * on-disk cache keyed by (model, prompt) -> reruns are free and reproducible,
    and the cache doubles as the "raw outputs" log of every model response
  * per-model pacing + exponential backoff for free-tier rate limits
  * fallback chain: if a role's primary model keeps failing, try the next one
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Type

import yaml
from pydantic import BaseModel, ValidationError


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    if text.startswith("{") or text.startswith("["):
        return text
    m = re.search(r"\{.*\}", text, flags=re.S)
    return m.group(0) if m else text


class LLM:
    def __init__(self, config_path: str | Path = "models.yaml", profile: str | None = None,
                 cache_dir: str | Path = ".cache/llm", use_cache: bool = True, log=print,
                 keys: dict[str, str] | None = None):
        # keys: {env var name: key} for THIS client only (e.g. a key a visitor typed into the app).
        # Never written to os.environ, which every session of a server process shares.
        self.keys = {k: v for k, v in (keys or {}).items() if v}
        cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        self.profile_name = profile or cfg.get("default_profile")
        if self.profile_name not in cfg["profiles"]:
            raise LLMError(f"Unknown profile '{self.profile_name}'. Options: {list(cfg['profiles'])}")
        self.providers = cfg["providers"]
        self.roles = cfg["profiles"][self.profile_name]
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self.log = log
        self._clients: dict = {}
        self._last_call: dict[str, float] = {}
        self._lock = threading.RLock()   # stats + pacing are shared when the miner runs episodes in parallel
        self.stats = {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0,
                      "failures": 0, "by_model": {}}

    # ------------------------------------------------------------------
    def describe(self) -> dict:
        return {role: [m["provider"] + ":" + m["model"] for m in self._chain(role)] for role in self.roles}

    def _chain(self, role: str) -> list[dict]:
        spec = self.roles.get(role) or self.roles.get("default")
        if spec is None:
            raise LLMError(f"No model configured for role '{role}' in profile '{self.profile_name}'")
        return spec if isinstance(spec, list) else [spec]

    def _key(self, provider: str) -> str:
        p = self.providers[provider]
        env = p.get("api_key_env", "")
        return self.keys.get(env) or os.environ.get(env, "") or p.get("api_key", "")

    def _has_key(self, provider: str) -> bool:
        return not self.providers[provider].get("requires_key", True) or bool(self._key(provider))

    def _client(self, provider: str):
        if provider not in self._clients:
            from openai import OpenAI
            p = self.providers[provider]
            key = self._key(provider)
            if not key and p.get("requires_key", True):
                raise LLMError(f"Missing API key: set environment variable {p.get('api_key_env')}")
            self._clients[provider] = OpenAI(base_url=p["base_url"], api_key=key or "none",
                                             timeout=p.get("timeout_s", 120), max_retries=0)
        return self._clients[provider]

    def _pace(self, provider: str, model_cfg: dict):
        """Keep each model under its rpm. Thread-safe: with --concurrency, each thread reserves the next
        free slot under the lock, then sleeps outside it, so the rpm limit holds across threads."""
        rpm = model_cfg.get("rpm") or self.providers[provider].get("rpm")
        if not rpm:
            return
        gap = 60.0 / rpm
        key = provider + ":" + model_cfg["model"]
        with self._lock:
            slot = max(time.time(), self._last_call.get(key, 0) + gap)
            self._last_call[key] = slot
        wait = slot - time.time()
        if wait > 0:
            time.sleep(wait)

    # ------------------------------------------------------------------
    def json(self, role: str, system: str, user: str, schema: Type[BaseModel],
             temperature: float = 0.2, tag: str = "") -> tuple[BaseModel, dict]:
        """Call the model for `role`, return (validated object, metadata)."""
        errors = []
        # Skip models whose API key is not set (e.g. a Groq+Gemini profile with only a Gemini key),
        # as long as at least one model in the chain can run. Saves a failed attempt + log line per call.
        chain = [m for m in self._chain(role) if self._has_key(m["provider"])] or self._chain(role)
        for i, mcfg in enumerate(chain):
            try:
                return self._json_one(mcfg, system, user, schema, temperature, tag, role,
                                      has_fallback=i < len(chain) - 1)
            except Exception as e:  # try next model in the fallback chain
                errors.append(f"{mcfg['provider']}:{mcfg['model']}: {e}")
                self.stats["failures"] += 1
                self.log(f"  ! {role} via {mcfg['model']} failed: {str(e)[:200]}")
        raise LLMError(" | ".join(errors))

    def _json_one(self, mcfg, system, user, schema, temperature, tag, role, has_fallback=False):
        provider, model = mcfg["provider"], mcfg["model"]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        key_src = json.dumps({"m": model, "p": provider, "msg": messages, "t": temperature}, sort_keys=True)
        key = hashlib.sha256(key_src.encode()).hexdigest()[:20]
        path = self.cache_dir / f"{tag or role}__{key}.json"

        if self.use_cache and path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            try:
                obj = schema.model_validate_json(_extract_json(rec["response"]))
                with self._lock:
                    self.stats["cache_hits"] += 1
                return obj, {"model": f"{provider}:{model}", "cached": True, "cache_file": path.name}
            except ValidationError:
                pass  # stale/invalid cache entry: call again

        last_text, last_err = "", ""
        for attempt in range(3):  # attempt 0 normal, 1-2 = repair after invalid JSON
            msgs = list(messages)
            if attempt and last_text:
                msgs += [{"role": "assistant", "content": last_text[:6000]},
                         {"role": "user", "content": f"Your output was not valid for the schema: {last_err[:800]}\n"
                                                     "Return ONLY the corrected JSON object."}]
            text, usage = self._raw_call(provider, mcfg, msgs, temperature, has_fallback)
            last_text = text
            try:
                obj = schema.model_validate_json(_extract_json(text))
                rec = {"role": role, "tag": tag, "provider": provider, "model": model,
                       "temperature": temperature, "messages": msgs, "response": text, "usage": usage,
                       "time": time.strftime("%Y-%m-%d %H:%M:%S")}
                path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                return obj, {"model": f"{provider}:{model}", "cached": False, "cache_file": path.name,
                             "repairs": attempt}
            except ValidationError as e:
                last_err = str(e)
        raise LLMError(f"invalid JSON after repairs: {last_err[:300]}")

    def _raw_call(self, provider, mcfg, messages, temperature, has_fallback=False):
        client = self._client(provider)
        # A rate-limited model with a fallback behind it: give up after 2 tries and move on,
        # instead of sleeping through 6 backoffs (minutes) on a model that is throttled anyway.
        max_429 = 2 if has_fallback else 6
        model = mcfg["model"]
        pcfg = self.providers[provider]
        delay = 5.0
        for attempt in range(6):
            self._pace(provider, mcfg)
            try:
                kwargs = dict(model=model, messages=messages, temperature=temperature)
                if mcfg.get("max_tokens"):
                    kwargs["max_tokens"] = mcfg["max_tokens"]
                if pcfg.get("json_mode", True):
                    kwargs["response_format"] = {"type": "json_object"}
                if mcfg.get("extra_body"):
                    kwargs["extra_body"] = mcfg["extra_body"]
                r = client.chat.completions.create(**kwargs)
                text = r.choices[0].message.content or ""
                u = getattr(r, "usage", None)
                usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                         "completion_tokens": getattr(u, "completion_tokens", 0) or 0}
                with self._lock:
                    self.stats["calls"] += 1
                    self.stats["prompt_tokens"] += usage["prompt_tokens"]
                    self.stats["completion_tokens"] += usage["completion_tokens"]
                    bm = self.stats["by_model"].setdefault(f"{provider}:{model}", {"calls": 0, "in": 0, "out": 0})
                    bm["calls"] += 1; bm["in"] += usage["prompt_tokens"]; bm["out"] += usage["completion_tokens"]
                if not text.strip():
                    raise LLMError("empty response")
                return text, usage
            except Exception as e:
                msg = str(e)
                status = getattr(e, "status_code", None)
                low = msg.lower()
                self.stats.setdefault("error_samples", []).append(f"{model}: {status} {msg[:300]}")
                daily_quota = status == 429 and ("perday" in low.replace(" ", "") or "per day" in low
                                                 or "requests_per_day" in low or "limit: 0" in low)
                retryable = not daily_quota and (status in (408, 429, 500, 502, 503, 504) or "rate" in low
                                                 or "timeout" in low or "connection" in low or "empty response" in msg)
                if daily_quota:
                    self.log(f"  ! {model}: daily free-tier quota used up -> trying fallback model")
                if not retryable or attempt == 5 or (status == 429 and attempt + 1 >= max_429):
                    raise
                m = re.search(r"retry(?:Delay| in|-after)?[\"':\s]*([\d.]+)\s*s", msg, re.I)
                wait = float(m.group(1)) + 1 if m else delay
                self.log(f"  ... {model}: {status or 'error'} - waiting {wait:.0f}s (attempt {attempt + 1}/6)")
                time.sleep(min(wait, 90))
                delay = min(delay * 2, 90)
        raise LLMError("unreachable")
