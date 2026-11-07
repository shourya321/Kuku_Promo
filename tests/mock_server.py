"""Fake OpenAI-compatible server for testing the LLM code path offline.
Returns plausible JSON for each role (and one deliberately broken reply)."""
import json, re, random, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

broken_once = {"done": False}

def reply(system, user):
    if "performance-marketing editor" in system:
        blocks = re.findall(r"\[B(\d+) (\d+):([\d.]+)-(\d+):([\d.]+)\] ([^\n]*)", user)
        bl = [(int(b), int(m1)*60+float(s1), int(m2)*60+float(s2), t) for b, m1, s1, m2, s2, t in blocks]
        hooks = [b for b in bl if "!" in b[3] and not b[3].startswith("CAMERA")] or bl
        cands = []
        for h in hooks[:2]:
            end = next((b for b in bl if b[2] >= h[1] + 30 and not b[3].startswith("CAMERA")), bl[-1])
            cands.append({"title": "t", "segments": [{"start_block": f"B{h[0]:03d}", "end_block": f"B{end[0]:03d}"}],
                          "hook_block": f"B{h[0]}", "hook": h[3][:60], "hook_type": "line",
                          "cliffhanger_block": f"E99-B{end[0]:03d}", "cliffhanger": end[3][:60], "open_question": "q",
                          "why": "w", "trope": "betrayal", "standalone_risk": "", "spoiler_risk": "low", "strength": random.randint(4, 9)})
        cands.append({"title": "bad", "segments": [{"start_block": "B999", "end_block": "B1000"}], "hook_block": "B999",
                      "hook": "x", "cliffhanger_block": "B1000", "cliffhanger": "x", "why": "x", "strength": 3})
        moments = [{"start_block": f"B{h[0]:03d}", "end_block": f"B{h[0]+3:03d}", "label": h[3][:40], "kind": "hook"} for h in hooks[:2]]
        out = {"episode_summary": "s", "candidates": cands, "moments": moments}
        if "EPISODE 2 " in user and not broken_once["done"]:
            broken_once["done"] = True
            return "Sure! here is json: {\"episode_summary\": 1, candidates: oops"
        return "```json\n" + json.dumps(out) + "\n```"
    if "strict creative-performance reviewer" in system:
        ids = re.findall(r"=== CLIP (\S+) ===", user)
        return json.dumps({"scores": [{"id": i, "hook": random.randint(2, 5), "cliffhanger": random.randint(2, 5),
                                       "standalone": random.randint(1, 5), "trope": random.randint(2, 5), "visual": "4",
                                       "critique": "c"} for i in ids]})
    if "random American" in system:
        return json.dumps({"what_is_happening": "a woman is betrayed", "who_vs_who": "a vs b", "unanswered_question": "?",
                           "confusing": [], "clarity": random.randint(2, 5), "keep_watching": random.randint(2, 5)})
    if "head of user acquisition" in system:
        ids = re.findall(r"^(\S+) \|", user, re.M)
        random.shuffle(ids)
        return json.dumps({"order": [{"id": i, "reason": "r"} for i in ids]})
    if "on-screen text for a microdrama" in system:
        return json.dumps({"context_caption": "She trusted her sister. Big mistake.", "ad_hook_text": "Wait for it"})
    if "story montage" in system:
        ids = re.findall(r"^(M\d+):", user, re.M)
        return json.dumps({"montages": [{"title": "m", "moment_ids": ids[:4], "hook": "h", "cliffhanger": "c", "why": "w"}]})
    return "{}"

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = body["messages"]
        text = reply(msgs[0]["content"], msgs[1]["content"])
        if len(msgs) > 2:  # repair turn
            text = reply(msgs[0]["content"], msgs[1]["content"].replace("EPISODE 2 ", "EPISODE 2b "))
        data = {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": len(json.dumps(msgs)) // 4, "completion_tokens": len(text) // 4, "total_tokens": 0}}
        b = json.dumps(data).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
